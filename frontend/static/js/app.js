/**
 * OpenBMC AI-BDD Portal — Frontend Application Logic
 * v2: QEMU structured launch, preset management, command preview,
 *     async WebSocket streaming, Robot suite execution, report display.
 */

// ── API helper ───────────────────────────────────────────────────────────────

const API = {
  base: window.location.origin,
  get:  (path)        => fetch(`${API.base}${path}`).then(r => r.json()),
  post: (path, body)  => fetch(`${API.base}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body ?? {}),
  }).then(r => r.json()),
};

// ── Toast ─────────────────────────────────────────────────────────────────────

function showToast(msg, type = 'info') {
  const el = document.createElement('div');
  el.className = `toast toast--${type}`;
  el.textContent = msg;
  document.getElementById('toast-container').appendChild(el);
  setTimeout(() => el.remove(), 4200);
}

// ── Backend health ────────────────────────────────────────────────────────────

async function checkBackendHealth() {
  const pill = document.getElementById('backend-status');
  try {
    await API.get('/health');
    pill.querySelector('.dot').className = 'dot dot--ok';
    pill.querySelector('.label').textContent = 'Backend ✓';
  } catch {
    pill.querySelector('.dot').className = 'dot dot--stopped';
    pill.querySelector('.label').textContent = 'Backend ✗';
  }
}

// ── Preset management ─────────────────────────────────────────────────────────

let _presets = [];

async function loadPresets() {
  try {
    const data = await API.get('/api/qemu/presets');
    _presets = data.presets ?? [];
    const row = document.getElementById('preset-btn-row');
    if (!_presets.length) {
      row.innerHTML = '<span style="font-size:0.8rem;color:var(--text-muted)">No presets available</span>';
      return;
    }
    row.innerHTML = _presets.map(p => `
      <button class="btn btn--preset" onclick="applyPreset('${p.id}')" title="${p.label}">
        ⚡ ${p.label}
      </button>
    `).join('');
  } catch {
    document.getElementById('preset-btn-row').innerHTML =
      '<span style="font-size:0.8rem;color:var(--text-muted)">Failed to load presets</span>';
  }
}

function applyPreset(presetId) {
  const p = _presets.find(x => x.id === presetId);
  if (!p) return;

  document.getElementById('qemu-binary').value      = p.binary     ?? '';
  document.getElementById('qemu-machine').value     = p.machine    ?? '';
  document.getElementById('qemu-memory').value      = p.memory     ?? '1G';
  document.getElementById('qemu-extra-args').value  = p.extra_args ?? '';

  // Pre-select image (symlink name) if it exists in the dropdown
  if (p.image) {
    const sel = document.getElementById('qemu-image');
    const opt = [...sel.options].find(o => o.value === p.image);
    if (opt) sel.value = p.image;
  }

  // Fill port numbers from preset
  if (p.host_ssh_port)   document.getElementById('port-ssh').value   = p.host_ssh_port;
  if (p.host_https_port) document.getElementById('port-https').value = p.host_https_port;
  if (p.host_ipmi_port)  document.getElementById('port-ipmi').value  = p.host_ipmi_port;

  showToast(`Preset "${p.label}" applied`, 'info');
  previewCommand();   // auto-refresh command preview
}

// ── QEMU Image list ───────────────────────────────────────────────────────────

async function refreshQemuImages() {
  try {
    const data = await API.get('/api/qemu/images');
    const sel  = document.getElementById('qemu-image');
    sel.innerHTML = '';
    if (!data.images?.length) {
      sel.innerHTML = '<option value="">-- no images found --</option>';
      return;
    }
    data.images.forEach(img => {
      const opt = document.createElement('option');
      opt.value = img;
      opt.textContent = img;
      sel.appendChild(opt);
    });
  } catch {
    showToast('Failed to load QEMU images', 'error');
  }
}

// ── Command preview ───────────────────────────────────────────────────────────

// Expose as a globally callable debounce shorthand (used by oninput="debouncePreview()")
function debouncePreview() {
  clearTimeout(_previewTimer);
  _previewTimer = setTimeout(previewCommand, 500);
}

async function previewCommand() {
  const image = document.getElementById('qemu-image').value;
  if (!image) {
    document.getElementById('qemu-cmd-preview').textContent =
      '# Select a firmware image first';
    return;
  }

  const body = {
    machine:              document.getElementById('qemu-machine').value,
    memory:               document.getElementById('qemu-memory').value || '1G',
    image,
    binary:               document.getElementById('qemu-binary').value || null,
    extra_args:           document.getElementById('qemu-extra-args').value,
    use_nic:              document.getElementById('qemu-use-nic').checked,
    host_ssh_port:        parseInt(document.getElementById('port-ssh').value)   || 2222,
    host_https_port:      parseInt(document.getElementById('port-https').value) || 2443,
    host_ipmi_port:       parseInt(document.getElementById('port-ipmi').value)  || 2623,
    use_docker:           document.getElementById('qemu-use-docker').checked,
    docker_image:         document.getElementById('docker-image').value || 'crops/poky:ubuntu-22.04',
    docker_container_name: 'qemu-portal-session',
  };

  try {
    const data = await API.post('/api/qemu/build-command', body);
    document.getElementById('qemu-cmd-preview').textContent = data.command ?? '# error';
  } catch (e) {
    document.getElementById('qemu-cmd-preview').textContent = `# Error: ${e}`;
  }
}

