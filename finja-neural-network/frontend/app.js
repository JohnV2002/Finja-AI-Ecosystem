/*
  YourAI Dashboard App Shell
  =========================
  Frontend module for the YourAI dashboard.

  Main Responsibilities:
  - Manage global dashboard state, tabs, users, modes, and WebSocket connectivity.
  - Route backend events to chat, debug, analytics, and config modules.
  - Provide shared toast and utility helpers for frontend modules.

  Side Effects:
  - Reads and writes browser localStorage.
  - Opens WebSocket connections to the dashboard server.
  - Updates global DOM state and visible notifications.
*/
const App = (() => {
  // ─── DOM Refs ───────────────────────────────────────────────
  const connDot     = document.getElementById('connDot');
  const connLabel   = document.getElementById('connLabel');
  const modeToggle  = document.getElementById('modeToggle');
  const userSelect  = document.getElementById('userSelect');
  const userBadge   = document.getElementById('userBadge');
  const addUserBtn   = document.getElementById('addUserBtn');
  const userModal    = document.getElementById('userModal');
  const toastEl     = document.getElementById('toastContainer');

  // ─── State ──────────────────────────────────────────────────
  let ws            = null;
  let wsRetryDelay  = 1000;
  let wsRetryTimer  = null;
  let wsRetryStopped = false;  // Stop retries on auth error
  const accessKey   = localStorage.getItem('yourai_access_key');
  let userRole      = 'guest';
  let currentUser   = { key: 'admin', id: 'admin', display: 'Admin (Admin)', role: 'admin' };
  let currentMode   = 'yourai';
  let activeTab     = 'chat';
  let maintenancePollTimer = null;

  // ─── Auth Helper ─────────────────────────────────────────────
  function _authHeaders() {
    return YourAIAPI.authHeaders();
  }

  // ─── WebSocket ───────────────────────────────────────────────

  function _connectWs() {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    // WebSocket cannot send custom headers, so the key stays in the URL for this connection only.
    const wsUrl = `${proto}://${location.host}/ws` + (accessKey ? `?key=${accessKey}` : '');
    ws = new WebSocket(wsUrl);

    _setConnStatus('connecting');

    ws.onopen = () => {
      _setConnStatus('connected');
      wsRetryDelay = 1000;
    };

    ws.onclose = () => {
      _setConnStatus('disconnected');
      if (!wsRetryStopped) _scheduleRetry();
    };

    ws.onerror = () => {
      ws.close();
    };

    ws.onmessage = (event) => {
      let msg;
      try { msg = JSON.parse(event.data); }
      catch { return; }
      _handleMessage(msg);
    };
  }

  function _scheduleRetry() {
    clearTimeout(wsRetryTimer);
    wsRetryTimer = setTimeout(() => {
      // Exponential backoff: 1s → 2s → 4s → 8s → ... → max 60s
      // Slow enough to not block the port on server restart
      wsRetryDelay = Math.min(wsRetryDelay * 2, 60000);
      _connectWs();
    }, wsRetryDelay);
  }

  function _setConnStatus(state) {
    connDot.className = `conn-dot ${state}`;
    const labels = {
      connected:    'verbunden',
      disconnected: 'getrennt',
      connecting:   'verbinde...',
    };
    connLabel.textContent = labels[state] || state;
  }

  // ─── Message handling ─────────────────────────────────────────

  function _handleMessage(msg) {
    switch (msg.type) {
      case 'event':
        Debug.addEvent(msg.data);

        // Chat display: only show events for the current user (or events without for_user = own session)
        // for_user can be user_id ("admin") or user_key ("admin") — check both
        const _fu = (msg.data.for_user || '').toLowerCase();
        const _isMyEvent = !_fu
          || _fu === currentUser.key.toLowerCase()
          || _fu === (currentUser.id || '').toLowerCase();

        // Pipeline end with yourai response → forward to chat (only own)
        if (msg.data.event_type === 'pipeline_end' && msg.data.content && _isMyEvent) {
          Chat.showYourAIMessage(
            msg.data.content,
            msg.data.tracking_id || null,
            msg.data.model || null,
            msg.data.expert_domain || null,
            msg.data.expert_model  || null
          );
        }
        // Image generated → show in chat (only own) + refresh usage counter
        if (msg.data.event_type === 'image_ready') {
          if (_isMyEvent) {
            console.log('🎨 [YourAI] image_ready event:', { image_url: msg.data.image_url, for_user: msg.data.for_user });
            if (msg.data.image_url) {
              Chat.showYourAIImage(msg.data.image_url, msg.data.content || '');
            }
          }
          // Refresh usage pill after short delay (let disk write finish)
          setTimeout(() => Chat.refreshImageUsage(), 1500);
        }
        if (msg.data.event_type === 'system_info' && msg.data.node_name === 'queue_status' && _isMyEvent) {
          Chat.handleMessage(msg);
        }
        // Promise confirmation popup
        if (msg.data.event_type === 'promise_confirmation' && _isMyEvent) {
          Chat.showPromiseConfirmation(msg.data);
        }
        break;

      case 'user_info':
        _applyUserInfo(msg.data);
        break;

      case 'user_changed':
        _applyUserInfo(msg.data);
        break;
      case 'mode_changed':
        _applyUserInfo(msg.data);
        // Reload chat from mode-specific localStorage (after mode is updated)
        Chat.reloadForMode();
        break;

      case 'input_received':
        // Server confirmed it received our input — handled by chat
        break;

      case 'clear_events':
        Debug.clear();
        break;

      case 'maintenance_error':
        Chat.showMaintenanceError(msg.data || {});
        break;

      case 'config_changed':
        if (msg.data?.key === 'USE_MAINTENANCE') {
          const active = Boolean(msg.data.value);
          const draining = Boolean(msg.data.draining);
          const role = (currentUser.role || '').toLowerCase();
          _updateMaintenanceBadge(role === 'admin' && (active || draining));
          if (typeof Config !== 'undefined') Config.applyMaintenance({ active, draining, pending: msg.data.pending || 0 });
          toast(draining ? 'Maintenance wird vorbereitet.' : (active ? 'Maintenance Mode ist jetzt aktiv.' : 'Maintenance Mode ist aus.'), 'info');
        } else if (typeof Config !== 'undefined') {
          Config.loadUserProfile?.();
        }
        break;

      case 'maintenance_status':
        _handleMaintenanceStatus(msg.data || {});
        break;

      case 'permissions':
        _applyPermissions(msg.data);
        break;

      case 'force_refresh':
        // Server requests full page reload (e.g. maintenance mode toggled)
        console.log('🔄 Force refresh requested:', msg.data?.reason);
        location.reload();
        return;  // don't process further

      case 'auth_error':
        wsRetryStopped = true;  // STOP reconnecting on denied key!
        clearTimeout(wsRetryTimer);
        _showAuthError(msg.data);
        break;

      default:
        // Let chat handle other types
        Chat.handleMessage(msg);
    }
  }

  function _handleMaintenanceStatus(data) {
    const role = (currentUser.role || userRole || '').toLowerCase();
    const isAdmin = role === 'admin';
    if (typeof Config !== 'undefined') Config.applyMaintenance(data);
    _updateMaintenanceBadge(isAdmin && (data.active || data.draining));
    if (!isAdmin && data.active) {
      location.reload();
    }
  }

  async function _pollMaintenanceStatus() {
    if (!accessKey) return;
    try {
      const res = await fetch('/api/maintenance/status?_=' + Date.now(), {
        headers: _authHeaders(),
        cache: 'no-store',
      });
      if (!res.ok) return;
      const data = await res.json();
      _handleMaintenanceStatus(data);
    } catch (_) {}
  }

  function _startMaintenancePolling() {
    if (maintenancePollTimer) return;
    maintenancePollTimer = setInterval(_pollMaintenanceStatus, 12000);
    setTimeout(_pollMaintenanceStatus, 1500);
  }

  function _applyUserInfo(data) {
    // Fill user dropdown
    if (data.available_users) {
      userSelect.innerHTML = '';
      data.available_users.forEach(u => {
        const opt = document.createElement('option');
        opt.value = u.key;
        opt.textContent = u.name;
        if (u.key === data.current_user_key) opt.selected = true;
        userSelect.appendChild(opt);
      });
    }

    // Update badge
    const role = (data.available_users || [])
      .find(u => u.key === data.current_user_key)?.role || 'guest';
    userBadge.textContent = role;
    userBadge.className = `user-badge ${role}`;

    // Update current user state
    currentUser = {
      key:     data.current_user_key  || 'admin',
      id:      data.current_user_id   || data.current_user_key || 'admin',
      display: data.current_user      || 'Admin',
      role,
      language: data.current_language || 'en',
    };

    // Respect server-side can_switch_user flag
    if (data.can_switch_user === false) {
      userSelect.disabled = true;
      userSelect.style.pointerEvents = 'none';
      userSelect.style.opacity = '0.6';
      if (addUserBtn) addUserBtn.style.display = 'none';
    }

    // Update mode toggle
    if (data.current_mode) {
      currentMode = data.current_mode;
      _updateModeBtn();
    }

    // Update chat user label
    Chat.updateUserLabel(currentUser.display);
  }

  function _applyPermissions(data) {
    userRole = data.role || 'guest';
    console.log('🔐 Permissions applied:', userRole);

    // Filter tabs based on role
    const tabs = {
      chat:   ['chat', 'debug', 'admin'],
      debug:  ['debug', 'admin'],
      analytics: ['debug', 'admin'],
      config: ['chat', 'debug', 'admin']  // all roles see Config (admin-only cards hidden by config.js)
    };

    document.querySelectorAll('.tab-btn').forEach(btn => {
      const tabName = btn.dataset.tab;
      const allowedRoles = tabs[tabName] || [];
      if (allowedRoles.includes(userRole)) {
        btn.style.display = '';
      } else {
        btn.style.display = 'none';
      }
    });

    // If current tab is hidden, switch to chat
    const allowedForCurrent = tabs[activeTab] || [];
    if (!allowedForCurrent.includes(userRole)) {
      document.querySelector('.tab-btn[data-tab="chat"]')?.click();
    }

    // Security: Hide user selector + add user button for non-admins
    const canSwitch = data.can_switch_user || false;
    userSelect.disabled = !canSwitch;
    if (!canSwitch) {
      userSelect.style.pointerEvents = 'none';
      userSelect.style.opacity = '0.6';
    }
    if (addUserBtn) {
      addUserBtn.style.display = canSwitch ? '' : 'none';
    }

    // Security: Hide mode toggle if can_altpersona is false
    const canAltPersona = data.can_altpersona || false;
    if (modeToggle) {
      modeToggle.style.display = canAltPersona ? '' : 'none';
    }

    // Admin escape hatch: wenn Maintenance aktiv ist, floating Button zeigen
    _updateMaintenanceBadge(userRole === 'admin' && data.maintenance === true);
  }

  let _maintenanceBadge = null;

  function _updateMaintenanceBadge(show) {
    if (!show) {
      _maintenanceBadge?.remove();
      _maintenanceBadge = null;
      return;
    }
    if (_maintenanceBadge) return; // already shown
    const btn = document.createElement('button');
    btn.id = 'adminMaintenanceEscape';
    btn.textContent = '🚧 Maintenance — Ausschalten';
    btn.style.cssText = [
      'position:fixed', 'bottom:80px', 'left:50%', 'transform:translateX(-50%)',
      'z-index:9999', 'padding:10px 20px', 'border-radius:999px',
      'background:#e05555', 'color:#fff', 'border:none', 'cursor:pointer',
      'font-size:14px', 'font-weight:600', 'box-shadow:0 4px 20px rgba(0,0,0,0.4)',
    ].join(';');
    btn.addEventListener('click', async () => {
      btn.disabled = true;
      btn.textContent = '⏳ Wird ausgeschaltet...';
      try {
        const res = await fetch('/api/config', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', ..._authHeaders() },
          body: JSON.stringify({ key: 'USE_MAINTENANCE', value: false }),
        });
        if (res.ok) {
          toast('🚧 Maintenance ausgeschaltet!', 'success');
          _updateMaintenanceBadge(false);
          if (typeof Config !== 'undefined') Config.applyMaintenance(false);
        } else {
          toast('❌ Fehler beim Ausschalten', 'error');
          btn.disabled = false;
          btn.textContent = '🚧 Maintenance — Ausschalten';
        }
      } catch (e) {
        toast(`❌ ${e.message}`, 'error');
        btn.disabled = false;
        btn.textContent = '🚧 Maintenance — Ausschalten';
      }
    });
    document.body.appendChild(btn);
    _maintenanceBadge = btn;
  }

  function _showAuthError(message) {
    const overlay = document.createElement('div');
    overlay.className = 'auth-overlay';
    overlay.innerHTML = `
      <div class="auth-card">
        <h1>🛑 Access Denied</h1>
        <p>${message}</p>
        <p>Bitte öffne den Link erneut mit deinem <code>?key=...</code> Parameter.</p>
      </div>
    `;
    document.body.appendChild(overlay);
  }

  function _updateModeBtn() {
    modeToggle.className = `mode-toggle ${currentMode}`;
    modeToggle.textContent = currentMode === 'altpersona' ? '😈 AltPersona' : '🌸 YourAI';

    // Global body class for CSS theming (altpersona = purple, yourai = orange)
    document.body.classList.toggle('mode-altpersona', currentMode === 'altpersona');
    document.body.classList.toggle('mode-yourai', currentMode !== 'altpersona');

    // Update dynamic text elements
    const isAltPersona = currentMode === 'altpersona';
    const botName = isAltPersona ? 'AltPersona' : 'YourAI';
    const botEmoji = isAltPersona ? '😈' : '🦊';

    const typingInd = document.getElementById('typingIndicator');
    if (typingInd) typingInd.textContent = `${botName} tippt...`;

    const chatInput = document.getElementById('chatInput');
    if (chatInput) chatInput.placeholder = `Nachricht an ${botName}...`;

    const emptyMsg = document.querySelector('.chat-empty p');
    if (emptyMsg) emptyMsg.textContent = `Schreib etwas und ${botName} antwortet...`;

    const emptyFox = document.querySelector('.chat-empty-fox');
    if (emptyFox) emptyFox.textContent = botEmoji;
  }

  // ─── Tab Router ───────────────────────────────────────────────

  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const tab = btn.dataset.tab;
      if (tab === activeTab) return;

      // Deactivate old
      document.querySelector(`.tab-btn[data-tab="${activeTab}"]`)?.classList.remove('active');
      document.getElementById(`tab-${activeTab}`)?.classList.remove('active');
      Debug.onTabActive(activeTab === 'debug' ? false : null);
      if (activeTab === 'analytics' && typeof Analytics !== 'undefined') Analytics.onActive(false);

      // Activate new
      btn.classList.add('active');
      document.getElementById(`tab-${tab}`)?.classList.add('active');
      activeTab = tab;

      if (tab === 'debug') Debug.onTabActive(true);
      if (tab === 'analytics' && typeof Analytics !== 'undefined') Analytics.onActive(true);
      if (tab === 'config') {
        Config.loadUserProfile();
        Config.loadTokenUsageOverview();
        Config.refreshBrainStatus();
        Config.startPolling();
        Config.startPollingSubconscious();
      }
      else { Config.stopPolling(); Config.stopPollingSubconscious(); }
    });
  });

  // ─── User Selector ────────────────────────────────────────────
  userSelect.addEventListener('change', () => {
    sendWs({ type: 'switch_user', user_key: userSelect.value });
  });

  // ─── User Creation ───────────────────────────────────────────
  
  function _openUserModal() {
    userModal.classList.add('active');
    document.getElementById('new_user_key').focus();
  }

  function _closeUserModal() {
    userModal.classList.remove('active');
    // Clear inputs
    ['new_user_key', 'new_display_name', 'new_description', 'new_access_key'].forEach(id => {
      document.getElementById(id).value = '';
    });
    document.getElementById('grant_dashboard').checked = false;
    document.getElementById('new_can_altpersona').checked = false;
    document.getElementById('dashboard_fields').style.display = 'none';
  }

  function _generateRandomStr(length) {
    const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
    let result = '';
    for (let i = 0; i < length; i++) result += chars.charAt(Math.floor(Math.random() * chars.length));
    return result;
  }

  function _updateMagicLink() {
    const key = document.getElementById('new_access_key').value;
    const linkEl = document.getElementById('magicLink');
    if (key) {
      linkEl.textContent = `${location.protocol}//${location.host}/?key=${key}`;
    } else {
      linkEl.textContent = '...';
    }
  }

  function _generateAccessKey() {
    const role = document.getElementById('new_access_role').value;
    const randomPart = _generateRandomStr(64);
    const key = `${role}-${randomPart}`;
    document.getElementById('new_access_key').value = key;
    _updateMagicLink();
  }

  document.getElementById('grant_dashboard')?.addEventListener('change', (e) => {
    document.getElementById('dashboard_fields').style.display = e.target.checked ? 'block' : 'none';
    if (e.target.checked && !document.getElementById('new_access_key').value) {
      _generateAccessKey();
    }
  });

  document.getElementById('new_access_role')?.addEventListener('change', () => {
    if (document.getElementById('grant_dashboard').checked) _generateAccessKey();
  });

  document.getElementById('btnGenerateKey')?.addEventListener('click', _generateAccessKey);

  async function _handleUserCreate() {
    const key   = document.getElementById('new_user_key').value.trim();
    const name  = document.getElementById('new_display_name').value.trim();
    const role  = document.getElementById('new_user_role').value;
    const desc  = document.getElementById('new_description').value.trim();
    const lang  = document.getElementById('new_language').value;

    const grantDashboard = document.getElementById('grant_dashboard').checked;
    const accessRole = document.getElementById('new_access_role').value;
    const newUserAccessKey = document.getElementById('new_access_key').value; // Key des NEUEN Users (nicht Admin-Key!)
    const canAltPersona = document.getElementById('new_can_altpersona').checked;

    if (!key) {
      toast('ID / Key ist erforderlich!', 'error');
      return;
    }

    try {
      const res = await fetch('/api/create_user', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ..._authHeaders() },
        body: JSON.stringify({
          user_key: key,
          display_name: name,
          role: role,
          description: desc,
          language: lang,
          grant_dashboard: grantDashboard,
          access_key: newUserAccessKey,
          access_role: accessRole,
          can_altpersona: canAltPersona
        })
      });
      const data = await res.json();
      if (data.status === 'ok') {
        toast(data.message, 'success');
        _closeUserModal();
        // Server sends 'user_info' via WS, which refreshes the list
        // but we switch manually to be fast
        sendWs({ type: 'switch_user', user_key: key });
      } else {
        toast(data.message || 'Fehler beim Erstellen', 'error');
      }
    } catch (e) {
      toast(`API Fehler: ${e.message}`, 'error');
    }
  }

  addUserBtn?.addEventListener('click', _openUserModal);
  document.getElementById('closeUserModal')?.addEventListener('click', _closeUserModal);
  document.getElementById('cancelUserCreate')?.addEventListener('click', _closeUserModal);
  document.getElementById('confirmUserCreate')?.addEventListener('click', _handleUserCreate);

  // ─── Mode Toggle ─────────────────────────────────────────────
  modeToggle.addEventListener('click', () => {
    const next = currentMode === 'yourai' ? 'altpersona' : 'yourai';
    sendWs({ type: 'switch_mode', mode: next });
  });

  // ─── Public: send WebSocket message ──────────────────────────
  function sendWs(obj) {
    if (ws?.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(obj));
      return true;
    }
    toast('Keine Verbindung zum Dashboard. Nachricht wurde nicht gesendet.', 'error');
    return false;
  }

  // ─── Public: toast notifications ─────────────────────────────
  function toast(message, type = 'info', durationMs = 3500) {
    const allowed = ['success', 'error', 'info'];
    const safeType = allowed.includes(type) ? type : 'info';
    const icons = { success: '✅', error: '❌', info: 'ℹ️' };
    const t = document.createElement('div');
    t.className = `toast ${safeType}`;
    t.textContent = `${icons[safeType] || 'ℹ️'} ${message}`;
    toastEl.appendChild(t);

    setTimeout(() => {
      t.classList.add('out');
      t.addEventListener('animationend', () => t.remove(), { once: true });
    }, durationMs);
  }

  // ─── Public: current user display name ───────────────────────
  function getCurrentUserDisplay() {
    return currentUser.display;
  }

  function getCurrentLanguage() {
    return currentUser.language || 'en';
  }

  // ─── Public: current mode (yourai/altpersona) ──────────────────────
  function getMode() {
    return currentMode;
  }

  function getBotName() {
    return currentMode === 'altpersona' ? 'AltPersona 😈' : 'YourAI';
  }

  function getBotClass() {
    return currentMode === 'altpersona' ? 'altpersona' : 'yourai';
  }

  function getAccessKey() {
    return accessKey;
  }

  // ─── Version + aktives LLM laden ─────────────────────────────
  // Price list for image models used by the UI display.
  const _IMAGE_MODEL_PRICES = {
    'bytedance-seed/seedream-4.5':              '$0.04/img ✅ ZDR',
    'sourceful/riverflow-v2-fast':              '$0.02/img ✅ ZDR',
    'sourceful/riverflow-v2-standard-preview':  '$0.035/img ✅ ZDR',
    'sourceful/riverflow-v2-max-preview':       '$0.075/img ✅ ZDR',
    'black-forest-labs/flux.2-pro':             '~$0.03/MP ⚠️ no ZDR',
  };

  async function _loadImageModels() {
    const sel = document.getElementById('imageModelSelect');
    const priceEl = document.getElementById('imageModelPrice');
    if (!sel) return;
    try {
      const res = await fetch('/api/image_models', { headers: _authHeaders() });
      if (!res.ok) return;
      const data = await res.json();
      sel.innerHTML = '';
      (data.models || []).forEach(m => {
        const opt = document.createElement('option');
        opt.value = m;
        const short = m.split('/').pop();
        opt.textContent = short;
        if (m === data.active) opt.selected = true;
        sel.appendChild(opt);
      });
      if (priceEl) priceEl.textContent = _IMAGE_MODEL_PRICES[data.active] || '';
      sel.onchange = async () => {
        const newModel = sel.value;
        await fetch('/api/config', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', ..._authHeaders() },
          body: JSON.stringify({ key: 'IMAGE_MODEL', value: newModel }),
        });
        if (priceEl) priceEl.textContent = _IMAGE_MODEL_PRICES[newModel] || '';
      };
    } catch { /* ignore */ }
  }

  async function _loadVersion() {
    try {
      const res = await fetch('/api/version');
      if (!res.ok) return;
      const data = await res.json();

      // Version Badge unten rechts
      const badge = document.getElementById('appVersionBadge');
      if (badge && data.version) badge.textContent = `v${data.version}`;

      // LLM Pill im Debug Tab
      const llmEl = document.getElementById('debugLlmModel');
      if (llmEl && data.model) llmEl.textContent = data.model;
    } catch { /* ignore — kein Auth nötig, aber Server könnte noch starten */ }
  }

  // ─── Boot ─────────────────────────────────────────────────────
  function _boot() {
    _connectWs();
    Config.init();
    // Start on debug tab active = false
    Debug.onTabActive(false);
    _loadVersion();
    _loadImageModels();
    _startMaintenancePolling();
  }

  _boot();

  return { sendWs, toast, getCurrentUserDisplay, getCurrentLanguage, getAccessKey, getMode, getBotName, getBotClass };
})();
