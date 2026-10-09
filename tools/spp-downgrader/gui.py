#!/usr/bin/env python3
"""SPP Downgrader: drag-and-drop GUI for universal-spp converter."""
import sys
import os
import json
import argparse
import threading
import time
import queue
import tempfile
import shutil
import subprocess
from pathlib import Path
from contextlib import redirect_stdout, redirect_stderr
from io import StringIO
from tkinter import filedialog, messagebox
import tkinter as tk
from tkinter import ttk
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
except ImportError:
    TkinterDnD = None

# Inject engine into sys.path when not frozen.
ENGINE = Path(__file__).parent / 'universal-spp' / 'spp_downgrader'
if str(ENGINE) not in sys.path:
    sys.path.insert(0, str(ENGINE))
if str(ENGINE / 'spp_extractor') not in sys.path:
    sys.path.insert(0, str(ENGINE / 'spp_extractor'))
if str(ENGINE / 'spp_builder') not in sys.path:
    sys.path.insert(0, str(ENGINE / 'spp_builder'))

import uspp_tool


def run_cmd(fn, **kw):
    """Run a uspp_tool command (fn) with captured output. Returns (exit_code, stdout, stderr)."""
    ns = argparse.Namespace(verbose=False, **kw)
    out_buf = StringIO()
    err_buf = StringIO()
    try:
        with redirect_stdout(out_buf), redirect_stderr(err_buf):
            code = fn(ns)
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else 1
    except Exception as e:
        import traceback
        err_buf.write(traceback.format_exc())
        code = 1
    return code, out_buf.getvalue(), err_buf.getvalue()