// ── QEMU Status ───────────────────────────────────────────────────────────────

async function refreshQemuStatus() {
  try {
    const data = await API.get('/api/qemu/status');
    const running = !!data.running;

    // Nav dot
    document.querySelector('#qemu-status-nav .dot').className =
      `dot ${running ? 'dot--running' : 'dot--stopped'}`;

    // Panel badge
    document.querySelector('#qemu-status .dot').className =
      `dot ${running ? 'dot--running' : 'dot--stopped'}`;
    document.getElementById('qemu-status-text').textContent =
      running ? `執行中 (PID ${data.pid})` : '已停止';

    // Buttons
    document.getElementById('btn-start-qemu').disabled = running;
    document.getElementById('btn-stop-qemu').disabled  = !running;

    // Auto-connect WS when running and not already connected
    if (running && !_qemuWs) connectQemuLogs();
    if (!running && _qemuWs) {
      _qemuWs.close();
      _qemuWs = null;
    }
  } catch { /* ignore */ }
}

// ── NIC port group toggle ─────────────────────────────────────────────────────

function toggleNicPorts(checked) {
  document.getElementById('nic-port-group')
    .classList.toggle('collapsed', !checked);
  previewCommand();
}

function toggleDockerInput(checked) {
  document.getElementById('docker-image-group')
    .classList.toggle('collapsed', !checked);
}

// ── QEMU Launch ───────────────────────────────────────────────────────────────

async function launchQemu() {
  const image = document.getElementById('qemu-image').value;
  if (!image) { showToast('Please select a firmware image', 'error'); return; }

  const body = {
    machine:              document.getElementById('qemu-machine').value,
    memory:               document.getElementById('qemu-memory').value   || '1G',
    image,
    binary:               document.getElementById('qemu-binary').value   || null,
    extra_args:           document.getElementById('qemu-extra-args').value,
    use_nic:              document.getElementById('qemu-use-nic').checked,
    dry_run:              document.getElementById('qemu-dry-run').checked,
    host_ssh_port:        parseInt(document.getElementById('port-ssh').value)   || 2222,
    host_https_port:      parseInt(document.getElementById('port-https').value) || 2443,
    host_ipmi_port:       parseInt(document.getElementById('port-ipmi').value)  || 2623,
    use_docker:           document.getElementById('qemu-use-docker').checked,
    docker_image:         document.getElementById('docker-image').value || 'crops/poky:ubuntu-22.04',
    docker_container_name: 'qemu-portal-session',
  };

  const isDryRun = body.dry_run;
  showToast(isDryRun ? 'Dry-run: building command...' : 'Launching QEMU…', 'info');

  try {
    const data = await API.post('/api/qemu/launch', body);

    if (data.ok) {
      if (isDryRun) {
        // Show assembled command in preview + toast
        document.getElementById('qemu-cmd-preview').textContent = data.command;
        showToast('Dry-run complete — see command preview above', 'success');
        appendLog(`[DRY-RUN] ${data.command}\n`);
      } else {
        showToast(`QEMU launched (PID ${data.pid})`, 'success');
        appendLog(`[LAUNCH] ${data.command}\n`);
        connectQemuLogs();
      }
    } else {
      showToast(`Error: ${data.error}`, 'error');
      appendLog(`[ERROR] ${data.error}\n`);
    }
  } catch (e) {
    showToast('Failed to contact backend', 'error');
  }

  await refreshQemuStatus();
}

