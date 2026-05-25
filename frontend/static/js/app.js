/**
 * OpenBMC AI-BDD Portal — Frontend Application Logic
 * v3: Tab-based page navigation, CI preset suites, categorized test browser.
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

// ── Page navigation ───────────────────────────────────────────────────────────

const _PAGE_IDS = ['qemu', 'robot', 'reports'];

function showPage(name) {
  _PAGE_IDS.forEach(id => {
    const page = document.getElementById(`page-${id}`);
    const tab  = document.getElementById(`ptab-${id}`);
    if (!page || !tab) return;
    const isActive = id === name;
    page.classList.toggle('page--active', isActive);
    tab.classList.toggle('active', isActive);
    tab.setAttribute('aria-selected', String(isActive));
  });

  // Lazy-load reports when tab is first opened
  if (name === 'reports') loadReports();
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

  if (p.image) {
    const sel = document.getElementById('qemu-image');
    const opt = [...sel.options].find(o => o.value === p.image);
    if (opt) sel.value = p.image;
  }

  if (p.host_ssh_port)   document.getElementById('port-ssh').value   = p.host_ssh_port;
  if (p.host_https_port) document.getElementById('port-https').value = p.host_https_port;
  if (p.host_ipmi_port)  document.getElementById('port-ipmi').value  = p.host_ipmi_port;

  if (p.use_docker !== undefined) {
    const cb = document.getElementById('use-docker');
    if (cb) {
      cb.checked = p.use_docker;
      cb.dispatchEvent(new Event('change'));
    }
  }

  showToast(`Preset "${p.label}" applied`, 'info');
  previewCommand();
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

function debouncePreview() {
  clearTimeout(_previewTimer);
  _previewTimer = setTimeout(previewCommand, 500);
}

function _copyTextToClipboard(text, btn, label = '複製') {
  const markCopied = () => {
    btn.textContent = '已複製 ✓';
    setTimeout(() => { btn.textContent = label; }, 2000);
  };
  // Try execCommand first — must be synchronous (works on HTTP)
  const ta = document.createElement('textarea');
  ta.value = text;
  ta.style.cssText = 'position:fixed;top:0;left:0;opacity:0;pointer-events:none';
  document.body.appendChild(ta);
  ta.focus();
  ta.select();
  let ok = false;
  try { ok = document.execCommand('copy'); } catch {}
  document.body.removeChild(ta);
  if (ok) { markCopied(); return; }
  // Fallback: async clipboard API (HTTPS / localhost)
  if (navigator.clipboard) {
    navigator.clipboard.writeText(text).then(markCopied).catch(() => showToast('複製失敗', 'error'));
  } else {
    showToast('複製失敗', 'error');
  }
}

async function copyQemuCmd() {
  const pre = document.getElementById('qemu-cmd-preview');
  const btn = document.getElementById('qemu-cmd-copy-btn');
  if (!pre || !btn) return;
  try {
    await navigator.clipboard.writeText(pre.textContent);
    btn.textContent = '已複製 ✓';
    setTimeout(() => { btn.textContent = '複製'; }, 2000);
  } catch {
    showToast('複製失敗', 'error');
  }
}

function copyRobotCmd() {
  const pre = document.getElementById('robot-log-cmd-preview');
  const btn = document.getElementById('robot-cmd-copy-btn-log');
  if (!pre || !btn) return;
  _copyTextToClipboard(pre.textContent, btn);
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
    document.getElementById('qemu-cmd-preview').textContent = _formatQemuCmd(data.command ?? '# error');
  } catch (e) {
    document.getElementById('qemu-cmd-preview').textContent = `# Error: ${e}`;
  }
}

// ── QEMU Status ───────────────────────────────────────────────────────────────

async function refreshQemuStatus() {
  try {
    const data = await API.get('/api/qemu/status');
    const running = !!data.running;

    document.querySelector('#qemu-status-nav .dot').className =
      `dot ${running ? 'dot--running' : 'dot--stopped'}`;
    document.querySelector('#qemu-status .dot').className =
      `dot ${running ? 'dot--running' : 'dot--stopped'}`;
    document.getElementById('qemu-status-text').textContent =
      running ? `執行中 (PID ${data.pid})` : '已停止';

    document.getElementById('btn-start-qemu').disabled = running;
    document.getElementById('btn-stop-qemu').disabled  = !running;

    if (running && !_qemuWs) connectQemuLogs();
    if (!running && _qemuWs) { _qemuWs.close(); _qemuWs = null; }
  } catch { /* ignore */ }
}

// ── NIC / Docker toggles ──────────────────────────────────────────────────────

function toggleNicPorts(checked) {
  document.getElementById('nic-port-group').classList.toggle('collapsed', !checked);
  previewCommand();
}