class SppDowngrader:
    def __init__(self, headless=False):
        self.headless = headless
        self.input_file = None
        self.uspp_file = None
        self.temp_uspp = None
        self.source_version = None
        self.last_output = None
        self.worker_thread = None
        self.work_queue = queue.Queue()

        if not headless:
            self.setup_gui()

    def cleanup_temp(self):
        """Delete the previous temp .uspp."""
        if self.temp_uspp and os.path.exists(self.temp_uspp):
            try:
                os.unlink(self.temp_uspp)
            except OSError:
                pass
        self.temp_uspp = None

    def log(self, msg):
        """Log a message (GUI or stdout in headless mode). Main thread only."""
        if self.headless:
            print(msg)
        else:
            self.log_text.config(state=tk.NORMAL)
            self.log_text.insert(tk.END, msg + '\n')
            self.log_text.see(tk.END)
            self.log_text.config(state=tk.DISABLED)

    def set_busy(self, busy):
        """Enable/disable UI controls."""
        if self.headless:
            return
        has_targets = bool(self.target_combo.cget('values'))
        self.drop_label.config(state=tk.NORMAL if not busy else tk.DISABLED)
        self.target_combo.config(state='readonly' if (not busy and has_targets) else tk.DISABLED)
        self.convert_btn.config(state=tk.NORMAL if (not busy and has_targets) else tk.DISABLED)
        self.root.config(cursor='watch' if busy else '')

    def load_file(self, path):
        """Load a .spp or .uspp file."""
        if not path:
            return
        ext = Path(path).suffix.lower()
        if ext not in ('.spp', '.uspp'):
            self.log(f"Not a .spp or .uspp: {path}")
            return

        self.cleanup_temp()
        self.input_file = path
        self.source_version = None
        self.last_output = None

        self.target_combo.config(values=[])
        self.target_combo.set('')
        self.source_label.config(text='Source version: -')
        self.open_folder_btn.config(state=tk.DISABLED)
        self.drop_label.config(text=Path(path).name)
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete('1.0', tk.END)
        self.log_text.config(state=tk.DISABLED)

        self.log(f"Loaded {path}")
        self.set_busy(True)

        if ext == '.uspp':
            self.uspp_file = path
            self.read_info()
        else:
            # Pack .spp to temp .uspp.
            self.temp_uspp = os.path.join(
                tempfile.gettempdir(),
                f"sppdowngrader_{os.urandom(8).hex()}.uspp"
            )
            self.uspp_file = self.temp_uspp
            self.log('Reading project (packing to temporary .uspp)...')
            self.run_async(
                lambda: run_cmd(uspp_tool.cmd_pack, input=self.input_file, output=self.temp_uspp),
                self.after_pack,
            )

    def after_pack(self, result):
        code, out, err = result
        if code != 0:
            self.log(f"Pack failed (exit {code}):\n{err}")
            self.set_busy(False)
            return
        self.read_info()

    def read_info(self):
        """Read the manifest and show source version + supported targets (fast, main thread)."""
        code, out, err = run_cmd(uspp_tool.cmd_info, uspp=self.uspp_file)
        if code != 0:
            self.log(f"Could not read file (exit {code}):\n{err}")
            self.set_busy(False)
            return

        try:
            info = json.loads(out)
        except ValueError as e:
            self.log(f"Error parsing info: {e}")
            self.set_busy(False)
            return
        self.source_version = info.get('created_version')
        if not self.source_version:
            self.log('File has no source version; cannot convert.')
            self.set_busy(False)
            return

        self.source_label.config(text=f'Source version: {self.source_version}')
        versions = info.get('supported_versions') or ['12.1', '12', '11', '10', '9', '8.1']
        self.target_combo.config(values=versions)
        self.target_combo.current(min(1, len(versions) - 1))
        self.log(f"Source is Painter {self.source_version}. Pick a target and click Convert.")
        self.set_busy(False)

    def run_async(self, work, on_done):
        """Run work() in a thread; on_done(result) is then called on the Tk main thread."""
        def worker():
            try:
                result = work()
            except Exception:
                import traceback
                result = (1, '', traceback.format_exc())
            self.work_queue.put((on_done, result))

        self.worker_thread = threading.Thread(target=worker, daemon=True)
        self.worker_thread.start()
        self.root.after(100, self.check_work)

    def check_work(self):
        """Poll for worker completion and hand the result to its callback."""
        try:
            on_done, result = self.work_queue.get_nowait()
        except queue.Empty:
            self.root.after(100, self.check_work)
            return
        on_done(result)

    def start_convert(self):
        """Initiate conversion."""
        target = self.target_combo.get()
        if not target:
            return

        self.set_busy(True)
        self.log(f"\nChecking v{self.source_version} -> v{target}...")
        self.run_async(
            lambda: run_cmd(uspp_tool.cmd_plan, uspp=self.uspp_file, target=target),
            lambda result: self.after_plan(result, target),
        )

    def after_plan(self, result, target):
        """Decide whether to proceed, asking about losses."""
        code, out, err = result
        if code != 0:
            self.log(f"Plan failed (exit {code}):\n{err}")
            self.set_busy(False)
            return
        try:
            plan = json.loads(out)
        except ValueError as e:
            self.log(f"Error parsing plan: {e}")
            self.set_busy(False)
            return

        if not plan.get('supported'):
            self.log(f"No conversion path from v{plan.get('source_version')} to v{target}.")
            self.set_busy(False)
            return

        if plan.get('lossy'):
            lines = []
            for feat in plan.get('lost_features', []):
                if isinstance(feat, str):
                    lines.append(f"- {feat}")
                else:
                    lines.append(f"- {json.dumps(feat, separators=(',', ':'), default=str)}")
            for fallback in plan.get('missing_raster_fallbacks', []):
                line = f"- {fallback['dataset']}: {fallback['reason']}"
                if line not in lines:
                    lines.append(line)
            shown = '\n'.join(lines[:25])
            if len(lines) > 25:
                shown += f"\n...and {len(lines) - 25} more"
            self.log(f"This downgrade is lossy:\n{shown}")
            answer = messagebox.askyesno(
                'Lossy downgrade',
                f"Downgrading v{plan.get('source_version')} to v{target} will lose some data:\n\n{shown}"
                "\n\nContinue? The original file is not changed."
            )
            if not answer:
                self.log('Cancelled.')
                self.set_busy(False)
                return

        self.start_build(target)

    def start_build(self, target):
        """Pick the output path and run build in the background."""
        out_dir = os.path.dirname(self.input_file)
        in_name = Path(self.input_file).stem
        out_path = os.path.join(out_dir, f"{in_name}_v{target}.spp")

        if os.path.exists(out_path):
            if not messagebox.askyesno('File exists', f"{out_path} already exists. Overwrite it?"):
                self.log('Cancelled.')
                self.set_busy(False)
                return

        self.log(f"Building {out_path} ...")
        self.last_output = out_path
        started = time.monotonic()
        self.run_async(
            lambda: run_cmd(uspp_tool.cmd_build, uspp=self.uspp_file, target=target, output=out_path),
            lambda result: self.after_build(result, started),
        )

    def after_build(self, result, started):
        code, out, err = result
        if out:
            self.log(out.strip())
        if code == 0:
            self.log(f"Done in {time.monotonic() - started:.0f}s. Close Painter fully before opening the new file.")
            self.open_folder_btn.config(state=tk.NORMAL)
        else:
            self.log(f"Build failed (exit {code}):\n{err}")
        self.set_busy(False)

    def setup_gui(self):
        """Create the tkinter GUI."""
        if TkinterDnD:
            self.root = TkinterDnD.Tk()
        else:
            self.root = tk.Tk()

        self.root.title('SPP Downgrader')
        self.root.geometry('560x430')
        self.root.minsize(560, 430)

        # Drop label
        self.drop_label = tk.Label(
            self.root,
            text="Drop a .spp or .uspp file here\n(or click to browse)",
            relief=tk.SOLID, borderwidth=1,
            font=('Segoe UI', 11),
            cursor='hand2'
        )
        self.drop_label.place(x=12, y=12, width=520, height=90)
        self.drop_label.bind('<Button-1>', lambda e: self.browse_file())
        if TkinterDnD:
            self.drop_label.drop_target_register(DND_FILES)
            self.drop_label.bind('<<Drop>>', self.on_drop)
            self.root.drop_target_register(DND_FILES)
            self.root.bind('<<Drop>>', self.on_drop)

        # Source version label
        self.source_label = tk.Label(self.root, text='Source version: -', font=('Segoe UI', 9))
        self.source_label.place(x=12, y=114, width=250, height=22)

        # Target version label and combobox
        tgt_label = tk.Label(self.root, text='Target version:', font=('Segoe UI', 9))
        tgt_label.place(x=12, y=146, width=95, height=22)

        self.target_combo = ttk.Combobox(self.root, state='readonly')
        self.target_combo.place(x=110, y=143, width=90, height=24)

        # Convert button
        self.convert_btn = tk.Button(
            self.root, text='Convert',
            command=self.start_convert,
            state=tk.DISABLED
        )
        self.convert_btn.place(x=212, y=141, width=100, height=28)

        # Open folder button
        self.open_folder_btn = tk.Button(
            self.root, text='Open output folder',
            command=self.open_output_folder,
            state=tk.DISABLED
        )
        self.open_folder_btn.place(x=322, y=141, width=130, height=28)

        # Log text
        self.log_text = tk.Text(
            self.root,
            font=('Consolas', 9),
            state=tk.DISABLED
        )
        self.log_text.place(x=12, y=180, width=520, height=200)

        # Scrollbar for log
        scroll = ttk.Scrollbar(self.root, command=self.log_text.yview)
        scroll.place(x=532, y=180, width=16, height=200)
        self.log_text.config(yscrollcommand=scroll.set)

        self.root.protocol('WM_DELETE_WINDOW', self.on_close)
        self.root.after(100, self.check_argv)

    def on_drop(self, event):
        """Handle drag-drop."""
        if self.worker_thread and self.worker_thread.is_alive():
            return
        try:
            files = self.root.tk.splitlist(event.data)
            if files:
                self.load_file(files[0])
        except Exception as e:
            self.log(f"Drop error: {e}")

    def browse_file(self):
        """Open file dialog."""
        if self.worker_thread and self.worker_thread.is_alive():
            return
        path = filedialog.askopenfilename(
            filetypes=[('Painter projects', '*.spp;*.uspp')]
        )
        if path:
            self.load_file(path)

    def open_output_folder(self):
        """Open the output folder."""
        if self.last_output:
            subprocess.Popen(['explorer', '/select,', self.last_output])

    def check_argv(self):
        """Load a file from sys.argv[1] if present."""
        if len(sys.argv) > 1:
            path = sys.argv[1]
            if os.path.isfile(path):
                self.load_file(path)

    def on_close(self):
        """Cleanup on window close."""
        self.cleanup_temp()
        self.root.destroy()

    def run(self):
        """Run the GUI."""
        self.root.mainloop()