// ── QEMU Stop ─────────────────────────────────────────────────────────────────

async function stopQemu() {
  showToast('Stopping QEMU…', 'info');
  try {
    const data = await API.post('/api/qemu/stop');
    if (data.ok) {
      showToast('QEMU stopped', 'success');
      appendLog('[STOPPED] QEMU process terminated\n');
    } else {
      showToast(`Error: ${data.error}`, 'error');
    }
  } catch { showToast('Failed to contact backend', 'error'); }
  await refreshQemuStatus();
}

// ── WebSocket log streaming (Bidirectional Interactive Terminal) ───────────────

let _qemuWs = null;
let term = null;

function _setWsBadge(state) {
  const badge = document.getElementById('ws-status-badge');
  if (!badge) return;
  badge.className = `ws-badge ws-badge--${state}`;
  badge.textContent = { on: 'WS ON', off: 'WS OFF', connecting: 'WS …' }[state] ?? 'WS';
}

function initTerminal() {
  const termContainer = document.getElementById('qemu-terminal');
  if (!termContainer || term) return;

  // Initialize a beautiful interactive terminal window matching retro style
  term = new Terminal({
    cursorBlink: true,
    cursorStyle: 'block',
    convertEol: true,
    theme: {
      background: '#0f1419',
      foreground: '#e6b450',
      cursor: '#f29718',
      black: '#000000',
      red: '#ff3333',
      green: '#33cc33',
      yellow: '#f29718',
      blue: '#3399ff',
      magenta: '#cc66ff',
      cyan: '#33ffff',
      white: '#ffffff'
    },
    fontFamily: 'JetBrains Mono, monospace',
    fontSize: 13,
    lineHeight: 1.2
  });

  term.open(termContainer);
  term.writeln('\x1b[33m# Waiting for QEMU to start...\x1b[0m');

  // Bidirectional typing: capture keyboard strokes and send straight to QEMU stdin
  term.onData(data => {
    if (_qemuWs && _qemuWs.readyState === WebSocket.OPEN) {
      _qemuWs.send(data);
    }
  });
}

function connectQemuLogs() {
  if (_qemuWs) return;
  initTerminal();

  const wsUrl = `ws://${window.location.host}/api/qemu/ws/logs`;
  _setWsBadge('connecting');
  _qemuWs = new WebSocket(wsUrl);

  _qemuWs.onopen = () => {
    _setWsBadge('on');
    term.write('\r\n\x1b[32m[WebSocket] Connected to QEMU serial console\x1b[0m\r\n');
  };

  _qemuWs.onmessage = e => {
    // Write stdout to terminal screen
    term.write(e.data);
  };

  _qemuWs.onclose = () => {
    _setWsBadge('off');
    term.write('\r\n\x1b[31m[WebSocket] Disconnected\x1b[0m\r\n');
    _qemuWs = null;
  };

  _qemuWs.onerror = () => {
    _setWsBadge('off');
    term.write('\r\n\x1b[31m[WebSocket] Connection error\x1b[0m\r\n');
    _qemuWs = null;
  };
}

function appendLog(text) {
  initTerminal();
  if (term) {
    // Normalise newlines to CRLF for correct term alignment
    term.write(text.replace(/\r?\n/g, '\r\n'));
  }
}

function clearLog() {
  if (term) {
    term.clear();
  }
}

// ── Robot Framework ───────────────────────────────────────────────────────────

let _selectedSuite = null;

