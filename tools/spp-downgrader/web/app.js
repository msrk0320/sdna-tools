// SPP Downgrader Web App
// Client-side gate using Google Identity Services. This is NOT a security boundary,
// just a way to keep casual visitors out of an internal tool.

const fallbackVersions = ['12.1', '12', '11', '10', '9', '8.1'];
let state = {
  input: null,
  uspp: null,
  sourceVersion: null,
  targetVersion: null,
  worker: null,
  busy: false
};

// ========== Auth Gate ==========
async function initAuth() {
  const config = window.SDNA_CONFIG || {};
  const clientId = config.googleClientId || '';
  const domain = config.allowedDomain || 'example.com';
  const isLocalhost = location.hostname === 'localhost' || location.hostname === '127.0.0.1';

  const authArea = document.getElementById('auth-area');
  const toolArea = document.getElementById('tool-area');
  const devBanner = document.getElementById('dev-banner');

  // Check sessionStorage for existing token
  let token = null;
  try {
    const stored = sessionStorage.getItem('sdna_auth');
    if (stored) {
      const parsed = JSON.parse(stored);
      if (parsed.exp * 1000 > Date.now()) {
        token = parsed;
      } else {
        sessionStorage.removeItem('sdna_auth');
      }
    }
  } catch (e) {}

  if (!clientId) {
    if (isLocalhost) {
      devBanner.style.display = 'block';
      toolArea.style.display = 'block';
      authArea.style.display = 'none';
      initWorker();
      return;
    } else {
      authArea.innerHTML = '<p style="color: #c00; padding: 16px;">Sign-in is not configured.</p>';
      toolArea.style.display = 'none';
      return;
    }
  }

  if (token) {
    // User already authenticated
    showAuthStatus(token.email);
    toolArea.style.display = 'block';
    authArea.style.display = 'block';
    initWorker();
    return;
  }

  // Show Google sign-in button
  authArea.style.display = 'block';
  toolArea.style.display = 'none';

  window.onGoogleSignIn = (response) => {
    const payload = parseJwt(response.credential);
    const email = payload.email || '';
    const hd = payload.hd || '';
    const verified = payload.email_verified || false;

    if (!verified || hd !== domain || !email.toLowerCase().endsWith('@' + domain)) {
      authArea.innerHTML = `<p style="color: #c00; padding: 16px;">Only @${domain} accounts can use this tool.</p>`;
      google.accounts.id.disableAutoSelect();
      return;
    }

    try {
      sessionStorage.setItem('sdna_auth', JSON.stringify({email, exp: payload.exp}));
    } catch (e) {}

    showAuthStatus(email);
    toolArea.style.display = 'block';
    initWorker();
  };

  google.accounts.id.initialize({
    client_id: clientId,
    callback: window.onGoogleSignIn,
    hd: domain,
    auto_select: true
  });

  const buttonDiv = document.getElementById('google-signin-button');
  if (buttonDiv) {
    google.accounts.id.renderButton(buttonDiv, {theme: 'outline', size: 'large'});
  }
}

