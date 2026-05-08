/* ══════════════════════════════════════════════════════════════════
   config.js — Config Panel: Feature Switches, Brain Control, Volume
══════════════════════════════════════════════════════════════════ */

const Config = (() => {
  const toggleGridEl = document.getElementById('toggleGrid');
  const modelListEl  = document.getElementById('modelList');
  const expertPoolListEl = document.getElementById('expertPoolList');
  const expertPoolMetaEl = document.getElementById('expertPoolMeta');
  const brainDot     = document.getElementById('brainStatusDot');
  const brainPidEl   = document.getElementById('brainPid');
  const brainUptimeEl= document.getElementById('brainUptime');
  const brainModelEl = document.getElementById('brainModel');
  const restartBtn   = document.getElementById('restartBtn');
  const stopBtn      = document.getElementById('stopBtn');
  const startBtn     = document.getElementById('startBtn');
  const volSlider    = document.getElementById('volumeSlider');
  const volValue     = document.getElementById('volValue');

  // ─── Flags that are "feature switches" (USE_*) ───────────────
  const USE_LABELS = {
    USE_STREAMING:    'Streaming Mode',
    USE_VOICE:        'Text-to-Speech',
    USE_DISCORD:      'Discord Bot',
    USE_SPOTIFY:      'Spotify Control',
    USE_TOOLS:        'File Brain Tools',
    USE_OPENROUTER:   'OpenRouter (Cloud)',
    USE_SAFETY_FILTER:'Granite Safety Filter',
    USE_ALTPERSONA_MODE:    'AltPersona Mode verfügbar',
    USE_WEBSITE:      'Website Update Tool',
    USE_WEB_SEARCH:   'Web Search (Crawler)',
    USE_PAPERLESS:    'Paperless (Dokumente)',
    USE_HOME_ASSISTANT:  'Home Assistant (Smart Home)',
    USE_PROMISE_CHECK:   'Promise Tracker 🤝',
  };

  let _config = {};
  let _debounceTimer = null;
  let _uptimeInterval = null;
  let _startTimestamp = null;
  let _userRole = 'chat';  // set by loadUserProfile(), guards admin-only calls

  // ─── API Helper ──────────────────────────────────────────────
  // Read key directly from URL params (avoids dependency on App which loads later)
  const _accessKey = localStorage.getItem('yourai_access_key');

  function _authHeaders(extra = {}) {
    const h = { ...extra };
    if (_accessKey) h['Authorization'] = `Bearer ${_accessKey}`;
    const uuid = (typeof YourAIUUID !== 'undefined') ? YourAIUUID.get() : null;
    if (uuid) h['X-Session-UUID'] = uuid;
    return h;
  }

  async function _api(url, options = {}) {
    options.headers = _authHeaders(options.headers || {});
    const res = await fetch(url, options);
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      const msg = err.detail || res.statusText;
      console.error(`❌ API Error [${res.status}] ${url}: ${msg}`);
      throw new Error(msg);
    }
    return res.json();
  }

  // ─── Maintenance Banner ──────────────────────────────────────
  const _maintenanceBanner = document.getElementById('maintenanceBanner');
  const _maintenanceToggle = document.getElementById('maintenanceToggle');

  function _applyMaintenance(active) {
    _maintenanceToggle.checked = Boolean(active);
    _maintenanceBanner.classList.toggle('active', Boolean(active));
  }

  _maintenanceToggle.addEventListener('change', async () => {
    const val = _maintenanceToggle.checked;
    _maintenanceBanner.classList.toggle('active', val);
    try {
      await _api('/api/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ key: 'USE_MAINTENANCE', value: val }),
      });
    } catch (e) {
      // Revert on error
      _applyMaintenance(!val);
      console.error('❌ Maintenance Toggle fehlgeschlagen:', e);
    }
  });

  // ─── Load config from API ─────────────────────────────────────
  async function load() {
    try {
      _config = await _api('/api/config');
      _renderToggles(_config.flags || {});
      _renderModels(_config.models || {});
      await _loadExpertPool();
      _applyMaintenance(_config.flags?.USE_MAINTENANCE ?? false);
    } catch (e) {
      console.error('❌ Config Load Failed:', e);
      toggleGridEl.innerHTML = `<div class="config-loading" style="color:var(--accent-red)">⚠️ Config konnte nicht geladen werden</div>`;
    }
  }

  // ─── Render USE_* toggles ─────────────────────────────────────
  function _renderToggles(flags) {
    toggleGridEl.innerHTML = '';

    const flagKeys = Object.keys(flags).filter(k => k.startsWith('USE_'));
    if (!flagKeys.length) {
      toggleGridEl.innerHTML = '<div class="config-loading">Keine USE_* flags gefunden</div>';
      return;
    }

    flagKeys.forEach(key => {
      const val   = flags[key];
      const label = USE_LABELS[key] || key.replace('USE_', '').replaceAll('_', ' ');

      const row = document.createElement('div');
      row.className = 'toggle-row';

      const lbl = document.createElement('label');
      lbl.className = 'toggle-label';
      lbl.htmlFor = `toggle-${key}`;
      // Build label using DOM API to avoid XSS (key/label come from server)
      const codeEl = document.createElement('code');
      codeEl.textContent = key;
      const spanEl = document.createElement('span');
      spanEl.textContent = label;
      lbl.appendChild(codeEl);
      lbl.appendChild(document.createTextNode(' '));
      lbl.appendChild(spanEl);


      const sw = document.createElement('label');
      sw.className = 'toggle-switch';

      const inp = document.createElement('input');
      inp.type = 'checkbox';
      inp.id = `toggle-${key}`;
      inp.checked = Boolean(val);
      inp.dataset.key = key;

      const track = document.createElement('span');
      track.className = 'toggle-track';

      inp.addEventListener('change', () => _onToggle(key, inp.checked));

      sw.appendChild(inp);
      sw.appendChild(track);
      row.appendChild(lbl);
      row.appendChild(sw);
      toggleGridEl.appendChild(row);
    });
  }

  // ─── Render model list ────────────────────────────────────────
  function _renderModels(models) {
    modelListEl.innerHTML = '';
    const entries = Object.entries(models);
    if (!entries.length) {
      modelListEl.textContent = 'Keine Models konfiguriert';
      return;
    }
    entries.forEach(([key, val]) => {
      const row = document.createElement('div');
      row.className = 'model-row';

      // Use textContent / setAttribute to avoid XSS — data comes from server
      const keyEl = document.createElement('span');
      keyEl.className = 'model-key';
      keyEl.textContent = key;

      const valEl = document.createElement('span');
      valEl.className = 'model-val';
      valEl.setAttribute('title', val);  // safe: attribute value, not HTML
      valEl.textContent = val;

      row.appendChild(keyEl);
      row.appendChild(valEl);
      modelListEl.appendChild(row);
    });
  }

  async function _loadExpertPool() {
    if (!expertPoolListEl) return;
    try {
      const pool = await _api('/api/expert_pool');
      _renderExpertPool(pool);
    } catch (e) {
      expertPoolListEl.innerHTML = '<div class="config-loading">Expert Pool konnte nicht geladen werden</div>';
      if (expertPoolMetaEl) expertPoolMetaEl.textContent = 'Fehler';
    }
  }

  function _renderExpertPool(pool) {
    const domains = pool.domains || {};
    const entries = Object.entries(domains);
    expertPoolListEl.innerHTML = '';

    if (expertPoolMetaEl) {
      const lock = pool.lock_ok ? 'lock ok' : 'lock fehlt';
      expertPoolMetaEl.textContent = `${pool.source || 'unknown'} - ${lock}`;
    }

    if (!entries.length) {
      expertPoolListEl.innerHTML = '<div class="config-loading">Keine Expert Models gefunden</div>';
      return;
    }

    entries.forEach(([domain, info]) => {
      const details = document.createElement('details');
      details.className = 'expert-pool-domain';

      const summary = document.createElement('summary');
      const name = document.createElement('span');
      name.className = 'expert-pool-domain-name';
      name.textContent = domain;
      const count = document.createElement('span');
      count.className = 'expert-pool-domain-count';
      count.textContent = `${(info.models || []).length} models`;
      summary.appendChild(name);
      summary.appendChild(count);
      details.appendChild(summary);

      const list = document.createElement('div');
      list.className = 'expert-pool-models';
      (info.models || []).forEach((m, idx) => {
        const row = document.createElement('div');
        row.className = 'expert-pool-model-row';
        const rank = document.createElement('span');
        rank.className = 'expert-pool-rank';
        rank.textContent = `#${idx + 1}`;
        const id = document.createElement('span');
        id.className = 'expert-pool-model-id';
        id.textContent = m.id || 'unknown';
        const meta = document.createElement('span');
        meta.className = 'expert-pool-model-meta';
        const cost = m.effective_cost_usd_per_m == null ? '?' : `$${m.effective_cost_usd_per_m}/M`;
        meta.textContent = `${m.source || 'pool'} - ${cost}`;
        row.appendChild(rank);
        row.appendChild(id);
        row.appendChild(meta);
        list.appendChild(row);
      });
      details.appendChild(list);
      expertPoolListEl.appendChild(details);
    });
  }


  // ─── Toggle changed — debounced save ─────────────────────────
  function _onToggle(key, value) {
    clearTimeout(_debounceTimer);
    _debounceTimer = setTimeout(() => _saveFlag(key, value), 400);
  }

  async function _saveFlag(key, value) {
    try {
      await _api('/api/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ key, value }),
      });
      App.toast(`${key} → ${value ? 'ON' : 'OFF'}`, 'success');
    } catch (e) {
      App.toast(`Fehler: ${e.message}`, 'error');
    }
  }

  // ─── Brain Control ───────────────────────────────────────────
  async function _restart() {
    restartBtn.disabled = true;
    restartBtn.classList.add('spinning');
    try {
      await _api('/api/restart', { method: 'POST' });
      App.toast('🔄 Brain wird neu gestartet...', 'info');
      // Status refresh after 2s
      setTimeout(refreshBrainStatus, 2000);
    } catch (e) {
      App.toast(`Restart fehlgeschlagen: ${e.message}`, 'error');
    } finally {
      setTimeout(() => {
        restartBtn.disabled = false;
        restartBtn.classList.remove('spinning');
      }, 2000);
    }
  }

  async function _stop() {
    if (!confirm('Brain stoppen?')) return;
    try {
      await _api('/api/brain/stop', { method: 'POST' });
      App.toast('⏹️ Brain gestoppt', 'info');
      setTimeout(refreshBrainStatus, 800);
    } catch (e) {
      App.toast(`Stop fehlgeschlagen: ${e.message}`, 'error');
    }
  }

  async function _start() {
    try {
      await _api('/api/brain/start', { method: 'POST' });
      App.toast('▶️ Brain wird gestartet...', 'info');
      setTimeout(refreshBrainStatus, 1500);
    } catch (e) {
      App.toast(`Start fehlgeschlagen: ${e.message}`, 'error');
    }
  }

  // ─── Brain Status ─────────────────────────────────────────────
  async function refreshBrainStatus() {
    if (_userRole !== 'admin') return;
    try {
      const data = await _api('/api/brain_status');
      _setBrainStatus(data);
    } catch {
      _setBrainStatus({ running: false, pid: null, uptime_s: null });
    }
  }

  function _setBrainStatus(data) {
    const running = Boolean(data.running);
    brainDot.className = `brain-status ${running ? 'running' : 'stopped'}`;
    brainPidEl.textContent  = data.pid  ? `#${data.pid}`  : '—';
    brainModelEl.textContent = data.model || '—';

    // Uptime ticker
    clearInterval(_uptimeInterval);
    if (running && data.uptime_s != null) {
      _startTimestamp = Date.now() - data.uptime_s * 1000;
      _uptimeInterval = setInterval(_tickUptime, 1000);
      _tickUptime();
    } else {
      brainUptimeEl.textContent = running ? '—' : 'gestoppt';
    }

    stopBtn.disabled  = !running;
    startBtn.disabled =  running;
  }

  function _tickUptime() {
    const s = Math.floor((Date.now() - _startTimestamp) / 1000);
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    const sec = s % 60;
    let timeStr = `${sec}s`;
    if (h > 0) {
      timeStr = `${h}h ${m}m ${sec}s`;
    } else if (m > 0) {
      timeStr = `${m}m ${sec}s`;
    }
    brainUptimeEl.textContent = timeStr;
  }

  // ─── Volume ──────────────────────────────────────────────────
  async function _loadVolume() {
    try {
      const res = await fetch('/get_volume', { headers: _authHeaders() });
      if (!res.ok) return;
      const { volume } = await res.json();
      volSlider.value = volume;
      volValue.textContent = `${volume}%`;
    } catch { /* ignore */ }
  }

  let _volSaveTimer = null;
  volSlider.addEventListener('input', () => {
    volValue.textContent = `${volSlider.value}%`;
    clearTimeout(_volSaveTimer);
    _volSaveTimer = setTimeout(() => _saveVolume(volSlider.value), 600);
  });

  async function _saveVolume(vol) {
    try {
      await fetch('/set_volume', {
        method: 'POST',
        headers: _authHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ volume: Number.parseInt(vol, 10) }),
      });
    } catch { /* ignore */ }
  }

  // ─── Admin Command Panel ──────────────────────────────────────
  const commandInput  = document.getElementById('commandInput');
  const commandRunBtn = document.getElementById('commandRunBtn');
  const commandResult = document.getElementById('commandResult');
  const commandQuickBtns = document.getElementById('commandQuickBtns');

  async function _runCommand(cmd) {
    if (!cmd) return;
    commandRunBtn.disabled = true;
    commandRunBtn.classList.add('spinning');
    commandResult.hidden = true;
    try {
      const res = await _api('/api/command', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ command: cmd }),
      });
      commandResult.hidden = false;
      if (res.ok) {
        commandResult.className = 'command-result success';
        commandResult.textContent = res.result;
        App.toast(res.result, 'success');
      } else {
        commandResult.className = 'command-result error';
        commandResult.textContent = `❌ ${res.error}`;
        App.toast(`❌ ${res.error}`, 'error');
      }
    } catch (e) {
      commandResult.hidden = false;
      commandResult.className = 'command-result error';
      commandResult.textContent = `❌ ${e.message}`;
      App.toast(`Command fehlgeschlagen: ${e.message}`, 'error');
    } finally {
      commandRunBtn.disabled = false;
      commandRunBtn.classList.remove('spinning');
    }
  }

  if (commandRunBtn) {
    commandRunBtn.addEventListener('click', () => _runCommand(commandInput?.value?.trim()));
  }
  if (commandInput) {
    commandInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') _runCommand(commandInput.value.trim());
    });
  }
  if (commandQuickBtns) {
    commandQuickBtns.addEventListener('click', (e) => {
      const btn = e.target.closest('[data-cmd]');
      if (!btn) return;
      const cmd = btn.dataset.cmd;
      if (commandInput) commandInput.value = cmd;
      _runCommand(cmd);
    });
  }

  // ─── Download Buttons ─────────────────────────────────────────
  async function _triggerDownload(apiPath, fallbackName) {
    try {
      const res = await fetch(apiPath, { headers: _authHeaders() });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
        App.toast(`❌ ${err.detail || 'Download fehlgeschlagen'}`, 'error');
        return;
      }
      const cd = res.headers.get('Content-Disposition') || '';
      const nameMatch = cd.match(/filename=([^\s;]+)/);
      const filename = nameMatch ? nameMatch[1] : fallbackName;
      const blob = await res.blob();
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = filename;
      a.click();
      URL.revokeObjectURL(a.href);
      App.toast(`📥 ${filename} wird heruntergeladen`, 'success');
    } catch (e) {
      App.toast(`❌ Download Fehler: ${e.message}`, 'error');
    }
  }

  document.getElementById('downloadLogsBtn')?.addEventListener('click', () => {
    _triggerDownload('/api/debug/download-log', 'debug_log.jsonl');
  });

  document.getElementById('clearLogsBtn')?.addEventListener('click', async () => {
    if (!confirm('Debug Log wirklich löschen? Das kann nicht rückgängig gemacht werden.')) return;
    try {
      const res = await fetch('/api/debug/clear-log', { method: 'DELETE', headers: _authHeaders() });
      const data = await res.json();
      if (data.ok) {
        App.toast('🗑️ Debug Log geleert — sauberer Start!', 'success');
      } else {
        App.toast(`❌ Fehler: ${data.error}`, 'error');
      }
    } catch (e) {
      App.toast(`❌ Fehler: ${e.message}`, 'error');
    }
  });

  document.getElementById('downloadOutputBtn')?.addEventListener('click', () => {
    _triggerDownload('/api/yourai/download-output', 'yourai_output.txt');
  });

  // ─── Event Listeners ─────────────────────────────────────────
  restartBtn.addEventListener('click', _restart);
  stopBtn.addEventListener('click', _stop);
  startBtn.addEventListener('click', _start);

  // ─── TTS Usage Display ───────────────────────────────────────
  function _updateTTSUsage(tts) {
    const el    = document.getElementById('ttsPremiumUsage');
    const optEl = document.getElementById('ttsTierElOption');
    const bmcEl = document.getElementById('ttsBMCBtn');
    if (!el || !tts) return;

    if (tts.unlimited) {
      el.textContent = '∞ unbegrenzt';
      el.className   = 'tts-premium-usage unlimited';
      optEl?.classList.remove('exhausted');
      if (bmcEl) bmcEl.hidden = true;
    } else {
      const left = tts.remaining ?? (tts.limit - tts.used);
      el.textContent = `${left} von ${tts.limit} gratis diesen Monat`;
      el.className   = 'tts-premium-usage' + (left === 0 ? ' empty' : left === 1 ? ' low' : '');
      optEl?.classList.toggle('exhausted', left === 0);
      if (bmcEl) bmcEl.hidden = left > 0;
    }
  }

  // Live update when TTS is used (header from /api/tts response)
  window.addEventListener('tts_usage_update', (e) => {
    const el = document.getElementById('ttsPremiumUsage');
    const optEl = document.getElementById('ttsTierElOption');
    if (!el) return;
    const remaining = e.detail?.remaining ?? 0;
    // Reload full usage from server to get correct limit
    _api('/api/user/me').then(me => _updateTTSUsage(me.tts_usage)).catch(() => {
      el.textContent = `${remaining} übrig diesen Monat`;
    });
    optEl?.classList.toggle('exhausted', remaining === 0);
  });

  window.addEventListener('tts_limit_reached', () => {
    _api('/api/user/me').then(me => _updateTTSUsage(me.tts_usage)).catch(() => {});
  });

  // ─── TTS Settings ────────────────────────────────────────────
  function initTTSSettings() {
    if (typeof TTS === 'undefined') return;

    const tierRadios   = document.querySelectorAll('input[name="ttsTier"]');
    const autoPlayChk  = document.getElementById('ttsAutoPlayToggle');

    // Apply saved settings to UI
    const savedTier = TTS.getTier();
    tierRadios.forEach(r => { r.checked = r.value === savedTier; });
    if (autoPlayChk) autoPlayChk.checked = TTS.isAutoPlay();

    // Tier change
    tierRadios.forEach(r => {
      r.addEventListener('change', () => {
        if (r.checked) TTS.setTier(r.value);
      });
    });

    // Auto-play toggle
    if (autoPlayChk) {
      autoPlayChk.addEventListener('change', () => {
        TTS.setAutoPlay(autoPlayChk.checked);
      });
    }
  }

  // ─── User Profile & Usage ─────────────────────────────────────
  async function loadUserProfile() {
    try {
      const me = await _api('/api/user/me');

      // Profile card
      const nameEl  = document.getElementById('profileName');
      const descEl  = document.getElementById('profileDesc');
      const badgeEl = document.getElementById('profileRoleBadge');
      if (nameEl)  nameEl.textContent = me.display_name || me.user_key;
      if (descEl)  descEl.textContent = me.description  || '';
      if (badgeEl) {
        badgeEl.textContent  = me.session_role || '—';
        badgeEl.dataset.role = me.session_role || '';
      }

      // Usage card — image quota
      const img     = me.image_usage || {};
      const numEl   = document.getElementById('imageUsageNumbers');
      const barEl   = document.getElementById('imageUsageBar');
      const monthEl = document.getElementById('usageMonth');

      if (monthEl) monthEl.textContent = img.month ? `Monat: ${img.month}` : '';
      if (numEl) {
        numEl.textContent = img.unlimited
          ? `${img.used} / ∞ (unbegrenzt)`
          : `${img.used} von ${img.limit} verwendet`;
      }
      if (barEl) {
        if (img.unlimited) {
          barEl.style.width = '100%';
          barEl.className   = 'usage-bar-fill unlimited';
        } else {
          const pct = img.limit > 0 ? Math.min(100, (img.used / img.limit) * 100) : 0;
          barEl.style.width = `${pct}%`;
          barEl.className   = 'usage-bar-fill'
            + (pct >= 90 ? ' danger' : pct >= 65 ? ' warning' : '');
        }
      }

      // TTS Premium usage (ElevenLabs)
      _updateTTSUsage(me.tts_usage);

      // Chatterbox usage counter (informational, no limit)
      const youraiUsageEl = document.getElementById('ttsYourAIUsage');
      if (youraiUsageEl && me.yourai_tts_usage) {
        const used = me.yourai_tts_usage.used || 0;
        if (used > 0) {
          youraiUsageEl.textContent = `${used}× diesen Monat genutzt`;
          youraiUsageEl.style.display = '';
        }
      }

      // Session UUID anzeigen
      const uuidEl = document.getElementById('profileSessionUUID');
      if (uuidEl && typeof YourAIUUID !== 'undefined') {
        uuidEl.textContent = YourAIUUID.get();
      }

      // Store role + hide admin-only elements for non-admins
      _userRole = me.access_role || 'chat';
      const isAdmin = _userRole === 'admin';
      document.querySelectorAll('.admin-only-card').forEach(el => {
        el.style.display = isAdmin ? '' : 'none';
      });

    } catch (e) {
      console.error('❌ User profile load failed:', e);
    }
  }

  // ─── Init ─────────────────────────────────────────────────────
  let _pollInterval = null;

  async function init() {
    initTTSSettings();                // sync — lädt aus localStorage
    await loadUserProfile();          // sets _userRole first
    if (_userRole === 'admin') {
      load();
      _loadVolume();
      refreshBrainStatus();
    }
  }

  function startPolling() {
    if (_userRole !== 'admin') return;
    if (!_pollInterval) {
      _pollInterval = setInterval(refreshBrainStatus, 5000);
    }
  }

  function stopPolling() {
    if (_pollInterval) {
      clearInterval(_pollInterval);
      _pollInterval = null;
    }
  }

  // ─── DSGVO Art. 15: Meine Daten anzeigen ────────────────────
  let _myDataLoaded = false;

  async function _loadMyData() {
    const panel      = document.getElementById('myDataPanel');
    const loading    = document.getElementById('myDataLoading');
    const content    = document.getElementById('myDataContent');
    const errorEl    = document.getElementById('myDataError');
    const diaryEl    = document.getElementById('myDataDiaryCount');
    const factCountEl= document.getElementById('myDataFactCount');
    const factsWrap  = document.getElementById('myDataFactsList');
    const toggleBtn  = document.getElementById('myDataToggleFacts');
    if (!panel) return;

    // Toggle panel visibility
    if (!panel.hidden && _myDataLoaded) {
      panel.hidden = true;
      document.getElementById('showMyDataBtn').textContent = '🔍 Meine Daten';
      return;
    }
    panel.hidden = false;
    document.getElementById('showMyDataBtn').textContent = '🔼 Ausblenden';
    if (_myDataLoaded) return;

    loading.hidden  = false;
    content.hidden  = true;
    errorEl.hidden  = true;

    try {
      const res = await fetch('/api/my_data', { headers: _authHeaders() });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const d = await res.json();

      diaryEl.textContent    = `${d.diary_count} Einträge`;
      factCountEl.textContent = `${d.memory_facts.length} Fakten`;

      // Memory facts list
      factsWrap.innerHTML = '';
      if (d.memory_facts.length > 0) {
        d.memory_facts.forEach(f => {
          const el = document.createElement('div');
          el.className = 'my-data-fact';
          el.textContent = f;
          factsWrap.appendChild(el);
        });
        toggleBtn.hidden = false;
        toggleBtn.textContent = `▶ ${d.memory_facts.length} Fakten anzeigen`;
        toggleBtn.onclick = () => {
          const open = !factsWrap.hidden;
          factsWrap.hidden = open;
          toggleBtn.textContent = open
            ? `▶ ${d.memory_facts.length} Fakten anzeigen`
            : `▼ ${d.memory_facts.length} Fakten ausblenden`;
        };
      }

      if (d.memory_error) errorEl.hidden = false;

      loading.hidden = true;
      content.hidden = false;
      _myDataLoaded  = true;

    } catch (e) {
      loading.hidden = true;
      errorEl.hidden = false;
      errorEl.textContent = `⚠️ Fehler beim Laden: ${e.message}`;
    }
  }

  document.getElementById('showMyDataBtn')?.addEventListener('click', _loadMyData);

  // ─── DSGVO: Meine Daten löschen ──────────────────────────────
  document.getElementById('deleteMyDataBtn')?.addEventListener('click', async () => {
    if (!confirm('Alle Diary-Einträge dieser Browser-Session löschen? Das kann nicht rückgängig gemacht werden.')) return;
    const btn = document.getElementById('deleteMyDataBtn');
    btn.disabled = true;
    btn.textContent = '⏳ Wird gelöscht...';
    try {
      const res = await fetch('/api/delete_my_data', { method: 'DELETE', headers: _authHeaders() });
      const data = await res.json();
      if (res.ok) {
        App.toast(`🗑️ ${data.message}`, 'success');
        btn.textContent = `✅ ${data.deleted} Einträge gelöscht`;
        // Reset data panel so it reloads fresh next time
        _myDataLoaded = false;
        const diaryEl = document.getElementById('myDataDiaryCount');
        if (diaryEl) diaryEl.textContent = '0 Einträge';
      } else {
        App.toast(`❌ ${data.detail || 'Fehler'}`, 'error');
        btn.disabled = false;
        btn.textContent = '🗑️ Meine Daten löschen';
      }
    } catch (e) {
      App.toast(`❌ ${e.message}`, 'error');
      btn.disabled = false;
      btn.textContent = '🗑️ Meine Daten löschen';
    }
  });

  return { init, refreshBrainStatus, startPolling, stopPolling, applyMaintenance: _applyMaintenance };
})();