function toggleDockerInput(checked) {
  document.getElementById('docker-image-group').classList.toggle('collapsed', !checked);
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
        document.getElementById('qemu-cmd-preview').textContent = _formatQemuCmd(data.command);
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

// ── WebSocket log streaming (xterm.js Interactive Terminal) ──────────────────

let _qemuWs   = null;
let term       = null;
let _fitAddon  = null;

function _setWsBadge(state) {
  const badge = document.getElementById('ws-status-badge');
  if (!badge) return;
  badge.className = `ws-badge ws-badge--${state}`;
  badge.textContent = { on: 'WS ON', off: 'WS OFF', connecting: 'WS …' }[state] ?? 'WS';
}

function initTerminal() {
  const termContainer = document.getElementById('qemu-terminal');
  if (!termContainer || term) return;

  term = new Terminal({
    cursorBlink: true,
    cursorStyle: 'block',
    convertEol: true,
    theme: {
      background: '#0f1419',
      foreground: '#e6b450',
      cursor: '#f29718',
      black: '#000000', red: '#ff3333', green: '#33cc33',
      yellow: '#f29718', blue: '#3399ff', magenta: '#cc66ff',
      cyan: '#33ffff',  white: '#ffffff'
    },
    fontFamily: 'JetBrains Mono, monospace',
    fontSize: 13,
    lineHeight: 1.2,
  });

  // FitAddon: auto-size cols/rows to match the container's pixel dimensions
  if (window.FitAddon) {
    _fitAddon = new window.FitAddon.FitAddon();
    term.loadAddon(_fitAddon);
  }

  term.open(termContainer);

  if (_fitAddon) {
    _fitAddon.fit();
    // Re-fit whenever the container is resized
    new ResizeObserver(() => _fitAddon.fit()).observe(termContainer);
  }

  term.writeln('\x1b[33m# Waiting for QEMU to start...\x1b[0m');

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

  _qemuWs.onopen  = () => { _setWsBadge('on');  term.write('\r\n\x1b[32m[WebSocket] Connected\x1b[0m\r\n'); };
  _qemuWs.onmessage = e => { term.write(e.data); };
  _qemuWs.onclose = () => { _setWsBadge('off'); term.write('\r\n\x1b[31m[WebSocket] Disconnected\x1b[0m\r\n'); _qemuWs = null; };
  _qemuWs.onerror = () => { _setWsBadge('off'); term.write('\r\n\x1b[31m[WebSocket] Error\x1b[0m\r\n'); _qemuWs = null; };
}

function appendLog(text) {
  initTerminal();
  if (term) term.write(text.replace(/\r?\n/g, '\r\n'));
}

function clearLog() {
  if (term) term.clear();
}

// ═══════════════════════════════════════════════════════════════
// ROBOT FRAMEWORK — CI Presets + Categorized Browser
// ═══════════════════════════════════════════════════════════════

// ── State ─────────────────────────────────────────────────────────────────────

let _ciData          = [];   // test_lists from API
let _robotDir        = '.';  // robot_script_dir from API
let _categorizedData = [];   // categorized tests from API
let _selectedCiIncludes = new Set();   // --include tag names (for CI mode)
let _selectedSuites  = new Set();      // file paths (for browse mode — used for running)
let _selectedTests   = new Set();      // "file\0name" keys (for test-case count + panel display)
let _activeBrowseCat = null;           // active category chip filter
let _robotWs         = null;
let _currentRunId    = null;

// ── Robot Tab switching ───────────────────────────────────────────────────────

function switchRobotTab(tab) {
  ['ci', 'browse', 'log'].forEach(t => {
    document.getElementById(`robot-section-${t}`)?.classList.toggle('collapsed', t !== tab);
    document.getElementById(`tab-${t}`)?.classList.toggle('active', t === tab);
  });
  if (tab === 'log') _syncLogCmdPreview();
}

function toggleVarsSection() {
  const content = document.getElementById('robot-vars-content');
  if (!content) return;
  const collapsed = content.classList.toggle('collapsed');
  const icon = document.getElementById('vars-toggle-icon');
  if (icon) icon.textContent = collapsed ? '▶' : '▲';
}

// ── CI Preset Cards ───────────────────────────────────────────────────────────

async function loadCiCards() {
  try {
    const data = await API.get('/api/robot/test-lists');
    _ciData    = data.test_lists ?? [];
    _robotDir  = data.robot_dir  ?? '.';
    _renderCiCards();
  } catch {
    const grid = document.getElementById('ci-cards-grid');
    grid.innerHTML = '<div class="ci-card-loading">⚠ 無法載入 CI 套件</div>';
  }
}

function _buildTagCommand(tag) {
  const vars = _collectVariables();
  const parts = ['python3', '-m', 'robot'];
  for (const [k, v] of Object.entries(vars)) {
    parts.push('--variable', `${k}:${v}`);
  }
  parts.push('--include', tag);
  parts.push(_robotDir);
  return parts.join(' ');
}

function _renderCiCards() {
  const grid = document.getElementById('ci-cards-grid');
  grid.replaceChildren();

  if (!_ciData.length) {
    const msg = document.createElement('div');
    msg.className = 'ci-card-loading';
    msg.textContent = '📂 未找到 test_lists 目錄';
    grid.appendChild(msg);
    return;
  }

  for (const tl of _ciData) {
    const card = _buildCiCard(tl);
    grid.appendChild(card);
  }
}

function _buildCiCard(tl) {
  const card = document.createElement('div');
  card.className = 'ci-card';
  card.id = `ci-card-${tl.name}`;

  // Name
  const nameEl = document.createElement('div');
  nameEl.className = 'ci-card-name';
  nameEl.textContent = tl.name;
  card.appendChild(nameEl);

  // Description
  const descEl = document.createElement('div');
  descEl.className = 'ci-card-desc';
  descEl.textContent = tl.description || tl.name;
  card.appendChild(descEl);

  // Footer: count + button
  const footer = document.createElement('div');
  footer.className = 'ci-card-footer';

  const countEl = document.createElement('span');
  countEl.className = 'ci-card-count';
  const strong = document.createElement('strong');
  strong.textContent = String(tl.count);
  countEl.appendChild(strong);
  countEl.append(' 個測試標籤');
  footer.appendChild(countEl);

  const btn = document.createElement('button');
  btn.className = 'ci-card-btn';
  btn.textContent = '選取';
  btn.setAttribute('tabindex', '-1');
  footer.appendChild(btn);

  card.appendChild(footer);
  card.addEventListener('click', () => _toggleCiCard(tl, card, btn));

  // Restore selected state if already selected
  const isSelected = tl.includes.some(tag => _selectedCiIncludes.has(tag));
  if (isSelected) {
    card.classList.add('selected');
    btn.classList.add('deselect');
    btn.textContent = '已選取 ✓';
  }

  return card;
}

function _toggleCiCard(tl, card, btn) {
  const isCurrentlySelected = card.classList.contains('selected');

  if (isCurrentlySelected) {
    tl.includes.forEach(tag => _selectedCiIncludes.delete(tag));
    card.classList.remove('selected');
    btn.classList.remove('deselect');
    btn.textContent = '選取';
  } else {
    tl.includes.forEach(tag => _selectedCiIncludes.add(tag));
    card.classList.add('selected');
    btn.classList.add('deselect');
    btn.textContent = '已選取 ✓';
  }

  _updateCiSelectionBar();
  _renderCiTagCmdPanel();
}

function _renderCiTagCmdPanel() {
  const panel = document.getElementById('ci-tag-cmd-panel');
  if (!panel) return;

  // Collect all selected cards' tag data
  const selectedCards = [...document.querySelectorAll('.ci-card.selected')];
  if (!selectedCards.length) {
    panel.style.display = 'none';
    panel.replaceChildren();
    return;
  }

  panel.style.display = 'block';
  panel.replaceChildren();

  const header = document.createElement('div');
  header.className = 'ci-tag-panel-header';
  header.textContent = '📋 已選取套件的測試標籤指令';
  panel.appendChild(header);

  // Gather tags from all selected CI cards (preserve order)
  const allTags = [];
  for (const tl of _ciData) {
    const card = document.getElementById(`ci-card-${tl.name}`);
    if (card?.classList.contains('selected')) {
      for (const tag of tl.includes) {
        if (!allTags.includes(tag)) allTags.push(tag);
      }
    }
  }

  const list = document.createElement('div');
  list.className = 'ci-tag-list';

  for (const tag of allTags) {
    const cmd = _buildTagCommand(tag);

    const wrap = document.createElement('div');
    wrap.style.marginBottom = '12px';

    // Header
    const hdr = document.createElement('div');
    hdr.className = 'log-console-header';
    hdr.style.borderRadius = '6px 6px 0 0';

    const tagLabel = document.createElement('span');
    tagLabel.textContent = tag;
    tagLabel.style.cssText = 'font-family:var(--font-mono);font-size:0.85rem;font-weight:700;color:var(--text-primary,#e2e8f0);letter-spacing:0.04em';

    const copyBtn = document.createElement('button');
    copyBtn.className = 'btn btn--ghost btn--xs';
    copyBtn.textContent = '複製';
    copyBtn.addEventListener('click', async () => {
      try {
        await navigator.clipboard.writeText(cmd);
        copyBtn.textContent = '已複製 ✓';
        setTimeout(() => { copyBtn.textContent = '複製'; }, 2000);
      } catch {
        showToast('複製失敗，請手動複製', 'error');
      }
    });

    hdr.appendChild(tagLabel);
    hdr.appendChild(copyBtn);

    // Body — same as #qemu-cmd-preview
    const body = document.createElement('pre');
    body.style.cssText = 'margin:0;background:#05080f;font-family:var(--font-mono);font-size:0.72rem;line-height:1.6;color:#f6ad55;padding:var(--space-3);overflow-x:auto;white-space:pre-wrap;word-break:break-all;border-radius:0 0 6px 6px;border:1px solid var(--border-subtle);border-top:none';
    body.textContent = cmd;

    wrap.appendChild(hdr);
    wrap.appendChild(body);
    list.appendChild(wrap);
  }
  panel.appendChild(list);
}

function _updateCiSelectionBar() {
  const bar   = document.getElementById('ci-selection-bar');
  const count = document.getElementById('ci-selected-count');
  const n = _selectedCiIncludes.size;

  bar.classList.toggle('hidden', n === 0);
  if (count) count.textContent = String(n);
}

function clearCiSelection() {
  _selectedCiIncludes.clear();
  document.querySelectorAll('.ci-card').forEach(card => {
    card.classList.remove('selected');
    const btn = card.querySelector('.ci-card-btn');
    if (btn) { btn.classList.remove('deselect'); btn.textContent = '選取'; }
  });
  _updateCiSelectionBar();
  _renderCiTagCmdPanel();
}

// ── Categorized Test Browser ──────────────────────────────────────────────────

async function loadCategorized() {
  const container = document.getElementById('browse-test-list');
  container.replaceChildren();
  const loading = document.createElement('div');
  loading.className = 'tree-empty';
  loading.textContent = '⏳ 解析 .robot 檔案中，請稍候…';
  container.appendChild(loading);

  try {
    const data = await API.get('/api/robot/categorized');
    _categorizedData = data.categories ?? [];
    if (data.robot_dir) _robotDir = data.robot_dir;
    _renderBrowseCategoryChips();
    _renderBrowseTests(_activeBrowseCat, '');
  } catch {
    container.replaceChildren();
    const err = document.createElement('div');
    err.className = 'tree-empty';
    err.textContent = '⚠ 無法載入測試清單 — 確認後端已啟動';
    container.appendChild(err);
    showToast('Failed to load categorized tests', 'error');
  }
}

function _renderBrowseCategoryChips() {
  const wrap = document.getElementById('browse-category-chips');
  wrap.replaceChildren();

  // "All" chip
  const allChip = document.createElement('div');
  allChip.className = 'chip' + (_activeBrowseCat === null ? ' active' : '');
  const allTotal = _categorizedData.reduce((s, c) => s + c.tests.length, 0);
  allChip.innerHTML = ''; // safe to build manually
  const allName = document.createElement('span');
  allName.textContent = '全部';
  allChip.appendChild(allName);
  const allCnt = document.createElement('span');
  allCnt.className = 'chip-count';
  allCnt.textContent = String(allTotal);
  allChip.appendChild(allCnt);
  allChip.setAttribute('role', 'button');
  allChip.setAttribute('tabindex', '0');
  allChip.addEventListener('click', () => {
    _activeBrowseCat = null;
    _renderBrowseCategoryChips();
    _renderBrowseTests(null, document.getElementById('browse-search')?.value ?? '');
  });
  wrap.appendChild(allChip);

  for (const cat of _categorizedData) {
    const chip = document.createElement('div');
    chip.className = 'chip' + (_activeBrowseCat === cat.key ? ' active' : '');
    chip.setAttribute('role', 'button');
    chip.setAttribute('tabindex', '0');

    const iconEl = document.createElement('span');
    iconEl.textContent = cat.icon + ' ';
    chip.appendChild(iconEl);

    const nameEl = document.createElement('span');
    nameEl.textContent = cat.display_name;
    chip.appendChild(nameEl);

    const cntEl = document.createElement('span');
    cntEl.className = 'chip-count';
    cntEl.textContent = String(cat.tests.length);
    chip.appendChild(cntEl);

    const catKey = cat.key;
    chip.addEventListener('click', () => {
      _activeBrowseCat = catKey;
      _renderBrowseCategoryChips();
      _renderBrowseTests(catKey, document.getElementById('browse-search')?.value ?? '');
    });
    wrap.appendChild(chip);
  }
}

function _renderBrowseTests(categoryKey, query) {
  const container = document.getElementById('browse-test-list');
  container.replaceChildren();

  const q = (query ?? '').toLowerCase().trim();

  let tests = [];
  for (const cat of _categorizedData) {
    if (categoryKey && cat.key !== categoryKey) continue;
    for (const t of cat.tests) {
      const matchQ = !q
        || t.name.toLowerCase().includes(q)
        || (t.doc && t.doc.toLowerCase().includes(q))
        || (t.suite_doc && t.suite_doc.toLowerCase().includes(q));
      if (matchQ) {
        tests.push({ ...t, category: cat });
      }
    }
  }

  if (!tests.length) {
    const empty = document.createElement('div');
    empty.className = 'tree-empty';
    empty.textContent = q ? '🔍 無符合的測試' : '📂 此類別無測試';
    container.appendChild(empty);
    _updateBrowseSelectionBar();
    return;
  }

  for (const t of tests) {
    container.appendChild(_buildTestCard(t));
  }
  _updateBrowseSelectionBar();
}

function _buildTestCard(t) {
  const _testKey = t.file + '\0' + t.name;
  const card = document.createElement('div');
  card.className = 'test-card' + (_selectedTests.has(_testKey) ? ' checked' : '');
  card.setAttribute('role', 'listitem');

  // Checkbox
  const cb = document.createElement('input');
  cb.type = 'checkbox';
  cb.className = 'test-card-cb';
  cb.checked = _selectedTests.has(_testKey);
  cb.setAttribute('aria-label', t.name);
  card._suiteFile = t.file;
  card._testKey   = _testKey;
  cb.addEventListener('change', () => {
    if (cb.checked) {
      _selectedTests.add(_testKey);
      _selectedSuites.add(t.file);
      card.classList.add('checked');
    } else {
      _selectedTests.delete(_testKey);
      // Remove file only if no other selected test in this file remains
      const prefix = t.file + '\0';
      let stillHas = false;
      for (const k of _selectedTests) { if (k.startsWith(prefix)) { stillHas = true; break; } }
      if (!stillHas) _selectedSuites.delete(t.file);
      card.classList.remove('checked');
    }
    _updateBrowseSelectionBar();
    _renderBrowseTagCmdPanel();
  });
  card.appendChild(cb);

  // Body
  const body = document.createElement('div');
  body.className = 'test-card-body';

  const nameEl = document.createElement('div');
  nameEl.className = 'test-card-name';
  nameEl.textContent = t.name;
  body.appendChild(nameEl);

  // Doc: prefer test-level doc, fall back to suite doc
  const docText = t.doc || t.suite_doc || '';
  if (docText) {
    const docEl = document.createElement('div');
    docEl.className = 'test-card-doc';
    docEl.textContent = docText.length > 160 ? docText.slice(0, 157) + '…' : docText;
    body.appendChild(docEl);
  }

  // Meta: tags + file path
  const meta = document.createElement('div');
  meta.className = 'test-card-meta';

  // Category badge
  if (t.category) {
    const catTag = document.createElement('span');
    catTag.className = 'test-tag';
    catTag.textContent = t.category.icon + ' ' + t.category.display_name;
    meta.appendChild(catTag);
  }

  // First tag from test
  if (t.tags?.length) {
    const tagEl = document.createElement('span');
    tagEl.className = 'test-tag';
    tagEl.textContent = t.tags[0];
    meta.appendChild(tagEl);
  }

  // File path
  const fileEl = document.createElement('span');
  fileEl.className = 'test-file';
  fileEl.textContent = t.file;
  meta.appendChild(fileEl);

  body.appendChild(meta);
  card.appendChild(body);

  // Click on card = toggle checkbox
  card.addEventListener('click', (e) => {
    if (e.target === cb) return;
    cb.checked = !cb.checked;
    cb.dispatchEvent(new Event('change'));
  });

  return card;
}

function filterBrowse(query) {
  _renderBrowseTests(_activeBrowseCat, query);
}

function _updateBrowseSelectionBar() {
  const count = document.getElementById('browse-selected-count');
  const n = _selectedTests.size;   // test-case count (not unique-file count)
  if (count) count.textContent = String(n);
}

function selectAllBrowse() {
  document.querySelectorAll('.test-card').forEach(card => {
    const cb = card.querySelector('.test-card-cb');
    if (!cb) return;
    cb.checked = true;
    card.classList.add('checked');
    if (card._testKey)   _selectedTests.add(card._testKey);
    if (card._suiteFile) _selectedSuites.add(card._suiteFile);
  });
  _updateBrowseSelectionBar();
  _renderBrowseTagCmdPanel();
}

function clearCategoryBrowse() {
  document.querySelectorAll('.test-card').forEach(card => {
    const cb = card.querySelector('.test-card-cb');
    if (!cb) return;
    cb.checked = false;
    card.classList.remove('checked');
    if (card._testKey) _selectedTests.delete(card._testKey);
  });
  // Rebuild _selectedSuites from remaining _selectedTests
  _selectedSuites.clear();
  for (const k of _selectedTests) {
    const sep = k.indexOf('\0');
    if (sep > 0) _selectedSuites.add(k.slice(0, sep));
  }
  _updateBrowseSelectionBar();
  _renderBrowseTagCmdPanel();
}

function clearBrowseSelections() {
  _selectedSuites.clear();
  _selectedTests.clear();
  document.querySelectorAll('.test-card-cb').forEach(cb => {
    cb.checked = false;
    cb.closest('.test-card')?.classList.remove('checked');
  });
  _updateBrowseSelectionBar();
  _renderBrowseTagCmdPanel();
}

function _renderBrowseTagCmdPanel() {
  const panel = document.getElementById('browse-tag-cmd-panel');
  if (!panel) return;
  if (!_selectedTests.size) {
    panel.style.display = 'none';
    panel.replaceChildren();
    return;
  }

  panel.style.display = 'block';
  panel.replaceChildren();

  // Group selected tests by file
  const byFile = new Map();
  for (const k of _selectedTests) {
    const sep = k.indexOf('\0');
    const file = k.slice(0, sep);
    const name = k.slice(sep + 1);
    if (!byFile.has(file)) byFile.set(file, []);
    byFile.get(file).push(name);
  }

  const header = document.createElement('div');
  header.className = 'ci-tag-panel-header';
  header.textContent = `📋 已選取腳本執行指令（${byFile.size} 個檔案 / ${_selectedTests.size} 個測試案例）`;
  panel.appendChild(header);

  const list = document.createElement('div');
  list.className = 'ci-tag-list';

  for (const [file, testNames] of byFile) {
    const cmd = _buildBrowseCommand(file, testNames);

    const wrap = document.createElement('div');
    wrap.style.marginBottom = '12px';

    const hdr = document.createElement('div');
    hdr.className = 'log-console-header';
    hdr.style.borderRadius = '6px 6px 0 0';

    const label = document.createElement('span');
    label.textContent = file;
    label.style.cssText = 'font-family:var(--font-mono);font-size:0.85rem;font-weight:700;color:var(--text-primary,#e2e8f0);letter-spacing:0.04em';

    const copyBtn = document.createElement('button');
    copyBtn.className = 'btn btn--ghost btn--xs';
    copyBtn.textContent = '複製';
    copyBtn.addEventListener('click', async () => {
      try {
        await navigator.clipboard.writeText(cmd);
        copyBtn.textContent = '已複製 ✓';
        setTimeout(() => { copyBtn.textContent = '複製'; }, 2000);
      } catch { showToast('複製失敗', 'error'); }
    });

    hdr.appendChild(label);
    hdr.appendChild(copyBtn);

    const body = document.createElement('pre');
    body.style.cssText = 'margin:0;background:#05080f;font-family:var(--font-mono);font-size:0.72rem;line-height:1.6;color:#f6ad55;padding:var(--space-3);overflow-x:auto;white-space:pre-wrap;word-break:break-all;border-radius:0 0 6px 6px;border:1px solid var(--border-subtle);border-top:none';
    body.textContent = cmd;

    wrap.appendChild(hdr);
    wrap.appendChild(body);
    list.appendChild(wrap);
  }
  panel.appendChild(list);
}

function _buildBrowseCommand(file, testNames) {
  const vars = _collectVariables();
  const parts = ['python3', '-m', 'robot'];
  for (const [k, v] of Object.entries(vars)) {
    parts.push('--variable', `${k}:${v}`);
  }
  for (const name of testNames) {
    parts.push('--test', `"${name}"`);
  }
  parts.push(_robotDir + '/' + file);
  return parts.join(' ');
}

function _buildSuiteCommand(suite) {
  const vars = _collectVariables();
  const parts = ['python3', '-m', 'robot'];
  for (const [k, v] of Object.entries(vars)) {
    parts.push('--variable', `${k}:${v}`);
  }
  parts.push(_robotDir + '/' + suite);
  return parts.join(' ');
}

// ── Variables helpers ─────────────────────────────────────────────────────────

function _collectVariables() {
  const vars = {};
  const host      = document.getElementById('var-host')?.value.trim();
  const user      = document.getElementById('var-user')?.value.trim();
  const pass      = document.getElementById('var-pass')?.value.trim();
  const ipmiPass  = document.getElementById('var-ipmi-pass')?.value.trim();
  const sshPort   = document.getElementById('var-ssh-port')?.value.trim();
  const httpsPort = document.getElementById('var-https-port')?.value.trim();
  const ipmiPort  = document.getElementById('var-ipmi-port')?.value.trim();

  if (host)      vars['OPENBMC_HOST']              = host;
  if (user)      vars['OPENBMC_USERNAME']           = user;
  if (pass)      vars['OPENBMC_PASSWORD']           = pass;
  if (ipmiPass)  vars['IPMI_PASSWORD']              = ipmiPass;
  if (sshPort)   vars['SSH_PORT']                   = sshPort;
  if (httpsPort) vars['HTTPS_PORT']                 = httpsPort;
  if (ipmiPort)  vars['IPMI_PORT']                  = ipmiPort;

  const extra = document.getElementById('var-extra')?.value.trim() ?? '';
  extra.split('\n').forEach(line => {
    const idx = line.indexOf(':');
    if (idx < 1) return;
    const k = line.slice(0, idx).trim();
    const v = line.slice(idx + 1).trim();
    if (k) vars[k] = v;
  });
  return vars;
}

function fillDefaultVars() {
  document.getElementById('var-host').value      = '172.18.0.2';
  document.getElementById('var-user').value      = 'root';
  document.getElementById('var-pass').value      = '0penBmc';
  document.getElementById('var-ipmi-pass').value = '0penBmc';
  document.getElementById('var-ssh-port').value  = '2222';
  document.getElementById('var-https-port').value = '2443';
  document.getElementById('var-ipmi-port').value = '2623';
  document.getElementById('var-extra').value     = 'REDFISH_SUPPORT_TRANS_STATE:1';
  showToast('預設值已帶入', 'info');
}

function clearVars() {
  ['var-host','var-user','var-pass','var-ipmi-pass',
   'var-ssh-port','var-https-port','var-ipmi-port','var-extra'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.value = '';
  });
}

