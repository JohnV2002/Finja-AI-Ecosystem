/* ══════════════════════════════════════════════════════════════════
   debug.js — Pipeline Debug Feed (with persistent history)
══════════════════════════════════════════════════════════════════ */

const Debug = (() => {
  const feedEl      = document.getElementById('debugFeed');
  const badgeEl     = document.getElementById('eventBadge');
  const clearBtn    = document.getElementById('clearDebugBtn'); // may be null (removed)
  const filtersEl   = document.getElementById('debugFilters');

  function _authHeaders() {
    const h = {};
    const k = localStorage.getItem('yourai_access_key');
    if (k) h['Authorization'] = `Bearer ${k}`;
    return h;
  }

  let eventCount    = 0;
  let activeFilter  = 'all';
  let isDebugTab    = false;  // tracked by app.js
  const _seenKeys   = new Set(); // Duplikat-Filter bei WS-Reconnect

  // ─── History state ──────────────────────────────────────────
  let _totalOnServer  = null;   // total events known on server
  let _loadedCount    = 0;      // how many we've loaded so far
  let _isLoadingMore  = false;

  // ─── Event type → icon + node color class ───────────────────
  const EVENT_META = {
    pipeline_start:  { icon: '🚀', color: 'system' },
    pipeline_end:    { icon: '✅', color: 'system' },
    node_start:      { icon: '▶️', color: null },
    node_end:        { icon: '⏹️', color: null },
    node_error:      { icon: '❌', color: null },
    llm_call:        { icon: '📡', color: null },
    llm_thinking:    { icon: '🤔', color: null },
    llm_response:    { icon: '💬', color: null },
    llm_error:       { icon: '⚠️', color: null },
    memory_search:   { icon: '🔍', color: 'memory' },
    memory_found:    { icon: '🧠', color: 'memory' },
    memory_save:     { icon: '💾', color: 'memory' },
    system_info:     { icon: 'ℹ️', color: null },
    system_error:    { icon: '🔥', color: null },
    user_switch:     { icon: '👤', color: 'system' },
    system_prompt:   { icon: '📋', color: 'system' },
    user_message:    { icon: '💬', color: 'system' },
    promise_event:   { icon: '🤝', color: 'system' },
    image_ready:     { icon: '🖼️', color: 'system' },
  };

  // ─── Node name → node-pill color class ───────────────────────
  function _nodeClass(nodeName) {
    const n = (nodeName || '').toLowerCase();
    if (n.includes('yourai'))   return 'yourai';
    if (n.includes('altpersona'))    return 'altpersona';
    if (n.includes('router'))  return 'router';
    if (n.includes('memory'))  return 'memory';
    if (n.includes('expert'))  return 'expert';
    if (n.includes('granite')) return 'granite';
    if (n.includes('stream'))  return 'stream';
    if (n.includes('tool') || n.includes('spotify') || n.includes('web') || n.includes('paperless') || n.includes('image') || n.includes('file') || n.includes('assistant')) return 'tool';
    return 'system';
  }

  // ─── Determine filter category for an event ──────────────────
  function _getFilterCategory(event) {
    const n = (event.node_name || '').toLowerCase();
    if (event.status === 'error')    return 'error';
    if (n.includes('yourai'))         return 'yourai';
    if (n.includes('router'))        return 'router';
    if (n.includes('expert'))        return 'expert';
    if (n.includes('memory'))        return 'memory';
    if (n.includes('tool') || n.includes('spotify') || n.includes('web') || n.includes('paperless') || n.includes('image') || n.includes('file') || n.includes('assistant')) return 'tool';
    return 'other';
  }

  // ─── Render a single event card ──────────────────────────────
  function _renderCard(ev) {
    const meta   = EVENT_META[ev.event_type] || { icon: '•', color: 'system' };
    const nClass = meta.color || _nodeClass(ev.node_name);

    const card = document.createElement('div');
    card.className = `event-card status-${ev.status || 'info'}`;
    card.dataset.filter = _getFilterCategory(ev);

    // Hidden if filtered
    if (activeFilter !== 'all' && card.dataset.filter !== activeFilter) {
      card.hidden = true;
    }

    // ── Header (always visible) ──────────────────────────────
    const header = document.createElement('div');
    header.className = 'event-header';

    const icon = document.createElement('span');
    icon.className = 'event-icon';
    icon.textContent = meta.icon;

    const titleArea = document.createElement('div');
    titleArea.className = 'event-title-area';

    const titleEl = document.createElement('div');
    titleEl.className = 'event-title';
    titleEl.textContent = ev.title || ev.event_type;

    const metaEl = document.createElement('div');
    metaEl.className = 'event-meta';

    const pill = document.createElement('span');
    pill.className = `node-pill ${nClass}`;
    pill.textContent = ev.node_name || 'system';
    metaEl.appendChild(pill);

    if (ev.model) {
      const modelPill = document.createElement('span');
      modelPill.className = 'node-pill';
      modelPill.style.backgroundColor = 'rgba(255, 255, 255, 0.15)';
      modelPill.textContent = ev.model;
      metaEl.appendChild(modelPill);
    }

    // Show for_user if present (so admin knows who this event was for)
    if (ev.for_user) {
      const userPill = document.createElement('span');
      userPill.className = 'node-pill';
      userPill.style.backgroundColor = 'rgba(188, 140, 255, 0.3)';
      userPill.textContent = '👤 ' + ev.for_user;
      metaEl.appendChild(userPill);
    }

    if (ev.timestamp) {
      const ts = document.createElement('span');
      ts.textContent = ev.timestamp;
      metaEl.appendChild(ts);
    }

    titleArea.appendChild(titleEl);
    titleArea.appendChild(metaEl);

    const expandIcon = document.createElement('span');
    expandIcon.className = 'event-expand-icon';
    expandIcon.textContent = '›';

    const durationEl = document.createElement('span');
    if (ev.duration_ms != null) {
      durationEl.className = 'duration-tag';
      durationEl.textContent = ev.duration_ms < 1000
        ? `${ev.duration_ms}ms`
        : `${(ev.duration_ms / 1000).toFixed(1)}s`;
    }

    header.appendChild(icon);
    header.appendChild(titleArea);
    if (durationEl.className) header.appendChild(durationEl);
    header.appendChild(expandIcon);

    // ── Body (expandable) ─────────────────────────────────────
    const body = document.createElement('div');
    body.className = 'event-body';

    function _addSection(label, text, extraClass) {
      if (!text) return;
      const sec = document.createElement('div');
      const lbl = document.createElement('div');
      lbl.className = 'event-section-label';
      lbl.textContent = label;
      const block = document.createElement('pre');
      block.className = `event-content-block ${extraClass || ''}`;
      block.textContent = text;
      sec.appendChild(lbl);
      sec.appendChild(block);
      body.appendChild(sec);
    }

    _addSection('Thinking', ev.thinking, 'event-thinking-block');
    _addSection('Content',  ev.content);
    _addSection('Input',    ev.input_data);
    _addSection('Raw',      ev.raw_output);
    _addSection('Error',    ev.error || ev.stack_trace, 'event-error-block');

    // Toggle expand on header click
    header.addEventListener('click', () => {
      if (!body.children.length) return;  // nothing to show
      card.classList.toggle('expanded');
    });

    // Hide expand icon if nothing to expand
    if (!body.children.length) {
      expandIcon.style.visibility = 'hidden';
    }

    // Auto-expand errors
    if (ev.status === 'error') {
      card.classList.add('expanded');
    }

    card.appendChild(header);
    if (body.children.length) card.appendChild(body);

    return card;
  }

  // ─── "Load Earlier" button ──────────────────────────────────
  function _createLoadBtn() {
    const btn = document.createElement('button');
    btn.className = 'load-earlier-btn';
    btn.id = 'loadEarlierBtn';
    btn.innerHTML = '⏫ Load earlier events';
    btn.addEventListener('click', loadEarlier);
    return btn;
  }

  function _updateLoadBtn() {
    let btn = document.getElementById('loadEarlierBtn');
    if (_totalOnServer !== null && _loadedCount < _totalOnServer) {
      if (!btn) {
        btn = _createLoadBtn();
        feedEl.insertBefore(btn, feedEl.firstChild);
      }
      const remaining = _totalOnServer - _loadedCount;
      btn.innerHTML = `⏫ Load earlier events (${remaining} more)`;
      btn.disabled = false;
    } else if (btn) {
      btn.remove();
    }
  }

  async function loadEarlier() {
    if (_isLoadingMore) return;
    _isLoadingMore = true;
    const btn = document.getElementById('loadEarlierBtn');
    if (btn) {
      btn.innerHTML = '⏳ Loading...';
      btn.disabled = true;
    }

    try {
      const res = await fetch(`/api/debug/history?offset=${_loadedCount}&limit=200`, { headers: _authHeaders() });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();

      _totalOnServer = data.total;

      // We get events newest-first from the API, so reverse to get chronological
      const events = data.events.reverse();
      const scrollH = feedEl.scrollHeight;

      // Remove the "Load earlier" button temporarily
      if (btn) btn.remove();

      // Remove empty state if present
      const emptyEl = feedEl.querySelector('.debug-empty');
      if (emptyEl) emptyEl.remove();

      // Prepend older events at the top
      let added = 0;
      const firstCard = feedEl.querySelector('.event-card');
      for (const ev of events) {
        const key = `${ev.timestamp}|${ev.event_type}|${ev.title}`;
        if (_seenKeys.has(key)) continue;
        _seenKeys.add(key);

        const card = _renderCard(ev);
        if (firstCard) {
          feedEl.insertBefore(card, firstCard);
        } else {
          feedEl.appendChild(card);
        }
        added++;
      }

      _loadedCount += added;
      console.log(`🦊 [Debug] Loaded ${added} earlier events (${_loadedCount}/${_totalOnServer} total)`);

      // Keep scroll position stable (don't jump to top)
      feedEl.scrollTop = feedEl.scrollHeight - scrollH + feedEl.scrollTop;

    } catch (e) {
      console.error('🦊 [Debug] Failed to load history:', e);
    } finally {
      _isLoadingMore = false;
      _updateLoadBtn();
    }
  }

  // ─── Fetch total count on init (for "load earlier" button) ──
  async function _initHistoryCount() {
    try {
      const res = await fetch('/api/debug/history?offset=0&limit=1', { headers: _authHeaders() });
      if (res.ok) {
        const data = await res.json();
        _totalOnServer = data.total;
        console.log(`🦊 [Debug] Server has ${_totalOnServer} events in history`);
      }
    } catch (e) { /* ignore - non-admin or offline */ }
  }

  // ─── Public: add a new event ─────────────────────────────────
  function addEvent(ev) {
    if (!feedEl) return;
    // Duplikat-Check: gleicher Timestamp + gleicher Typ + gleicher Titel = skip
    const key = `${ev.timestamp}|${ev.event_type}|${ev.title}`;
    if (_seenKeys.has(key)) return;
    _seenKeys.add(key);

    // Remove empty state
    const emptyEl = feedEl.querySelector('.debug-empty');
    if (emptyEl) emptyEl.remove();

    const card = _renderCard(ev);
    feedEl.appendChild(card);
    feedEl.scrollTop = feedEl.scrollHeight;

    // Track loaded count
    _loadedCount++;
    if (_totalOnServer !== null) _totalOnServer++;

    // Badge (only shown when not on debug tab)
    if (!isDebugTab && badgeEl) {
      eventCount++;
      badgeEl.textContent = eventCount > 99 ? '99+' : eventCount;
      badgeEl.hidden = false;
    }
  }

  // ─── Public: bulk-load historical events ─────────────────────
  function loadEvents(eventsArray) {
    eventsArray.forEach(addEvent);
    // After initial load from WS, check if there's more on server
    _initHistoryCount().then(_updateLoadBtn);
  }

  // ─── Public: clear ───────────────────────────────────────────
  function clear() {
    if (feedEl) feedEl.innerHTML = '<div class="debug-empty"><p>🔍 Warte auf Pipeline Events...</p></div>';
    eventCount = 0;
    _loadedCount = 0;
    if (badgeEl) badgeEl.hidden = true;
    _seenKeys.clear();
  }

  // ─── Public: called when switching to/from debug tab ─────────
  function onTabActive(active) {
    isDebugTab = active;
    if (active) {
      eventCount = 0;
      if (badgeEl) badgeEl.hidden = true;
      // Show load button when admin views debug tab
      _updateLoadBtn();
    }
  }

  // ─── Filter buttons ───────────────────────────────────────────
  if (filtersEl) {
    filtersEl.addEventListener('click', (e) => {
      const chip = e.target.closest('.filter-chip');
      if (!chip) return;

      filtersEl.querySelectorAll('.filter-chip').forEach(c => c.classList.remove('active'));
      chip.classList.add('active');
      activeFilter = chip.dataset.filter;

      // Show/hide cards
      if (feedEl) {
        feedEl.querySelectorAll('.event-card').forEach(card => {
          card.hidden = activeFilter !== 'all' && card.dataset.filter !== activeFilter;
        });
      }
    });
  }

  if (clearBtn) clearBtn.addEventListener('click', clear);

  return { addEvent, loadEvents, clear, onTabActive, loadEarlier };
})();