function parseJwt(token) {
  const base64Url = token.split('.')[1];
  const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
  const jsonPayload = decodeURIComponent(atob(base64).split('').map(c => '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2)).join(''));
  return JSON.parse(jsonPayload);
}

function showAuthStatus(email) {
  const authArea = document.getElementById('auth-area');
  const signout = () => {
    try {
      sessionStorage.removeItem('sdna_auth');
    } catch (e) {}
    google.accounts.id.disableAutoSelect();
    location.reload();
  };
  authArea.innerHTML = `
    <div style="padding: 12px; background: var(--bg-secondary); border-radius: 4px;">
      Signed in as <strong>${escapeHtml(email)}</strong>
      <a href="javascript:void(0)" onclick="(${signout.toString()})(); return false;" style="margin-left: 16px;">Sign out</a>
    </div>
  `;
}

// ========== Worker Communication ==========
function initWorker() {
  state.worker = new Worker('worker.js');
  state.worker.onmessage = handleWorkerMessage;

  const logEl = document.getElementById('log');
  logEl.textContent = '';

  showStatus('Initializing converter...');
  state.worker.postMessage({type: 'init'});
}

function handleWorkerMessage(event) {
  const {id, type, ok, error, text, result, path, data} = event.data;

  if (type === 'status') {
    showStatus(text);
  } else if (type === 'init') {
    state.ready = ok;
    showStatus(ok ? 'Ready. Drop a .spp or .uspp file.' : `Converter failed to load: ${error}`);
  } else if (id !== null && id !== undefined) {
    const callback = window.workerCallbacks && window.workerCallbacks[id];
    if (callback) {
      delete window.workerCallbacks[id];
      callback(ok, error || (ok ? result : null));
    }
  }
}

let callbackId = 0;
function workerCall(type, payload, callback) {
  if (!state.worker) {
    callback(false, 'Worker not initialized');
    return;
  }
  const id = ++callbackId;
  window.workerCallbacks = window.workerCallbacks || {};
  window.workerCallbacks[id] = callback;
  state.worker.postMessage({id, type, ...payload});
}

function showStatus(text) {
  document.getElementById('status').textContent = text;
}

// ========== UI Helpers ==========
function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

function log(text) {
  const logEl = document.getElementById('log');
  const line = document.createTextNode(text + '\n');
  logEl.appendChild(line);
  logEl.scrollTop = logEl.scrollHeight;
}

function setBusy(busy) {
  state.busy = busy;
  const dropZone = document.getElementById('drop-zone');
  const selectEl = document.getElementById('target-version');
  const convertBtn = document.getElementById('convert-btn');

  dropZone.style.opacity = busy ? '0.5' : '1';
  dropZone.style.pointerEvents = busy ? 'none' : 'auto';
  selectEl.disabled = busy || selectEl.options.length === 0;
  convertBtn.disabled = busy || selectEl.options.length === 0;
}

// ========== File Handling ==========
function setupDropZone() {
  const dropZone = document.getElementById('drop-zone');

  dropZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropZone.style.borderColor = 'var(--accent-color)';
    dropZone.style.backgroundColor = 'var(--bg-secondary)';
  });

  dropZone.addEventListener('dragleave', () => {
    dropZone.style.borderColor = '';
    dropZone.style.backgroundColor = '';
  });

  dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropZone.style.borderColor = '';
    dropZone.style.backgroundColor = '';

    const files = e.dataTransfer.files;
    if (files.length > 0) {
      loadFile(files[0]);
    }
  });

  dropZone.addEventListener('click', () => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.spp,.uspp';
    input.onchange = (e) => {
      if (e.target.files.length > 0) {
        loadFile(e.target.files[0]);
      }
    };
    input.click();
  });
}

function loadFile(file) {
  const ext = file.name.toLowerCase().endsWith('.spp') ? '.spp' :
              file.name.toLowerCase().endsWith('.uspp') ? '.uspp' : null;

  if (!ext) {
    log(`Not a .spp or .uspp: ${file.name}`);
    return;
  }
  if (!state.ready) {
    log('The converter is still loading. Try again in a moment.');
    return;
  }

  state.input = file;
  state.uspp = null;
  state.sourceVersion = null;
  document.getElementById('target-version').innerHTML = '';
  document.getElementById('source-version').textContent = 'Source version: -';
  document.getElementById('log').textContent = '';
  document.getElementById('drop-zone').textContent = file.name;

  log(`Loaded ${file.name}`);
  setBusy(true);

  const reader = new FileReader();
  reader.onload = (e) => {
    const bytes = e.target.result;
    if (ext === '.uspp') {
      workerCall('load', {name: file.name, bytes}, (ok, result) => {
        if (!ok) {
          log(`Load failed: ${result}`);
          setBusy(false);
          return;
        }
        state.uspp = result;
        readInfo(result);
      });
    } else {
      // Pack .spp to temp .uspp
      log('Reading project (packing to temporary .uspp)...');
      workerCall('load', {name: file.name, bytes}, (ok, result) => {
        if (!ok) {
          log(`Load failed: ${result}`);
          setBusy(false);
          return;
        }
        const packArgs = ['pack', result, '-o', '/work/src.uspp'];
        workerCall('run', {args: packArgs}, (ok, result) => {
          if (!ok) {
            log(`Pack failed: ${result}`);
            setBusy(false);
            return;
          }
          const [code, out, err] = result;
          if (code !== 0) {
            log(`Pack failed (exit ${code}):\n${err}`);
            setBusy(false);
            return;
          }
          state.uspp = '/work/src.uspp';
          readInfo(state.uspp);
        });
      });
    }
  };
  reader.readAsArrayBuffer(file);
}

function readInfo(usppPath) {
  const infoArgs = ['info', '--uspp', usppPath];
  workerCall('run', {args: infoArgs}, (ok, result) => {
    if (!ok) {
      log(`Read failed: ${result}`);
      setBusy(false);
      return;
    }
    const [code, out, err] = result;
    if (code !== 0) {
      log(`Could not read file (exit ${code}):\n${err}`);
      setBusy(false);
      return;
    }

    let info;
    try {
      info = JSON.parse(out);
    } catch (e) {
      log(`Invalid response:\n${out}`);
      setBusy(false);
      return;
    }

    state.sourceVersion = info.created_version;
    if (!state.sourceVersion) {
      log('File has no source version; cannot convert.');
      setBusy(false);
      return;
    }

    document.getElementById('source-version').textContent = `Source version: ${state.sourceVersion}`;

    const versions = info.supported_versions && info.supported_versions.length > 0
      ? info.supported_versions
      : fallbackVersions;

    const selectEl = document.getElementById('target-version');
    selectEl.innerHTML = '';
    versions.forEach(v => {
      const opt = document.createElement('option');
      opt.value = v;
      opt.textContent = v;
      selectEl.appendChild(opt);
    });

    // Default to next version below source (index 1 if available)
    selectEl.selectedIndex = Math.min(1, selectEl.options.length - 1);

    log(`Source is Painter ${state.sourceVersion}. Pick a target and click Convert.`);
    setBusy(false);
  });
}