// ── CI Mode Run (using --include tags, suite = root ".") ──────────────────────

async function runCi() {
  const tags = [..._selectedCiIncludes];
  if (!tags.length) { showToast('請先點選至少一個 CI 套件', 'error'); return; }

  const isDryRun  = document.getElementById('robot-dry-run-ci')?.checked ?? false;
  const variables = _collectVariables();

  // Always fetch and show the assembled command preview
  _setRunStatus(true, '組合指令中…', 'btn-stream-ci');
  try {
    const preview = await API.post('/api/robot/run', {
      suites: ['.'], variables, dry_run: true, include_tags: tags,
    });
    if (preview.ok && preview.command) _showCmdPreview(preview.command, 'ci');
  } catch { /* preview failure is non-blocking */ }
  _setRunStatus(false, '', 'btn-stream-ci');

  if (isDryRun) {
    showToast('Dry-run 完成', 'success');
    return;
  }

  await _doStreamRun(['.'], variables, tags, 'btn-stream-ci');
}

// ── Browse Mode Run (using file paths) ────────────────────────────────────────

async function runBrowse() {
  const suites = [..._selectedSuites];
  if (!suites.length) { showToast('請先在「瀏覽測試」勾選至少一個腳本', 'error'); return; }

  // Collect selected test names from _selectedTests
  const testNames = [..._selectedTests].map(k => k.slice(k.indexOf('\0') + 1));

  const isDryRun  = document.getElementById('robot-dry-run-browse')?.checked ?? false;
  const variables = _collectVariables();

  // Always fetch and show the assembled command preview
  _setRunStatus(true, '組合指令中…', 'btn-stream-browse');
  try {
    const preview = await API.post('/api/robot/run', { suites, variables, dry_run: true, test_names: testNames });
    if (preview.ok && preview.command) _showCmdPreview(preview.command, 'browse');
  } catch { /* preview failure is non-blocking */ }
  _setRunStatus(false, '', 'btn-stream-browse');

  if (isDryRun) {
    showToast('Dry-run 完成', 'success');
    return;
  }

  await _doStreamRun(suites, variables, [], 'btn-stream-browse', testNames);
}

