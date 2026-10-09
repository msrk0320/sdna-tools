// Web Worker for running SPP Downgrader engine via Pyodide
importScripts('https://cdn.jsdelivr.net/pyodide/v0.27.7/full/pyodide.js');

let pyodide = null;

async function init() {
  try {
    self.postMessage({type: 'status', text: 'Loading Python...'});
    pyodide = await loadPyodide();

    self.postMessage({type: 'status', text: 'Loading libraries (numpy, h5py, pyyaml, mmh3)...'});
    await pyodide.loadPackage(['numpy', 'h5py', 'pyyaml', 'mmh3']);

    self.postMessage({type: 'status', text: 'Loading converter engine...'});

    // Fetch and unpack engine.zip
    const response = await fetch('engine.zip');
    const buf = await response.arrayBuffer();
    pyodide.FS.mkdirTree('/engine');
    await pyodide.unpackArchive(buf, 'zip', {extractDir: '/engine'});

    // Define run_tool function in Python
    const code = `
import sys, io, runpy, contextlib
sys.path.insert(0, '/engine')

def run_tool(args):
    out, err = io.StringIO(), io.StringIO()
    sys.argv = ['uspp_tool.py'] + list(args)
    code = 0
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            runpy.run_path('/engine/uspp_tool.py', run_name='__main__')
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
        except Exception:
            import traceback
            traceback.print_exc()
            code = 1
    return [code, out.getvalue(), err.getvalue()]
`;
    await pyodide.runPythonAsync(code);

    self.postMessage({id: null, type: 'init', ok: true});
  } catch (err) {
    self.postMessage({id: null, type: 'init', ok: false, error: err.message});
  }
}

self.onmessage = async (event) => {
  const {id, type, name, bytes, args, path} = event.data;

  if (type === 'init') {
    await init();
  } else if (type === 'load') {
    try {
      // Clear previous files in /work
      pyodide.FS.mkdirTree('/work');
      const ws = pyodide.FS.readdir('/work');
      for (const f of ws) {
        if (f !== '.' && f !== '..') {
          try {
            pyodide.FS.unlink('/work/' + f);
          } catch (e) {}
        }
      }

      pyodide.FS.writeFile('/work/' + name, new Uint8Array(bytes));
      self.postMessage({id, ok: true, result: '/work/' + name});
    } catch (err) {
      self.postMessage({id, ok: false, error: err.message});
    }
  } else if (type === 'run') {
    try {
      // run_tool returns a PyProxy; convert to a plain array before posting
      const proxy = pyodide.globals.get('run_tool')(args);
      const result = proxy.toJs();
      proxy.destroy();
      self.postMessage({id, ok: true, result});
    } catch (err) {
      self.postMessage({id, ok: false, error: err.message});
    }
  } else if (type === 'read') {
    try {
      const data = pyodide.FS.readFile(path);
      pyodide.FS.unlink(path);
      self.postMessage({id, ok: true, result: data.buffer}, [data.buffer]);
    } catch (err) {
      self.postMessage({id, ok: false, error: err.message});
    }
  }
};