// ========== Convert Flow ==========
function startConvert() {
  const selectEl = document.getElementById('target-version');
  const target = selectEl.options[selectEl.selectedIndex]?.value;

  if (!target) return;

  state.targetVersion = target;
  setBusy(true);
  log(`\nChecking v${state.sourceVersion} -> v${target}...`);

  const planArgs = ['plan', '--uspp', state.uspp, '--target', target];
  workerCall('run', {args: planArgs}, (ok, result) => {
    if (!ok) {
      log(`Plan failed: ${result}`);
      setBusy(false);
      return;
    }

    const [code, out, err] = result;
    if (code !== 0) {
      log(`Plan failed (exit ${code}):\n${err}`);
      setBusy(false);
      return;
    }

    let plan;
    try {
      plan = JSON.parse(out);
    } catch (e) {
      log(`Invalid plan response:\n${out}`);
      setBusy(false);
      return;
    }

    if (!plan.supported) {
      log(`No conversion path from v${plan.source_version} to v${target}.`);
      setBusy(false);
      return;
    }

    if (plan.lossy) {
      showLossyConfirm(plan, target);
    } else {
      startBuild(target);
    }
  });
}

function showLossyConfirm(plan, target) {
  const panel = document.getElementById('lossy-confirm-panel');
  const content = document.getElementById('lossy-confirm-content');
  const continueBtn = document.getElementById('lossy-continue-btn');
  const cancelBtn = document.getElementById('lossy-cancel-btn');

  let lines = [];
  if (plan.lost_features && Array.isArray(plan.lost_features)) {
    plan.lost_features.forEach(f => {
      if (typeof f === 'string') {
        lines.push('- ' + f);
      } else {
        lines.push('- ' + JSON.stringify(f));
      }
    });
  }

  if (plan.missing_raster_fallbacks && Array.isArray(plan.missing_raster_fallbacks)) {
    const unique = new Set();
    plan.missing_raster_fallbacks.forEach(r => {
      const line = `- ${r.dataset}: ${r.reason}`;
      unique.add(line);
    });
    lines.push(...unique);
  }

  const shown = lines.slice(0, 25).join('\n');
  const more = lines.length > 25 ? `\n...and ${lines.length - 25} more` : '';

  content.textContent = `This downgrade is lossy:\n\n${shown}${more}\n\nContinue? The original file is not changed.`;
  panel.style.display = 'block';

  continueBtn.onclick = () => {
    panel.style.display = 'none';
    startBuild(target);
  };

  cancelBtn.onclick = () => {
    panel.style.display = 'none';
    log('Cancelled.');
    setBusy(false);
  };
}

function startBuild(target) {
  if (document.getElementById('lossy-confirm-panel').style.display !== 'none') {
    return;
  }

  const inputName = state.input.name;
  const baseName = inputName.substring(0, inputName.lastIndexOf('.'));
  const outPath = `/work/out.spp`;

  log(`Building ${baseName}_v${target}.spp...`);
  const startTime = Date.now();

  const buildArgs = ['build', '--uspp', state.uspp, '--target', target, '-o', outPath];
  workerCall('run', {args: buildArgs}, (ok, result) => {
    if (!ok) {
      log(`Build failed: ${result}`);
      setBusy(false);
      return;
    }

    const [code, out, err] = result;
    const elapsed = Math.round((Date.now() - startTime) / 1000);

    if (out.trim()) {
      log(out.trim());
    }

    if (code !== 0) {
      log(`Build failed (exit ${code}):\n${err}`);
      if (err.includes("No module named 'lz4'") || err.includes("No module named 'pyspng'")) {
        log('\nNote: This .uspp contains raster fallbacks, which the web version cannot process yet. Use the desktop tool.');
      }
      setBusy(false);
      return;
    }

    log(`Done in ${elapsed}s. Close Painter fully before opening the new file.`);

    // Read the output file
    workerCall('read', {path: outPath}, (ok, result) => {
      if (!ok) {
        log(`Read output failed: ${result}`);
        setBusy(false);
        return;
      }

      const data = new Uint8Array(result);
      const blob = new Blob([data], {type: 'application/octet-stream'});
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${baseName}_v${target}.spp`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      setTimeout(() => URL.revokeObjectURL(url), 60000);

      setBusy(false);
    });
  });
}

// ========== Init ==========
window.addEventListener('DOMContentLoaded', () => {
  setupDropZone();
  initAuth();

  document.getElementById('convert-btn').onclick = startConvert;
});