// ── Shared streaming run helper ───────────────────────────────────────────────

async function _doStreamRun(suites, variables, includeTags, streamBtnId, testNames = []) {
  if (_robotWs) { _robotWs.close(); _robotWs = null; }

  const streamBtn = document.getElementById(streamBtnId);
  if (streamBtn) streamBtn.disabled = true;

  const label = includeTags.length
    ? `CI ${includeTags.length} tags`
    : `${testNames.length || suites.length} test(s)`;
  showToast(`啟動串流執行 (${label})…`, 'info');

  try {
    const data = await API.post('/api/robot/stream-run', {
      suites,
      variables,
      include_tags: includeTags,
      test_names:   testNames,
    });

    if (!data.ok) {
      showToast(`啟動失敗: ${data.detail ?? data.error}`, 'error');
      if (streamBtn) streamBtn.disabled = false;
      return;
    }

    _currentRunId = data.run_id;

    const badge    = document.getElementById('robot-run-id-badge');
    const badgeTxt = document.getElementById('robot-run-id-text');
    if (badge && badgeTxt) { badgeTxt.textContent = _currentRunId; badge.hidden = false; }

    switchRobotTab('log');
    clearRobotLog();
    appendRobotLog(`▶ Run ID: ${_currentRunId}\n`, 'log-info');
    appendRobotLog(`  Suites: ${suites.join(', ')}\n`, 'log-debug');
    if (includeTags.length) {
      appendRobotLog(`  --include: ${includeTags.join(', ')}\n`, 'log-debug');
    }
    appendRobotLog('─'.repeat(60) + '\n', 'log-sep');

    const progressWrap = document.getElementById('robot-progress-wrap');
    const progressBar  = document.getElementById('robot-progress-bar');
    progressWrap?.classList.remove('hidden');
    if (progressBar) progressBar.style.width = '100%';

    _setRobotWsBadge('connecting');
    const wsUrl = `ws://${window.location.host}/api/robot/ws/logs/${_currentRunId}`;
    _robotWs = new WebSocket(wsUrl);

    _robotWs.onopen = () => {
      _setRobotWsBadge('on');
      appendRobotLog('[WebSocket] 連線成功，等待輸出…\n', 'log-info');
    };

    _robotWs.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data);
        if (msg.generating_allure) {
          const rc = msg.returncode ?? -1;
          appendRobotLog('\n' + '─'.repeat(60) + '\n', 'log-sep');
          appendRobotLog(
            rc === 0 ? `✅ PASSED — rc: ${rc}\n` : `❌ FAILED — rc: ${rc}\n`,
            rc === 0 ? 'log-done' : 'log-fail'
          );
          appendRobotLog('[Allure] 產生報告中…\n', 'log-info');
          return;
        }
        if (msg.done !== undefined) {
          const rc = msg.returncode ?? -1;
          appendRobotLog('[Allure] 報告產生完成\n', 'log-info');
          progressWrap?.classList.add('hidden');
          if (streamBtn) streamBtn.disabled = false;
          _setRobotWsBadge('off');
          if (rc === 0) showToast('Robot 測試通過 ✓', 'success');
          else showToast(`Robot 測試失敗 (rc=${rc})`, 'error');
          loadReports(true);
          const viewReportBtn = document.createElement('button');
          viewReportBtn.className = 'btn btn--primary btn--sm';
          viewReportBtn.style.marginTop = '8px';
          viewReportBtn.textContent = '查看報告';
          viewReportBtn.addEventListener('click', () => showPage('reports'));
          const logEl = document.getElementById('robot-log-console');
          if (logEl) {
            logEl.appendChild(viewReportBtn);
            logEl.scrollTop = logEl.scrollHeight;
          }
          return;
        }
        if (msg.error) { appendRobotLog(`[ERROR] ${msg.error}\n`, 'log-fail'); return; }
      } catch { /* not JSON — plain log line */ }
      _appendColoredLog(e.data);
    };

    _robotWs.onclose = () => {
      _setRobotWsBadge('off');
      progressWrap?.classList.add('hidden');
      if (streamBtn) streamBtn.disabled = false;
    };

    _robotWs.onerror = () => {
      _setRobotWsBadge('off');
      appendRobotLog('[WebSocket ERROR] 連線中斷\n', 'log-fail');
      progressWrap?.classList.add('hidden');
      if (streamBtn) streamBtn.disabled = false;
    };

  } catch (e) {
    showToast(`串流啟動失敗: ${e}`, 'error');
    if (streamBtn) streamBtn.disabled = false;
  }
}

