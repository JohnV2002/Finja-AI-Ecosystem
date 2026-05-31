/*
  YourAI Config Usage Frontend
  ===========================
  Frontend module for the YourAI dashboard.

  Main Responsibilities:
  - Render configuration usage metrics and evaluation status.
  - Format usage snapshots for the dashboard.
  - Refresh usage data from backend endpoints.

  Side Effects:
  - Reads usage data from backend API endpoints.
  - Updates usage summary DOM nodes.
*/
const ConfigUsage = (() => {
  function formatTokens(n) {
    return new Intl.NumberFormat('de-DE').format(Number(n || 0));
  }

  function escapeHtml(text) {
    return String(text ?? '').replace(/[&<>"']/g, ch => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    })[ch]);
  }

  function updateTTSUsage(tts) {
    const el = document.getElementById('ttsPremiumUsage');
    const optEl = document.getElementById('ttsTierElOption');
    const bmcEl = document.getElementById('ttsBMCBtn');
    if (!el || !tts) return;

    if (tts.unlimited) {
      el.textContent = '∞ unbegrenzt';
      el.className = 'tts-premium-usage unlimited';
      optEl?.classList.remove('exhausted');
      if (bmcEl) bmcEl.hidden = true;
      return;
    }

    const left = tts.remaining ?? (tts.limit - tts.used);
    el.textContent = `${left} von ${tts.limit} gratis diesen Monat`;
    el.className = 'tts-premium-usage' + (left === 0 ? ' empty' : left === 1 ? ' low' : '');
    optEl?.classList.toggle('exhausted', left === 0);
    if (bmcEl) bmcEl.hidden = left > 0;
  }

  function updateTokenUsage(usage) {
    const token = usage || {};
    const numEl = document.getElementById('tokenUsageNumbers');
    const barEl = document.getElementById('tokenUsageBar');
    const used = Number(token.used || 0);
    const limit = Number(token.limit || 80000);
    const pct = limit > 0 ? Math.min(100, (used / limit) * 100) : 0;
    if (numEl) {
      numEl.textContent = `${formatTokens(used)} / ${formatTokens(limit)} Tokens`;
      numEl.title = token.session_id ? `Session: ${token.session_id}` : '';
    }
    if (barEl) {
      barEl.style.width = `${pct}%`;
      barEl.className = 'usage-bar-fill'
        + (pct >= 90 ? ' danger' : pct >= 65 ? ' warning' : '');
    }
  }

  function updateStyleUsage(style) {
    const data = style || {};
    const realtime = data.realtime || {};
    const snapshot = data.snapshot || {};
    const moodEl = document.getElementById('profileStyleMood');
    const compactEl = document.getElementById('profileStyleCompact');
    const detailsEl = document.getElementById('profileStyleDetails');
    const metaEl = document.getElementById('profileStyleMeta');
    const realtimeCount = Number(realtime.msg_count || 0);
    const snapshotCount = Number(snapshot.msg_count || 0);
    const preferSnapshot = snapshot.compact && snapshotCount >= realtimeCount;
    const primary = preferSnapshot ? snapshot : realtime;
    const secondary = preferSnapshot ? realtime : snapshot;
    const mood = primary.mood || secondary.mood || 'neutral';
    const energy = primary.energy || secondary.energy || '';
    const compact = primary.compact || secondary.compact || 'No analysis yet';
    if (moodEl) {
      moodEl.textContent = energy ? `${mood} / ${energy}` : mood;
      moodEl.dataset.role = mood;
    }
    if (compactEl) compactEl.textContent = compact;
    if (detailsEl) {
      const detailRows = [
        ['Baseline', snapshot.baseline],
        ['Subtext', snapshot.subtext],
        ['YourAI-Tuning', snapshot.response_tuning],
        ['Prediction', snapshot.prediction],
        ['Signale', snapshot.signals || (Array.isArray(realtime.signals) ? realtime.signals.join(', ') : realtime.signals)],
      ].filter(([, value]) => String(value || '').trim());

      detailsEl.hidden = !detailRows.length;
      detailsEl.innerHTML = detailRows.map(([label, value]) => `
        <div class="profile-style-detail-row">
          <span>${escapeHtml(label)}</span>
          <p>${escapeHtml(value)}</p>
        </div>
      `).join('');
    }
    if (metaEl) {
      const count = Number(data.msg_count || realtime.msg_count || snapshot.msg_count || 0);
      const next = Number(data.next_snapshot_in ?? realtime.next_snapshot_in ?? 0);
      const snap = snapshot.snapshot_at ? `Snapshot: ${snapshot.snapshot_at}` : 'Snapshot wartet';
      metaEl.textContent = `${count} Nachrichten · nächstes LLM-Eval in ${next} · ${snap}`;
    }
  }

  function renderTokenUsageOverview(data, listEl) {
    const sessions = data.sessions || [];
    if (!sessions.length) {
      const stale = data.stale_count || 0;
      listEl.innerHTML = `<div class="config-loading">Keine aktive Token-Session${stale ? ` (${stale} stale ausgeblendet)` : ''}</div>`;
      return;
    }

    listEl.innerHTML = sessions.slice(0, 12).map(s => {
      const pct = Math.min(100, Number(s.percent || 0));
      const level = s.level || (pct >= 90 ? 'danger' : pct >= 65 ? 'warning' : 'ok');
      const name = escapeHtml(s.display_name || s.user_key || s.session_id);
      const sid = escapeHtml(s.session_id || '');
      const age = Number(s.age_seconds || 0);
      const ageLabel = age < 60 ? 'gerade aktiv' : `aktiv vor ${Math.floor(age / 60)} min`;
      return `
        <div class="token-usage-item ${level}">
          <div class="token-usage-top">
            <span class="token-usage-name">${name}</span>
            <span class="token-usage-num">${formatTokens(s.used)} / ${formatTokens(s.limit || 80000)}</span>
          </div>
          <div class="usage-bar-track">
            <div class="usage-bar-fill ${level === 'danger' ? 'danger' : level === 'warning' ? 'warning' : ''}" style="width:${pct}%"></div>
          </div>
          <div class="token-usage-session">${sid} · ${ageLabel}</div>
        </div>`;
    }).join('');
  }

  function renderTokenUsageError(listEl) {
    listEl.innerHTML = '<div class="config-loading" style="color:var(--accent-red)">Token Usage konnte nicht geladen werden</div>';
  }

  return { updateTTSUsage, updateTokenUsage, updateStyleUsage, renderTokenUsageOverview, renderTokenUsageError };
})();