async function loadSuites() {
  try {
    const data = await API.get('/api/robot/suites');
    const list  = document.getElementById('robot-suite-list');
    document.getElementById('suite-count').textContent = data.suites.length;

    if (!data.suites?.length) {
      list.innerHTML = '<div class="suite-empty">No .robot suites found in configured directory.</div>';
      return;
    }
    list.innerHTML = data.suites.map((s, i) => `
      <label class="suite-item" id="suite-${i}">
        <input type="radio" name="suite" value="${s.path}"
               onchange="selectSuite('${s.path}', 'suite-${i}')" />
        <div>
          <div class="suite-name">${s.name}</div>
          <div class="suite-path">${s.path}</div>
        </div>
      </label>
    `).join('');
  } catch {
    showToast('Failed to load Robot suites', 'error');
  }
}

function selectSuite(path, itemId) {
  _selectedSuite = path;
  document.querySelectorAll('.suite-item').forEach(el => el.classList.remove('active'));
  document.getElementById(itemId)?.classList.add('active');
}

async function runRobotSuite() {
  if (!_selectedSuite) { showToast('Please select a test suite first', 'error'); return; }

  const varsRaw   = document.getElementById('robot-extra-vars').value.trim();
  const extraVars = {};
  if (varsRaw) {
    varsRaw.split('\n').forEach(line => {
      const [k, ...rest] = line.split(':');
      if (k?.trim()) extraVars[k.trim()] = rest.join(':').trim();
    });
  }

  const statusEl = document.getElementById('robot-run-status');
  const runBtn   = document.getElementById('btn-run-robot');
  statusEl.hidden = false;
  runBtn.disabled = true;
  showToast(`Running: ${_selectedSuite}`, 'info');

  try {
    const data = await API.post('/api/robot/run', {
      suite_path: _selectedSuite,
      extra_vars: extraVars,
    });
    if (data.ok) {
      showToast('Test suite completed ✓', 'success');
    } else {
      showToast(`Suite failed (rc=${data.returncode})`, 'error');
    }
    await loadReports();
  } catch {
    showToast('Failed to run Robot suite', 'error');
  } finally {
    statusEl.hidden = true;
    runBtn.disabled = false;
  }
}

// ── Reports ───────────────────────────────────────────────────────────────────

async function loadReports() {
  try {
    const data = await API.get('/api/robot/reports');
    const list  = document.getElementById('report-list');

    if (!data.reports?.length) {
      list.innerHTML = '<div class="report-empty">No reports yet. Run a test suite to generate reports.</div>';
      return;
    }
    list.innerHTML = data.reports.map(r => `
      <div class="report-card">
        <div class="report-card-header">
          <span class="report-name">📄 ${r.name}</span>
          <span class="report-timestamp">${r.modified}</span>
        </div>
        <div class="report-actions">
          <a href="/reports/${encodeURIComponent(r.report_path)}" target="_blank"
             class="btn btn--ghost btn--sm report-link">🌐 HTML Report</a>
          <a href="/reports/${encodeURIComponent(r.log_path)}" target="_blank"
             class="btn btn--ghost btn--sm report-link">📋 Full Log</a>
        </div>
      </div>
    `).join('');
  } catch {
    showToast('Failed to load reports', 'error');
  }
}

// ── Reactive: auto-preview when inputs change ─────────────────────────────────

function _bindAutoPreview() {
  document.getElementById('qemu-image')?.addEventListener('change', previewCommand);
  document.getElementById('qemu-machine')?.addEventListener('input', debouncePreview);
  document.getElementById('qemu-extra-args')?.addEventListener('input', debouncePreview);
  document.getElementById('qemu-memory')?.addEventListener('input', debouncePreview);
  document.getElementById('qemu-use-nic')?.addEventListener('change', previewCommand);
  // Port fields already use oninput="debouncePreview()" in HTML
}

let _previewTimer = null;

// ── Init ──────────────────────────────────────────────────────────────────────

async function init() {
  initTerminal();
  await checkBackendHealth();
  await Promise.all([
    loadPresets(),
    refreshQemuImages(),
    refreshQemuStatus(),
    loadSuites(),
    loadReports(),
  ]);
  _bindAutoPreview();

  setInterval(refreshQemuStatus,   5000);
  setInterval(checkBackendHealth, 30000);
}

document.addEventListener('DOMContentLoaded', init);