// ── Run status helpers ────────────────────────────────────────────────────────

function _syncLogCmdPreview() {
  // Show the most recently assembled command in the Live Log header area
  const logWrap  = document.getElementById('robot-log-cmd-wrap');
  const logPre   = document.getElementById('robot-log-cmd-preview');
  if (!logWrap || !logPre) return;

  // Try CI preview first, then browse
  const ciPre    = document.getElementById('robot-cmd-preview-ci');
  const browsePre = document.getElementById('robot-cmd-preview-browse');
  const ciWrap   = document.getElementById('robot-cmd-preview-wrap-ci');
  const browseWrap = document.getElementById('robot-cmd-preview-wrap-browse');

  let cmd = '';
  if (ciWrap?.style.display !== 'none' && ciPre?.textContent?.trim()) {
    cmd = ciPre.textContent;
  } else if (browseWrap?.style.display !== 'none' && browsePre?.textContent?.trim()) {
    cmd = browsePre.textContent;
  }

  if (cmd) {
    logWrap.style.display = 'block';
    logPre.textContent = cmd;
  } else {
    logWrap.style.display = 'none';
  }
}

function _setRunStatus(active, text, btnId) {
  // Determine which status element to use based on which btn-row it belongs to
  const suffix   = btnId.includes('browse') ? 'browse' : '';
  const statusId = suffix ? 'robot-run-status-browse' : 'robot-run-status';
  const textId   = suffix ? 'robot-run-status-text-browse' : 'robot-run-status-text';
  const statusEl  = document.getElementById(statusId);
  const statusTxt = document.getElementById(textId);
  const btn       = document.getElementById(btnId);
  if (statusEl) statusEl.hidden = !active;
  if (statusTxt) statusTxt.textContent = text;
  if (btn) btn.disabled = active;
}