def headless_convert(args):
    """Run headless conversion: --convert IN --target V -o OUT [--yes] [--log]."""
    app = SppDowngrader(headless=True)
    app.input_file = args.input

    # Pack if needed
    ext = Path(args.input).suffix.lower()
    if ext == '.spp':
        app.temp_uspp = os.path.join(
            tempfile.gettempdir(),
            f"sppdowngrader_{os.urandom(8).hex()}.uspp"
        )
        app.uspp_file = app.temp_uspp
        app.log('Packing to temporary .uspp...')
        code, out, err = run_cmd(uspp_tool.cmd_pack, input=args.input, output=app.temp_uspp)
        if code != 0:
            app.log(f"Pack failed (exit {code}):\n{err}")
            if args.log:
                with open(args.output + '.log', 'w') as f:
                    f.write(f"Pack failed (exit {code}):\n{err}\n")
            return code
    else:
        app.uspp_file = args.input

    # Plan
    code, out, err = run_cmd(uspp_tool.cmd_plan, uspp=app.uspp_file, target=args.target)
    if code != 0:
        app.log(f"Plan failed (exit {code}):\n{err}")
        if args.log:
            with open(args.output + '.log', 'w') as f:
                f.write(f"Plan failed (exit {code}):\n{err}\n")
        return code

    plan = json.loads(out)
    if not plan.get('supported'):
        app.log(f"No conversion path from v{plan.get('source_version')} to {args.target}")
        if args.log:
            with open(args.output + '.log', 'w') as f:
                f.write(f"No conversion path\n")
        return 2

    # If lossy and not --yes, exit 2
    if plan.get('lossy') and not args.yes:
        lines = []
        for feat in plan.get('lost_features', []):
            if isinstance(feat, str):
                lines.append(f"- {feat}")
            else:
                lines.append(f"- {json.dumps(feat, separators=(',', ':'), default=str)}")
        for fallback in plan.get('missing_raster_fallbacks', []):
            line = f"- {fallback['dataset']}: {fallback['reason']}"
            if line not in lines:
                lines.append(line)
        msg = '\n'.join(lines[:25])
        if len(lines) > 25:
            msg += f"\n...and {len(lines) - 25} more"
        app.log(f"Lossy downgrade would lose data:\n{msg}")
        if args.log:
            with open(args.output + '.log', 'w') as f:
                f.write(f"Lossy downgrade:\n{msg}\n")
        return 2

    # Build
    code, out, err = run_cmd(uspp_tool.cmd_build, uspp=app.uspp_file, target=args.target, output=args.output)
    if out:
        app.log(out.strip())
    if code == 0:
        app.log("Done.")
    else:
        app.log(f"Build failed (exit {code}):\n{err}")

    if args.log:
        log_text = '\n'.join([m for m in [out, err] if m])
        with open(args.output + '.log', 'w') as f:
            f.write(log_text)

    app.cleanup_temp()
    return code


def main():
    """Entry point."""
    import sys

    # Check for headless mode
    if '--convert' in sys.argv:
        parser = argparse.ArgumentParser(description='SPP Downgrader headless converter')
        parser.add_argument('--convert', required=True, dest='input', metavar='IN')
        parser.add_argument('--target', required=True, metavar='V')
        parser.add_argument('-o', '--output', required=True, metavar='OUT')
        parser.add_argument('--yes', action='store_true', help='Skip lossy confirmation')
        parser.add_argument('--log', action='store_true', help='Write .log file')
        args = parser.parse_args()
        sys.exit(headless_convert(args))

    # GUI mode
    app = SppDowngrader(headless=False)
    app.run()


if __name__ == '__main__':
    main()
