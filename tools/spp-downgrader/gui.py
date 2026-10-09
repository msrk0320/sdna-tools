#!/usr/bin/env python3
"""SPP Downgrader: drag-and-drop GUI for universal-spp converter."""
import sys
import os
import json
import argparse
import threading
import time
import math
import queue
import tempfile
import shutil
import subprocess
from pathlib import Path
from contextlib import redirect_stdout, redirect_stderr
from io import StringIO
from tkinter import filedialog, messagebox
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
except ImportError:
    TkinterDnD = None
try:
    import sv_ttk
except ImportError:
    sv_ttk = None

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


# ---------------------------------------------------------------------------
# Design tokens. Colours follow the Windows 11 (WinUI) light/dark palettes;
# every text pair is >= 4.5:1 and every boundary/icon pair >= 3:1.
# ---------------------------------------------------------------------------
THEMES = {
    'light': {
        'bg': '#fafafa', 'surface': '#ffffff', 'surface_hover': '#f3f3f3',
        'border': '#e1e1e1', 'border_strong': '#8a8a8a',
        'text': '#1c1c1c', 'text2': '#5d5d5d',
        'accent': '#005fb8', 'accent_tint': '#eaf2fb',
        'success': '#0f7b0f', 'success_bg': '#dff6dd',
        'caution': '#9d5d00', 'caution_bg': '#fff4ce',
        'critical': '#c42b1c', 'critical_bg': '#fde7e9',
        'log_bg': '#f3f3f3',
    },
    'dark': {
        'bg': '#1c1c1c', 'surface': '#2b2b2b', 'surface_hover': '#323232',
        'border': '#3d3d3d', 'border_strong': '#8a8a8a',
        'text': '#fafafa', 'text2': '#c5c5c5',
        'accent': '#57c8ff', 'accent_tint': '#1d3240',
        'success': '#6ccb5f', 'success_bg': '#393d1b',
        'caution': '#fce100', 'caution_bg': '#433519',
        'critical': '#ff99a4', 'critical_bg': '#442726',
        'log_bg': '#232323',
    },
}

# Segoe Fluent Icons / Segoe MDL2 Assets code points (same in both fonts).
ICON_OPEN = ''
ICON_RELEASE = ''
ICON_DOCUMENT = ''
ICON_INFO = ''
ICON_WARNING = ''
ICON_ERROR = ''
ICON_SUCCESS = ''

CONTENT_W = 520  # logical px; everything is multiplied by the DPI scale