function _formatCmd(cmd) {
  // Robot: line-break before each --flag
  return cmd.replace(/\s(--\w)/g, ' \\\n  $1');
}

function _formatQemuCmd(cmd) {
  // QEMU: line-break before each -flag (single dash, not inside values)
  return cmd.replace(/\s(-\w)/g, ' \\\n  $1');
}

function _showCmdPreview(cmd, suffix) {
  const wrap = document.getElementById(`robot-cmd-preview-wrap-${suffix}`);
  const el   = document.getElementById(`robot-cmd-preview-${suffix}`);
  const hdr  = document.getElementById(`robot-cmd-preview-hdr-${suffix}`);
  if (!wrap) return;

  wrap.style.display = 'block';
  if (el) el.textContent = _formatCmd(cmd);

  // Add copy button to header (once); always copies formatted textContent
  if (hdr && !hdr.querySelector('.cmd-copy-btn')) {
    const copyBtn = document.createElement('button');
    copyBtn.className = 'btn btn--ghost btn--xs cmd-copy-btn';
    copyBtn.textContent = '複製';
    copyBtn.addEventListener('click', () => {
      _copyTextToClipboard(el ? el.textContent : cmd, copyBtn);
    });
    hdr.appendChild(copyBtn);
  }
}

// ── Robot log console helpers ─────────────────────────────────────────────────

const _LOG_PATTERNS = [
  { re: /\bPASS\b/,                cls: 'log-pass'  },
  { re: /\bFAIL\b/,                cls: 'log-fail'  },
  { re: /\bWARN\b/,                cls: 'log-warn'  },
  { re: /^\[ INFO \]|^INFO/,       cls: 'log-info'  },
  { re: /^\[ DEBUG \]|^DEBUG/,     cls: 'log-debug' },
  { re: /^={2,}|^-{2,}/,          cls: 'log-sep'   },
];

function _appendColoredLog(text) {
  let cls = null;
  for (const { re, cls: c } of _LOG_PATTERNS) {
    if (re.test(text)) { cls = c; break; }
  }
  appendRobotLog(text, cls);
}

function appendRobotLog(text, cssClass = null) {
  const logEl = document.getElementById('robot-log-console');
  if (!logEl) return;
  const span = document.createElement('span');
  if (cssClass) span.className = cssClass;
  span.textContent = text;
  logEl.appendChild(span);
  logEl.scrollTop = logEl.scrollHeight;
}

function clearRobotLog() {
  const logEl = document.getElementById('robot-log-console');
  if (logEl) logEl.replaceChildren();
}

function _setRobotWsBadge(state) {
  const badge = document.getElementById('robot-ws-badge');
  if (!badge) return;
  badge.className = `ws-badge ws-badge--${state}`;
  badge.textContent = { on: 'WS ON', off: 'WS OFF', connecting: 'WS …' }[state] ?? 'WS';
}