def system_theme():
    """'dark' or 'light', from the Windows app-mode setting."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r'Software\Microsoft\Windows\CurrentVersion\Themes\Personalize') as key:
            return 'light' if winreg.QueryValueEx(key, 'AppsUseLightTheme')[0] else 'dark'
    except OSError:
        return 'light'


def loss_lines(plan):
    """Human-readable list of what a lossy plan drops."""
    lines = []
    for feat in plan.get('lost_features', []):
        lines.append(feat if isinstance(feat, str)
                     else json.dumps(feat, separators=(',', ':'), default=str))
    for fallback in plan.get('missing_raster_fallbacks', []):
        line = f"{fallback['dataset']}: {fallback['reason']}"
        if line not in lines:
            lines.append(line)
    return lines


def fit_text(text, font, width, middle=False):
    """Shorten text with an ellipsis (at the end, or in the middle for paths)."""
    if font.measure(text) <= width:
        return text
    if middle:
        left, right = text[:len(text) // 2], text[len(text) // 2:]
        while left and right and font.measure(left + '…' + right) > width:
            left, right = left[:-1], right[1:]
        return left + '…' + right
    while text and font.measure(text + '…') > width:
        text = text[:-1]
    return text + '…'


def round_rect(canvas, x1, y1, x2, y2, r, **kw):
    """Rounded rectangle as a polygon with explicit corner arcs."""
    pts = []
    for cx, cy, start in ((x2 - r, y1 + r, -90), (x2 - r, y2 - r, 0),
                          (x1 + r, y2 - r, 90), (x1 + r, y1 + r, 180)):
        for i in range(9):
            a = math.radians(start + i * 90 / 8)
            pts += [cx + r * math.cos(a), cy + r * math.sin(a)]
    return canvas.create_polygon(pts, **kw)


def make_app_icon(size):
    """Window icon drawn in code: an accent tile with a down arrow onto a baseline."""
    accent, fg = (0x00, 0x5f, 0xb8), (0xff, 0xff, 0xff)
    r, ss = 0.22 * size, 4

    def in_tile(x, y):
        dx = max(r - x, 0, x - (size - r))
        dy = max(r - y, 0, y - (size - r))
        return dx * dx + dy * dy <= r * r

    def in_glyph(x, y):
        u, v = x / size, y / size
        if 0.44 <= u <= 0.56 and 0.18 <= v <= 0.52:
            return True
        if 0.46 <= v <= 0.72 and abs(u - 0.5) <= (0.72 - v) / 0.26 * 0.24:
            return True
        return 0.25 <= u <= 0.75 and 0.79 <= v <= 0.86

    img = tk.PhotoImage(width=size, height=size)
    rows, clear = [], []
    for py in range(size):
        row = []
        for px in range(size):
            tile = glyph = 0
            for sy in range(ss):
                for sx in range(ss):
                    x, y = px + (sx + 0.5) / ss, py + (sy + 0.5) / ss
                    if in_tile(x, y):
                        tile += 1
                        glyph += in_glyph(x, y)
            if tile < ss * ss / 2:
                clear.append((px, py))
            t = glyph / tile if tile else 0
            row.append('#%02x%02x%02x' % tuple(round(a + (b - a) * t) for a, b in zip(accent, fg)))
        rows.append('{' + ' '.join(row) + '}')
    img.put(' '.join(rows))
    for px, py in clear:
        img.transparency_set(px, py, True)
    return img


class Surface(tk.Canvas):
    """Rounded panel that hosts a plain frame (`body`) and sizes itself to it."""

    def __init__(self, master, app, fill, outline=None, pad=12):
        # Start tall so the hosted frame is mapped and reports its size; _fit then shrinks it.
        super().__init__(master, highlightthickness=0, bd=0, height=app.px(240))
        self.app, self.fill, self.outline = app, fill, outline
        self.pad = app.px(pad)
        self.body = tk.Frame(self, bd=0, highlightthickness=0)
        self.window = self.create_window(self.pad, self.pad, window=self.body, anchor='nw')
        self.body.bind('<Configure>', self._fit)
        self.bind('<Configure>', lambda e: self.redraw())
        app.surfaces.append(self)
        self.redraw()

    def _fit(self, _event=None):
        h = self.body.winfo_reqheight() + 2 * self.pad
        if int(self.cget('height')) != h:
            self.configure(height=h)

    def redraw(self):
        p = self.app.colors
        self.configure(bg=p['bg'])
        self.body.configure(bg=p[self.fill])
        w, h = self.winfo_width(), self.winfo_height()
        self.delete('panel')
        if w > 1 and h > 1:
            round_rect(self, 1, 1, w - 1, h - 1, self.app.px(6), tags='panel',
                       fill=p[self.fill], outline=p[self.outline] if self.outline else p[self.fill])
            self.tag_lower('panel')
            self.itemconfigure(self.window, width=w - 2 * self.pad)


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

    # ------------------------------------------------------------------
    # Worker plumbing: engine calls run in a thread that never touches Tk;
    # results come back through a queue polled with root.after.
    # ------------------------------------------------------------------
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

    def is_working(self):
        return self.phase != 'idle'

    # ------------------------------------------------------------------
    # Flow: load -> (pack) -> info -> pick target -> plan -> confirm -> build
    # ------------------------------------------------------------------
    def load_file(self, path):
        """Load a .spp or .uspp file."""
        if not path:
            return
        ext = Path(path).suffix.lower()
        if ext not in ('.spp', '.uspp'):
            self.log(f"Not a .spp or .uspp: {path}")
            self.show_message('error', 'Not a Painter project',
                              f"{Path(path).name} is not a .spp or .uspp file.")
            return

        self.cleanup_temp()
        self.input_file = path
        self.source_version = None
        self.last_output = None
        self.versions = []
        try:
            self.file_size = os.path.getsize(path)
        except OSError:
            self.file_size = None

        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete('1.0', tk.END)
        self.log_text.config(state=tk.DISABLED)
        self.log(f"Loaded {path}")
        self.start_busy('Opening project', 'Reading layers, textures and settings.')

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
            temp, src = self.temp_uspp, self.input_file
            self.run_async(
                lambda: run_cmd(uspp_tool.cmd_pack, input=src, output=temp),
                self.after_pack,
            )

    def after_pack(self, result):
        code, out, err = result
        if code != 0:
            self.log(f"Pack failed (exit {code}):\n{err}")
            self.fail('Could not open this project', err, code)
            return
        self.read_info()

    def read_info(self):
        """Read the manifest (in the background) for source version + supported targets."""
        uspp = self.uspp_file
        self.run_async(lambda: run_cmd(uspp_tool.cmd_info, uspp=uspp), self.after_info)

    def after_info(self, result):
        code, out, err = result
        if code != 0:
            self.log(f"Could not read file (exit {code}):\n{err}")
            self.fail('Could not read this project', err, code)
            return
        try:
            info = json.loads(out)
        except ValueError as e:
            self.log(f"Error parsing info: {e}")
            self.fail('Could not read this project', str(e))
            return
        self.source_version = info.get('created_version')
        if not self.source_version:
            self.log('File has no source version; cannot convert.')
            self.fail('Unknown Painter version',
                      'The file does not record which Painter version saved it, so it cannot be converted.')
            return

        self.versions = info.get('supported_versions') or ['12.1', '12', '11', '10', '9', '8.1']
        self.target_combo.config(values=[f'Painter {v}' for v in self.versions])
        self.target_combo.current(min(1, len(self.versions) - 1))
        self.log(f"Source is Painter {self.source_version}. Pick a target and click Convert.")
        self.stop_busy()
        self.show_hint()
        self.convert_btn.focus_set()

    def selected_target(self):
        i = self.target_combo.current()
        return self.versions[i] if 0 <= i < len(self.versions) else None

    def output_path(self, target):
        return os.path.join(os.path.dirname(self.input_file),
                            f"{Path(self.input_file).stem}_v{target}.spp")

    def start_convert(self):
        """Initiate conversion."""
        target = self.selected_target()
        if not target or self.is_working():
            return

        self.log(f"\nChecking v{self.source_version} -> v{target}...")
        self.start_busy(f'Checking Painter {target} compatibility', 'Step 1 of 2')
        uspp = self.uspp_file
        self.run_async(
            lambda: run_cmd(uspp_tool.cmd_plan, uspp=uspp, target=target),
            lambda result: self.after_plan(result, target),
        )

    def after_plan(self, result, target):
        """Decide whether to proceed, asking about losses inline."""
        code, out, err = result
        if code != 0:
            self.log(f"Plan failed (exit {code}):\n{err}")
            self.fail('Could not check compatibility', err, code)
            return
        try:
            plan = json.loads(out)
        except ValueError as e:
            self.log(f"Error parsing plan: {e}")
            self.fail('Could not check compatibility', str(e))
            return

        if not plan.get('supported'):
            self.log(f"No conversion path from v{plan.get('source_version')} to v{target}.")
            self.stop_busy()
            self.show_message('error', f'Painter {target} is not supported for this file',
                              f"There is no conversion path from Painter {plan.get('source_version')} "
                              f"to {target}. Pick another target version.")
            return

        lost = loss_lines(plan) if plan.get('lossy') else []
        if lost:
            self.log("This downgrade is lossy:\n" + '\n'.join(f'- {l}' for l in lost))
        exists = os.path.exists(self.output_path(target))
        self.stop_busy()
        if lost or exists:
            self.show_confirm(target, lost, exists)
        else:
            self.start_build(target)

    def cancel_confirm(self):
        self.log('Cancelled.')
        self.phase = 'idle'
        self.show_hint()
        self.sync_controls()
        self.convert_btn.focus_set()

    def start_build(self, target):
        """Run the build in the background; output goes next to the input."""
        out_path = self.output_path(target)
        self.log(f"Building {out_path} ...")
        self.last_output = out_path
        started = time.monotonic()
        self.start_busy(f'Writing Painter {target} project', 'Step 2 of 2 · The original file is not changed.')
        uspp = self.uspp_file
        self.run_async(
            lambda: run_cmd(uspp_tool.cmd_build, uspp=uspp, target=target, output=out_path),
            lambda result: self.after_build(result, started, target),
        )

    def after_build(self, result, started, target):
        code, out, err = result
        if out:
            self.log(out.strip())
        if code == 0:
            secs = time.monotonic() - started
            self.log(f"Done in {secs:.0f}s. Close Painter fully before opening the new file.")
            self.stop_busy()
            self.show_message('success', f'Saved {Path(self.last_output).name}',
                              f'Converted to Painter {target} in {secs:.0f} s. '
                              'Close Painter fully before opening the new file.',
                              action=('Show in folder', self.open_output_folder))
        else:
            self.log(f"Build failed (exit {code}):\n{err}")
            self.last_output = None
            self.fail('Conversion failed', err, code)

    def fail(self, title, err, code=None):
        """End a busy phase with an inline error and the log opened."""
        lines = [l.strip() for l in (err or '').strip().splitlines() if l.strip()]
        detail = lines[-1] if lines else (f'The engine exited with code {code}.' if code else '')
        if len(detail) > 220:
            detail = detail[:220] + '…'
        self.stop_busy()
        self.show_message('error', title, detail or 'See details below.')
        self.set_details(True)

    # ------------------------------------------------------------------
    # GUI construction
    # ------------------------------------------------------------------
    def px(self, n):
        return int(round(n * self.scale))

    def setup_gui(self):
        """Create the tkinter GUI."""
        if sys.platform == 'win32':
            try:
                import ctypes
                ctypes.windll.shcore.SetProcessDpiAwareness(1)
            except (AttributeError, OSError):
                pass
        if TkinterDnD:
            self.root = TkinterDnD.Tk()
        else:
            self.root = tk.Tk()

        self.root.withdraw()
        self.root.title('SPP Downgrader')
        self.root.resizable(False, False)
        self.scale = max(1.0, self.root.winfo_fpixels('1i') / 96)
        self.phase = 'idle'
        self.versions = []
        self.file_size = None
        self.zone_hover = self.zone_drag = False
        self.details_open = False
        self.busy_started = None
        self.tick_job = None
        self.themed = []
        self.surfaces = []
        self.theme = None
        self.colors = THEMES['light']
        self.message = None

        self.setup_fonts()
        if sv_ttk:
            sv_ttk.set_theme('light', self.root)  # loads the theme; real mode applied below
            self.scale_sv_fonts()
        self.style = ttk.Style(self.root)

        try:
            self.icons = [make_app_icon(64), make_app_icon(32)]
            self.root.iconphoto(True, *self.icons)
        except tk.TclError:
            pass

        pad = self.px(24)
        outer = self.paint(tk.Frame(self.root, bd=0), bg='bg')
        outer.pack(fill=tk.BOTH, expand=True, padx=pad, pady=(self.px(20), self.px(12)))
        self.outer = outer

        # Header
        self.paint(tk.Label(outer, text='SPP Downgrader', font=self.f_title, anchor='w'),
                   bg='bg', fg='text').pack(fill=tk.X)
        self.paint(tk.Label(outer, text='Save a Substance Painter project for an older Painter version.',
                            font=self.f_body, anchor='w'), bg='bg', fg='text2').pack(fill=tk.X, pady=(self.px(2), 0))

        # Drop zone: focusable, clickable, keyboard operable.
        self.zone = tk.Canvas(outer, width=self.px(CONTENT_W), height=self.px(128),
                              highlightthickness=0, bd=0, takefocus=1, cursor='hand2')
        self.zone.pack(pady=(self.px(16), 0))
        self.zone.bind('<Configure>', lambda e: self.draw_zone())
        self.zone.bind('<Button-1>', lambda e: self.browse_file())
        self.zone.bind('<Return>', lambda e: self.browse_file())
        self.zone.bind('<space>', lambda e: self.browse_file())
        self.zone.bind('<Enter>', lambda e: self.set_zone(hover=True))
        self.zone.bind('<Leave>', lambda e: self.set_zone(hover=False))
        self.zone.bind('<FocusIn>', lambda e: self.draw_zone())
        self.zone.bind('<FocusOut>', lambda e: self.draw_zone())
        if TkinterDnD:
            for w in (self.root, self.zone):
                w.drop_target_register(DND_FILES)
                w.dnd_bind('<<DropEnter>>', self.on_drag_enter)
                w.dnd_bind('<<DropLeave>>', self.on_drag_leave)
                w.dnd_bind('<<Drop>>', self.on_drop)

        # Target row
        row = self.paint(tk.Frame(outer, bd=0), bg='bg')
        row.pack(fill=tk.X, pady=(self.px(16), 0))
        self.paint(tk.Label(row, text='Convert to', font=self.f_body), bg='bg', fg='text').pack(side=tk.LEFT)
        self.target_combo = ttk.Combobox(row, state=tk.DISABLED, width=12)
        self.target_combo.pack(side=tk.LEFT, padx=(self.px(12), 0))
        self.target_combo.bind('<<ComboboxSelected>>', self.on_target_changed)
        self.convert_btn = self.button(row, 'Convert', self.start_convert, style='Accent.TButton')
        self.convert_btn.ring.pack(side=tk.RIGHT)
        self.output_label = self.paint(tk.Label(outer, font=self.f_caption, anchor='w', justify=tk.LEFT),
                                       bg='bg', fg='text2')
        self.output_label.pack(fill=tk.X, pady=(self.px(6), 0))

        # Status area: keeps a minimum height so routine states don't resize the window.
        self.status = self.paint(tk.Frame(outer, bd=0), bg='bg')
        self.status.pack(fill=tk.X, pady=(self.px(16), 0))
        self.status.grid_columnconfigure(0, weight=1)
        self.status.grid_rowconfigure(0, minsize=self.px(112))

        # Footer: progressive disclosure for the engine log.
        foot = self.paint(tk.Frame(outer, bd=0), bg='bg')
        foot.pack(fill=tk.X, pady=(self.px(8), 0))
        self.details_btn = self.button(foot, 'Show details', lambda: self.set_details(not self.details_open),
                                       style='Link.Toolbutton')
        self.details_btn.ring.pack(side=tk.LEFT)
        self.paint(tk.Label(foot, text='Ctrl+O  Open file', font=self.f_caption),
                   bg='bg', fg='text2').pack(side=tk.RIGHT)

        self.log_frame = self.paint(tk.Frame(outer, bd=0), bg='bg')
        self.log_text = tk.Text(self.log_frame, height=10, width=1, wrap=tk.WORD, font=self.f_mono,
                                relief=tk.FLAT, bd=0, padx=self.px(10), pady=self.px(8),
                                highlightthickness=1, state=tk.DISABLED)
        self.paint(self.log_text, bg='log_bg', fg='text', highlightbackground='border',
                   highlightcolor='accent', insertbackground='text',
                   selectbackground='accent', selectforeground='surface')
        scroll = ttk.Scrollbar(self.log_frame, command=self.log_text.yview)
        self.log_text.config(yscrollcommand=scroll.set)
        scroll.pack(side=tk.RIGHT, fill=tk.Y, padx=(self.px(4), 0))
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.root.bind_all('<Control-o>', lambda e: self.browse_file())
        self.root.bind_all('<Control-O>', lambda e: self.browse_file())
        self.root.bind('<Escape>', self.on_escape)

        self.apply_theme(system_theme())
        self.show_hint()
        self.sync_controls()
        self.root.protocol('WM_DELETE_WINDOW', self.on_close)
        self.root.deiconify()
        self.root.after(50, self.style_titlebar)  # re-apply once the native frame is mapped
        self.zone.focus_set()
        self.root.after(1500, self.watch_theme)
        self.root.after(100, self.check_argv)

    def setup_fonts(self):
        families = set(tkfont.families(self.root))

        def pick(*names):
            return next((n for n in names if n in families), 'Segoe UI')

        text = pick('Segoe UI Variable Text', 'Segoe UI')
        strong = pick('Segoe UI Variable Text Semibold', 'Segoe UI Semibold')
        display = pick('Segoe UI Variable Display Semib', 'Segoe UI Semibold')
        self.icon_family = pick('Segoe Fluent Icons', 'Segoe MDL2 Assets')
        self.f_title = tkfont.Font(self.root, family=display, size=-self.px(22))
        self.f_body = tkfont.Font(self.root, family=text, size=-self.px(14))
        self.f_strong = tkfont.Font(self.root, family=strong, size=-self.px(14))
        self.f_caption = tkfont.Font(self.root, family=text, size=-self.px(12))
        self.f_icon = tkfont.Font(self.root, family=self.icon_family, size=-self.px(16))
        self.f_icon_lg = tkfont.Font(self.root, family=self.icon_family, size=-self.px(28))
        self.f_mono = tkfont.Font(self.root, family=pick('Cascadia Mono', 'Consolas'), size=-self.px(12))
        self.font_families = {'text': text, 'strong': strong, 'display': display}

    def scale_sv_fonts(self):
        """sv_ttk sizes its fonts in raw pixels; rescale them for this display's DPI."""
        fam = self.font_families
        for name, family, size in (
                ('SunValleyCaptionFont', fam['text'], 12), ('SunValleyBodyFont', fam['text'], 14),
                ('SunValleyBodyStrongFont', fam['strong'], 14), ('SunValleyBodyLargeFont', fam['text'], 18),
                ('SunValleySubtitleFont', fam['display'], 20), ('SunValleyTitleFont', fam['display'], 28)):
            try:
                self.root.tk.call('font', 'configure', name, '-family', family, '-size', -self.px(size))
            except tk.TclError:
                pass

    def button(self, parent, text, command, style='TButton'):
        """ttk button inside a 2px ring that shows keyboard focus clearly in both themes."""
        ring = self.paint(tk.Frame(parent, bd=0), bg='bg')
        btn = ttk.Button(ring, text=text, command=command, style=style)
        btn.pack(padx=self.px(2), pady=self.px(2))
        btn.ring = ring
        btn.bind('<FocusIn>', lambda e: self.paint_ring(btn), add='+')
        btn.bind('<FocusOut>', lambda e: self.paint_ring(btn), add='+')
        btn.bind('<Return>', lambda e: btn.invoke())
        return btn

    def paint_ring(self, btn):
        try:
            focused = self.root.focus_get() is btn
        except KeyError:
            focused = False
        btn.ring.configure(bg=self.colors['text' if focused else 'bg'])

    def paint(self, widget, **roles):
        """Register a classic Tk widget whose colours follow the theme tokens."""
        self.themed.append((widget, roles))
        widget.configure(**{opt: self.colors[role] for opt, role in roles.items()})
        return widget

    # ------------------------------------------------------------------
    # Theme
    # ------------------------------------------------------------------
    def apply_theme(self, mode):
        self.theme = mode
        self.colors = p = THEMES[mode]
        if sv_ttk:
            sv_ttk.set_theme(mode, self.root)
        s = self.style
        # ttk styles are per theme, so they are re-applied after every switch.
        s.configure('TButton', padding=(self.px(14), self.px(5)))
        s.configure('Accent.TButton', padding=(self.px(18), self.px(5)))
        s.configure('TCombobox', padding=(self.px(8), self.px(3)))
        s.configure('Link.Toolbutton', padding=(self.px(8), self.px(4)), foreground=p['accent'])
        s.map('Link.Toolbutton', foreground=[('disabled', p['text2'])])
        self.root.configure(bg=p['bg'])
        # Combobox drop-down list (a classic listbox) follows the theme too.
        self.root.option_add('*TCombobox*Listbox.font', self.f_body)
        self.root.option_add('*TCombobox*Listbox.background', p['surface'])
        self.root.option_add('*TCombobox*Listbox.foreground', p['text'])
        self.themed = [(w, r) for w, r in self.themed if w.winfo_exists()]
        for w, roles in self.themed:
            w.configure(**{opt: p[role] for opt, role in roles.items()})
        self.surfaces = [sf for sf in self.surfaces if sf.winfo_exists()]
        for sf in self.surfaces:
            sf.redraw()
        self.draw_zone()
        for w, _ in self.themed:
            for child in w.winfo_children():
                if hasattr(child, 'ring'):
                    self.paint_ring(child)
        self.style_titlebar()

    def style_titlebar(self):
        """Dark/light title bar that blends into the window (Windows 10 20H1+/11)."""
        if sys.platform != 'win32':
            return
        try:
            import ctypes
            hwnd = int(self.root.wm_frame(), 16)
            dark = ctypes.c_int(1 if self.theme == 'dark' else 0)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(dark), 4)
            bg = self.colors['bg']
            colorref = ctypes.c_int(int(bg[5:7] + bg[3:5] + bg[1:3], 16))
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(colorref), 4)
        except (AttributeError, OSError):
            pass

    def watch_theme(self):
        mode = system_theme()
        if mode != self.theme:
            self.apply_theme(mode)
        self.root.after(1500, self.watch_theme)

    # ------------------------------------------------------------------
    # Drop zone
    # ------------------------------------------------------------------
    def set_zone(self, hover=None, drag=None):
        if hover is not None:
            self.zone_hover = hover
        if drag is not None:
            self.zone_drag = drag
        self.draw_zone()

    def draw_zone(self):
        z, p = self.zone, self.colors
        w, h = int(z.cget('width')), int(z.cget('height'))
        z.delete('all')
        z.configure(bg=p['bg'])
        try:
            focused = self.root.focus_get() is z
        except KeyError:  # focus inside the combobox pop-down
            focused = False
        active = self.zone_drag or focused
        loaded = bool(self.input_file)
        fill = p['accent_tint'] if self.zone_drag else (
            p['surface_hover'] if self.zone_hover and not self.is_working() else p['surface'])
        bw = self.px(2) if active else 1
        inset = bw / 2 + 1
        round_rect(z, inset, inset, w - inset, h - inset, self.px(8), fill=fill,
                   outline=p['accent'] if active else (p['border'] if loaded else p['border_strong']),
                   width=bw, dash=() if (active or loaded) else (4, 3))
        cx, cy = w / 2, h / 2

        if self.zone_drag:
            z.create_text(cx, cy - self.px(14), text=ICON_RELEASE, font=self.f_icon_lg, fill=p['accent'])
            z.create_text(cx, cy + self.px(24), text='Release to open', font=self.f_strong, fill=p['text'])
            return
        if not loaded:
            z.create_text(cx, cy - self.px(22), text=ICON_OPEN, font=self.f_icon_lg, fill=p['accent'])
            z.create_text(cx, cy + self.px(14), text='Drop a .spp or .uspp file here',
                          font=self.f_strong, fill=p['text'])
            z.create_text(cx, cy + self.px(36), text='or click to browse', font=self.f_caption, fill=p['text2'])
            return

        x = self.px(76)
        tw = w - x - self.px(24)
        z.create_text(self.px(40), cy, text=ICON_DOCUMENT, font=self.f_icon_lg, fill=p['accent'])
        name = Path(self.input_file).name
        z.create_text(x, cy - self.px(26), anchor='w', fill=p['text'], font=self.f_strong,
                      text=fit_text(name, self.f_strong, tw))
        meta = []
        if self.source_version:
            meta.append(f'Painter {self.source_version}')
        elif self.is_working():
            meta.append('Reading project…')
        if self.file_size is not None:
            meta.append(f'{self.file_size / 1048576:,.1f} MB')
        z.create_text(x, cy - self.px(4), anchor='w', fill=p['text'], font=self.f_body,
                      text='  ·  '.join(meta))
        z.create_text(x, cy + self.px(18), anchor='w', fill=p['text2'], font=self.f_caption,
                      text=fit_text(os.path.dirname(self.input_file), self.f_caption, tw, middle=True))
        if not self.is_working():
            z.create_text(x, cy + self.px(40), anchor='w', fill=p['accent'], font=self.f_caption,
                          text='Click or drop another file to replace')

    def on_drag_enter(self, event):
        if not self.is_working():
            self.set_zone(drag=True)
        return event.action

    def on_drag_leave(self, event):
        self.set_zone(drag=False)
        return event.action

    # ------------------------------------------------------------------
    # Status area states: hint / busy / confirm / success / error
    # ------------------------------------------------------------------
    def clear_status(self):
        for child in self.status.winfo_children():
            child.destroy()
        self.message = None
        frame = self.paint(tk.Frame(self.status, bd=0), bg='bg')
        frame.grid(row=0, column=0, sticky='new')
        return frame

    def show_hint(self):
        frame = self.clear_status()
        row = self.paint(tk.Frame(frame, bd=0), bg='bg')
        row.pack(fill=tk.X)
        self.paint(tk.Label(row, text=ICON_INFO, font=self.f_icon), bg='bg', fg='text2').pack(
            side=tk.LEFT, anchor='n', pady=(self.px(2), 0))
        self.paint(tk.Label(row, font=self.f_caption, justify=tk.LEFT, anchor='w',
                            wraplength=self.px(CONTENT_W - 32),
                            text='Your original file is never changed. The converted copy is saved '
                                 'next to it, and you will be asked before any features are dropped.'),
                   bg='bg', fg='text2').pack(side=tk.LEFT, fill=tk.X, padx=(self.px(10), 0))

    def start_busy(self, title, caption):
        self.phase = 'busy'
        self.busy_started = time.monotonic()
        frame = self.clear_status()
        head = self.paint(tk.Frame(frame, bd=0), bg='bg')
        head.pack(fill=tk.X)
        self.paint(tk.Label(head, text=title + '…', font=self.f_strong, anchor='w'),
                   bg='bg', fg='text').pack(side=tk.LEFT)
        self.elapsed_label = self.paint(tk.Label(head, text='0:00', font=self.f_caption), bg='bg', fg='text2')
        self.elapsed_label.pack(side=tk.RIGHT)
        bar = ttk.Progressbar(frame, mode='indeterminate')
        bar.pack(fill=tk.X, pady=(self.px(10), self.px(8)))
        bar.start(12)
        self.paint(tk.Label(frame, text=caption, font=self.f_caption, anchor='w'),
                   bg='bg', fg='text2').pack(fill=tk.X)
        self.sync_controls()
        self.tick()

    def tick(self):
        if self.tick_job:
            self.root.after_cancel(self.tick_job)
            self.tick_job = None
        if self.phase != 'busy':
            return
        secs = int(time.monotonic() - self.busy_started)
        if self.elapsed_label.winfo_exists():
            self.elapsed_label.configure(text=f'{secs // 60}:{secs % 60:02d}')
        self.tick_job = self.root.after(500, self.tick)

    def stop_busy(self):
        self.phase = 'idle'
        self.tick()
        self.sync_controls()

    def info_bar(self, parent, kind, title, body):
        """WinUI-style InfoBar: tinted panel, semantic icon, title and message."""
        icon = {'success': ICON_SUCCESS, 'caution': ICON_WARNING, 'error': ICON_ERROR}[kind]
        role = {'success': 'success', 'caution': 'caution', 'error': 'critical'}[kind]
        bar = Surface(parent, self, fill=role + '_bg', pad=14)
        bar.pack(fill=tk.X)
        b = bar.body
        self.paint(tk.Label(b, text=icon, font=self.f_icon), bg=role + '_bg', fg=role).grid(
            row=0, column=0, rowspan=2, sticky='n', pady=(self.px(2), 0))
        self.paint(tk.Label(b, text=title, font=self.f_strong, anchor='w', justify=tk.LEFT,
                            wraplength=self.px(CONTENT_W - 70)),
                   bg=role + '_bg', fg='text').grid(row=0, column=1, sticky='w', padx=(self.px(12), 0))
        if body:
            self.paint(tk.Label(b, text=body, font=self.f_body, anchor='w', justify=tk.LEFT,
                                wraplength=self.px(CONTENT_W - 70)),
                       bg=role + '_bg', fg='text').grid(row=1, column=1, sticky='w',
                                                        padx=(self.px(12), 0), pady=(self.px(2), 0))
        b.grid_columnconfigure(1, weight=1)
        return bar

    def show_message(self, kind, title, body, action=None):
        frame = self.clear_status()
        self.info_bar(frame, kind, title, body)
        self.message = kind
        if action:
            btns = self.paint(tk.Frame(frame, bd=0), bg='bg')
            btns.pack(fill=tk.X, pady=(self.px(12), 0))
            btn = self.button(btns, action[0], action[1])
            btn.ring.pack(side=tk.RIGHT)
            btn.focus_set()
        self.sync_controls()

    def show_confirm(self, target, lost, exists):
        self.phase = 'confirm'
        frame = self.clear_status()
        out_name = Path(self.output_path(target)).name
        if lost:
            n = len(lost)
            title = f'{n} item{"s" if n != 1 else ""} will be lost in Painter {target}'
            body = 'Painter ' + str(target) + ' cannot represent these. The original file is not changed.'
        else:
            title = f'{out_name} already exists'
            body = 'Converting again will replace it.'
        if lost and exists:
            body += f' {out_name} already exists and will be replaced.'
        self.info_bar(frame, 'caution', title, body)

        if lost:
            box = self.paint(tk.Frame(frame, bd=0), bg='bg')
            box.pack(fill=tk.X, pady=(self.px(10), 0))
            lines = min(len(lost), 7)
            text = tk.Text(box, height=lines, width=1, wrap=tk.WORD, font=self.f_body, relief=tk.FLAT,
                           bd=0, padx=self.px(12), pady=self.px(8), highlightthickness=1,
                           spacing1=self.px(1), spacing3=self.px(1), takefocus=1)
            self.paint(text, bg='surface', fg='text', highlightbackground='border',
                       highlightcolor='accent', selectbackground='accent', selectforeground='surface')
            text.insert('1.0', '\n'.join('•  ' + l for l in lost))
            text.config(state=tk.DISABLED)
            if len(lost) > lines:
                sb = ttk.Scrollbar(box, command=text.yview)
                text.config(yscrollcommand=sb.set)
                sb.pack(side=tk.RIGHT, fill=tk.Y, padx=(self.px(4), 0))
            text.pack(side=tk.LEFT, fill=tk.X, expand=True)

        btns = self.paint(tk.Frame(frame, bd=0), bg='bg')
        btns.pack(fill=tk.X, pady=(self.px(12), 0))
        go = self.button(btns, 'Replace and convert' if not lost else 'Convert anyway',
                         lambda: self.start_build(target), style='Accent.TButton')
        go.ring.pack(side=tk.RIGHT)
        cancel = self.button(btns, 'Cancel', self.cancel_confirm)
        cancel.ring.pack(side=tk.RIGHT, padx=(0, self.px(4)))
        self.paint(tk.Label(btns, text='Enter to continue  ·  Esc to cancel', font=self.f_caption),
                   bg='bg', fg='text2').pack(side=tk.LEFT)
        go.focus_set()
        self.sync_controls()

    def on_escape(self, _event=None):
        if self.phase == 'confirm':
            self.cancel_confirm()

    def sync_controls(self):
        """Enable controls only when they can do something."""
        ready = self.phase == 'idle' and bool(self.versions)
        self.target_combo.config(state='readonly' if ready else tk.DISABLED)
        self.convert_btn.config(state=tk.NORMAL if ready else tk.DISABLED)
        self.zone.config(cursor='' if self.is_working() else 'hand2')
        target = self.selected_target() if self.versions else None
        if target and self.input_file:
            text = f'Saves {Path(self.output_path(target)).name} next to the original.'
        elif self.input_file and self.is_working():
            text = 'Target versions appear once the project has been read.'
        elif self.input_file:
            text = 'This project could not be read. Open another file to continue.'
        else:
            text = 'Open a project to choose a target version.'
        self.output_label.configure(text=text)
        self.draw_zone()

    def on_target_changed(self, _event=None):
        self.target_combo.selection_clear()
        if self.message:
            self.show_hint()
        self.sync_controls()

    def set_details(self, show):
        self.details_open = show
        self.details_btn.configure(text='Hide details' if show else 'Show details')
        if show:
            self.log_frame.pack(fill=tk.BOTH, expand=True, pady=(self.px(8), 0))
        else:
            self.log_frame.pack_forget()

    # ------------------------------------------------------------------
    # Input
    # ------------------------------------------------------------------
    def on_drop(self, event):
        """Handle drag-drop."""
        self.set_zone(drag=False)
        if self.is_working():
            return event.action
        try:
            files = self.root.tk.splitlist(event.data)
            if files:
                self.load_file(files[0])
        except Exception as e:
            self.log(f"Drop error: {e}")
        return event.action

    def browse_file(self):
        """Open file dialog."""
        if self.is_working():
            return
        path = filedialog.askopenfilename(
            parent=self.root, title='Open a Painter project',
            filetypes=[('Painter projects', '*.spp;*.uspp')]
        )
        if path:
            self.load_file(os.path.normpath(path))

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
        if self.phase == 'busy' and not messagebox.askyesno(
                'SPP Downgrader', 'A conversion is still running. Quit anyway?',
                icon=messagebox.WARNING, parent=self.root):
            return
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