// ── Reports ───────────────────────────────────────────────────────────────────

let _reportsCache = null;   // null = never fetched; [] or [...] = fetched

function _renderReportList(reports, list) {
  list.replaceChildren();
  if (!reports.length) {
    const empty = document.createElement('div');
    empty.className = 'report-empty';
    empty.textContent = '尚無報告。執行測試套件後報告將顯示於此。';
    list.appendChild(empty);
    return;
  }
  reports.forEach(r => {
    const card = document.createElement('div');
    card.className = 'report-card';

    const header = document.createElement('div');
    header.className = 'report-card-header';

    const nameSpan = document.createElement('span');
    nameSpan.className = 'report-name';
    nameSpan.textContent = `📄 ${r.name}`;
    header.appendChild(nameSpan);

    const tsSpan = document.createElement('span');
    tsSpan.className = 'report-timestamp';
    tsSpan.textContent = r.modified;
    header.appendChild(tsSpan);

    card.appendChild(header);

    if (r.passed !== null || r.failed !== null || r.elapsed_s !== null) {
      const statsBar = document.createElement('div');
      statsBar.className = 'report-stats-bar';
      statsBar.style.cssText = 'display:flex;gap:12px;padding:4px 0 6px;font-size:0.82rem;flex-wrap:wrap';

      if (r.passed !== null) {
        const passEl = document.createElement('span');
        passEl.style.color = r.passed > 0 ? '#48bb78' : 'inherit';
        passEl.textContent = `\u2705 ${r.passed} passed`;
        statsBar.appendChild(passEl);
      }
      if (r.failed !== null) {
        const failEl = document.createElement('span');
        failEl.style.color = r.failed > 0 ? '#fc8181' : 'inherit';
        failEl.textContent = `\u274c ${r.failed} failed`;
        statsBar.appendChild(failEl);
      }
      if (r.elapsed_s !== null) {
        const timeEl = document.createElement('span');
        const s = r.elapsed_s;
        const timeStr = s >= 60
          ? `${Math.floor(s / 60)}m ${Math.round(s % 60)}s`
          : `${s.toFixed(1)}s`;
        timeEl.textContent = `\u23f1 ${timeStr}`;
        statsBar.appendChild(timeEl);
      }
      card.appendChild(statsBar);
    }

    const actions = document.createElement('div');
    actions.className = 'report-actions';

    const linkReport = document.createElement('a');
    linkReport.href = '/reports/' + r.report_path;
    linkReport.target = '_blank';
    linkReport.rel = 'noopener noreferrer';
    linkReport.className = 'btn btn--ghost btn--sm report-link';
    linkReport.textContent = '🌐 HTML Report';
    actions.appendChild(linkReport);

    const linkLog = document.createElement('a');
    linkLog.href = '/reports/' + r.log_path;
    linkLog.target = '_blank';
    linkLog.rel = 'noopener noreferrer';
    linkLog.className = 'btn btn--ghost btn--sm report-link';
    linkLog.textContent = '📋 Full Log';
    actions.appendChild(linkLog);

    if (r.allure_path) {
      const linkAllure = document.createElement('a');
      linkAllure.href = '/reports/' + r.allure_path;
      linkAllure.target = '_blank';
      linkAllure.rel = 'noopener noreferrer';
      linkAllure.className = 'btn btn--primary btn--sm report-link';
      linkAllure.textContent = '🔬 Allure 報告';
      actions.appendChild(linkAllure);
    }

    card.appendChild(actions);
    list.appendChild(card);
  });
}

async function loadReports(force = false) {
  const list = document.getElementById('report-list');

  // Return cached data instantly on repeat visits (no spinner)
  if (!force && _reportsCache !== null) {
    _renderReportList(_reportsCache, list);
    return;
  }

  list.innerHTML = '<div class="report-loading"><div class="report-loading-spinner"></div><span>載入報告中…</span></div>';
  try {
    const data = await API.get('/api/robot/reports');
    _reportsCache = data.reports ?? [];
    _renderReportList(_reportsCache, list);
  } catch {
    showToast('Failed to load reports', 'error');
  }
}

// ── Auto-preview bindings ─────────────────────────────────────────────────────

function _bindAutoPreview() {
  document.getElementById('qemu-image')?.addEventListener('change', previewCommand);
  document.getElementById('qemu-machine')?.addEventListener('input', debouncePreview);
  document.getElementById('qemu-extra-args')?.addEventListener('input', debouncePreview);
  document.getElementById('qemu-memory')?.addEventListener('input', debouncePreview);
  document.getElementById('qemu-binary')?.addEventListener('input', debouncePreview);
  document.getElementById('qemu-use-nic')?.addEventListener('change', debouncePreview);
}

let _previewTimer = null;

// ── Init ──────────────────────────────────────────────────────────────────────

async function init() {
  initTerminal();
  fillDefaultVars();
  await checkBackendHealth();
  await Promise.all([
    loadPresets(),
    refreshQemuImages(),
    refreshQemuStatus(),
    loadCiCards(),
    loadCategorized(),
  ]);
  _bindAutoPreview();

  // Collapse vars section when user interacts with anything below it in the robot panel
  document.getElementById('robot-panel')?.addEventListener('click', (e) => {
    const varsSection = document.getElementById('robot-section-vars');
    if (!varsSection || varsSection.contains(e.target)) return;
    const content = document.getElementById('robot-vars-content');
    if (content && !content.classList.contains('collapsed')) {
      content.classList.add('collapsed');
      const icon = document.getElementById('vars-toggle-icon');
      if (icon) icon.textContent = '▶';
    }
  }, true);  // capture phase so it fires before child handlers

  setInterval(refreshQemuStatus,   5000);
  setInterval(checkBackendHealth, 30000);
}

document.addEventListener('DOMContentLoaded', init);
