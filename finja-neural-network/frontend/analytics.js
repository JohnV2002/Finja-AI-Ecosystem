/*
  YourAI Analytics Frontend
  ========================
  Frontend module for the YourAI dashboard.

  Main Responsibilities:
  - Render dashboard analytics, health, timeline, and cost summaries.
  - Refresh analytics panels from backend API responses.
  - Handle admin-only analytics cleanup actions.

  Side Effects:
  - Reads analytics data from backend API endpoints.
  - Updates dashboard DOM nodes and may request analytics deletion.
*/
const Analytics = (() => {
  let initialized = false;
  let active = false;
  let refreshTimer = null;

  function $(id) {
    return document.getElementById(id);
  }

  function escapeHtml(text) {
    return String(text ?? '').replace(/[&<>"']/g, ch => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    })[ch]);
  }

  function fmtNumber(value) {
    return new Intl.NumberFormat('de-DE').format(Number(value || 0));
  }

  function fmtPct(value) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return '--';
    return `${(Number(value) * 100).toFixed(1)}%`;
  }

  function fmtMs(value) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return '--';
    const ms = Number(value);
    if (ms >= 1000) {
      const sec = ms / 1000;
      return `${sec >= 10 ? sec.toFixed(0) : sec.toFixed(1)}s`;
    }
    return `${Math.round(ms)}ms`;
  }

  function fmtPerSec(value) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return '--';
    return `${Number(value).toFixed(1)}/s`;
  }

  function fmtUsd(value) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return '--';
    const num = Number(value);
    if (num === 0) return '$0.0000';
    if (num < 0.01) return `$${num.toFixed(6)}`;
    return `$${num.toFixed(4)}`;
  }

  function fmtTime(value) {
    if (!value) return 'noch keine Daten';
    try {
      return new Date(value).toLocaleString('de-DE', {
        hour: '2-digit',
        minute: '2-digit',
        day: '2-digit',
        month: '2-digit'
      });
    } catch (_) {
      return String(value);
    }
  }

  function selectedHours() {
    return Number($('analyticsWindow')?.value || 24);
  }

  function selectedFilters() {
    return {
      user: $('analyticsUserFilter')?.value || '',
      source: $('analyticsSourceFilter')?.value || '',
      model: $('analyticsModelFilter')?.value || ''
    };
  }

  function queryParams(hours) {
    const params = new URLSearchParams({
      hours: String(hours)
    });
    const filters = selectedFilters();
    Object.entries(filters).forEach(([key, value]) => {
      if (value) params.set(key, value);
    });
    return params.toString();
  }

  function bucketMinutes(hours) {
    if (hours <= 12) return 30;
    if (hours <= 72) return 60;
    return 240;
  }

  function setText(id, value) {
    const el = $(id);
    if (el) el.textContent = value;
  }

  function setLoading(isLoading) {
    $('analyticsRefreshBtn')?.toggleAttribute('disabled', isLoading);
    const btn = $('analyticsRefreshBtn');
    if (btn) btn.textContent = isLoading ? 'Lade...' : 'Refresh';
  }

  function syncSelectOptions(id, values, label) {
    const el = $(id);
    if (!el) return;
    const current = el.value;
    const list = Array.isArray(values) ? values : [];
    el.innerHTML = [
      `<option value="">${escapeHtml(label)}</option>`,
      ...list.map(value => `<option value="${escapeHtml(value)}">${escapeHtml(value)}</option>`)
    ].join('');
    if (current && list.includes(current)) {
      el.value = current;
    }
  }

  function renderFilterOptions(summary) {
    const options = summary?.filters?.options || {};
    syncSelectOptions('analyticsUserFilter', options.users, 'All users');
    syncSelectOptions('analyticsSourceFilter', options.sources, 'All sources');
    syncSelectOptions('analyticsModelFilter', options.models, 'All models');
  }

  function renderKpis(summary) {
    setText('analyticsRequests', fmtNumber(summary.requests));
    setText('analyticsRequestsSub', `${summary.window_hours || selectedHours()}h Fenster`);
    setText('analyticsErrorRate', fmtPct(summary.error_rate));
    const inbox = summary.error_inbox || {};
    setText('analyticsErrorsSub', `${fmtNumber(summary.errors)} Events | ${fmtNumber(inbox.unseen)} unseen`);

    const e2e = summary.e2e_ms || {};
    setText('analyticsE2E', `${fmtMs(e2e.p50)} / ${fmtMs(e2e.p95)}`);
    setText('analyticsE2ESub', `avg ${fmtMs(e2e.avg)} | max ${fmtMs(e2e.max)}`);

    const llm = summary.llm_ms || {};
    setText('analyticsLLM', fmtMs(llm.p50));
    setText('analyticsLLMSub', `p95 ${fmtMs(llm.p95)} | n=${fmtNumber(llm.count)}`);

    const ttft = summary.ttft_ms || {};
    setText('analyticsTTFT', fmtMs(ttft.p50));
    setText('analyticsTTFTSub', `p95 ${fmtMs(ttft.p95)} | n=${fmtNumber(ttft.count)}`);

    const tps = summary.output_tokens_per_sec || {};
    const tokens = summary.tokens || {};
    setText('analyticsTPS', fmtPerSec(tps.avg));
    setText('analyticsTPSSub', `${fmtNumber(tokens.completion)} completion tokens`);

    const costs = summary.costs || {};
    setText('analyticsCost', fmtUsd(costs.total_usd));
    setText('analyticsCostSub', `LLM ${fmtUsd(costs.llm_usd)} | Services ${fmtUsd(costs.service_usd)}`);
    setText('analyticsCostUnknown', fmtNumber(costs.unknown_tokens));
    setText('analyticsCostUnknownSub', `${fmtNumber(costs.unknown_model_count)} Modelle ohne Preis`);

    const memory = summary.memory_ms || {};
    setText('analyticsMemory', fmtMs(memory.p50));
    setText('analyticsMemorySub', `p95 ${fmtMs(memory.p95)} | n=${fmtNumber(memory.count)}`);

    const memorySearch = summary.memory_search_ms || {};
    const memoryResults = summary.memory_search_results || {};
    setText('analyticsMemorySearch', fmtMs(memorySearch.p50));
    setText('analyticsMemorySearchSub', `avg ${fmtNumber(memoryResults.avg)} Treffer | n=${fmtNumber(memorySearch.count)}`);

    const memoryCache = summary.memory_cache || {};
    setText('analyticsMemoryCache', fmtPct(memoryCache.hit_rate));
    setText('analyticsMemoryCacheSub', `${fmtNumber(memoryCache.hits)} / ${fmtNumber(memoryCache.total)} RAM hits`);

    const ttsCache = summary.tts_cache || {};
    setText('analyticsTtsCache', fmtPct(ttsCache.hit_rate));
    setText('analyticsTtsCacheSub', `${fmtNumber(ttsCache.hits)} / ${fmtNumber(ttsCache.total)} TTS hits`);

    const diary = summary.diary_rag_ms || {};
    const diaryResults = summary.diary_rag_results || {};
    setText('analyticsDiary', fmtMs(diary.p50));
    setText('analyticsDiarySub', `avg ${fmtNumber(diaryResults.avg)} Treffer | n=${fmtNumber(diary.count)}`);

    const expert = summary.expert_ms || {};
    setText('analyticsExpert', fmtMs(expert.p50));
    setText('analyticsExpertSub', `p95 ${fmtMs(expert.p95)} | n=${fmtNumber(expert.count)}`);
  }

  function renderDurationList(id, rows, emptyText) {
    const el = $(id);
    if (!el) return;
    const list = Array.isArray(rows) ? rows : [];
    if (!list.length) {
      el.innerHTML = `<div class="analytics-empty">${escapeHtml(emptyText)}</div>`;
      return;
    }
    el.innerHTML = list.slice(0, 12).map(row => `
      <div class="analytics-row">
        <span class="analytics-row-name" title="${escapeHtml(row.name)}">${escapeHtml(row.name)}</span>
        <span class="analytics-row-stat">${fmtMs(row.p50)}</span>
        <span class="analytics-row-stat muted">${fmtMs(row.p95)}</span>
        <small>n=${fmtNumber(row.count)}</small>
      </div>
    `).join('');
  }

  function renderCounterList(id, rows, emptyText) {
    const el = $(id);
    if (!el) return;
    const list = Array.isArray(rows) ? rows : [];
    if (!list.length) {
      el.innerHTML = `<div class="analytics-empty">${escapeHtml(emptyText)}</div>`;
      return;
    }
    el.innerHTML = list.slice(0, 12).map(row => `
      <div class="analytics-row">
        <span class="analytics-row-name" title="${escapeHtml(row.name)}">${escapeHtml(row.name)}</span>
        <span class="analytics-row-stat">${fmtNumber(row.count)}</span>
      </div>
    `).join('');
  }

  function renderRepeatList(id, rows, emptyText) {
    const el = $(id);
    if (!el) return;
    const list = Array.isArray(rows) ? rows : [];
    if (!list.length) {
      el.innerHTML = `<div class="analytics-empty">${escapeHtml(emptyText)}</div>`;
      return;
    }
    el.innerHTML = list.slice(0, 8).map(row => `
      <div class="analytics-row">
        <span class="analytics-row-name" title="${escapeHtml(row.name)}">${escapeHtml(row.name)}</span>
        <span class="analytics-row-stat">${fmtNumber(row.count)}x</span>
        <small>${row.seen ? 'seen' : 'unseen'}</small>
      </div>
    `).join('');
  }

  function renderCostList(id, rows, emptyText) {
    const el = $(id);
    if (!el) return;
    const list = Array.isArray(rows) ? rows : [];
    if (!list.length) {
      el.innerHTML = `<div class="analytics-empty">${escapeHtml(emptyText)}</div>`;
      return;
    }
    el.innerHTML = list.slice(0, 8).map(row => {
      const parts = [];
      if (row.tokens !== undefined) parts.push(`${fmtNumber(row.tokens)} tok`);
      if (row.count !== undefined) parts.push(`${fmtNumber(row.count)}x`);
      if (row.source) parts.push(row.source);
      return `
        <div class="analytics-row">
          <span class="analytics-row-name" title="${escapeHtml(row.name)}">${escapeHtml(row.name)}</span>
          <span class="analytics-row-stat">${fmtUsd(row.cost_usd)}</span>
          <small>${escapeHtml(parts.join(' | '))}</small>
        </div>
      `;
    }).join('');
  }

  function renderUnknownCostList(id, rows, emptyText) {
    const el = $(id);
    if (!el) return;
    const list = Array.isArray(rows) ? rows : [];
    if (!list.length) {
      el.innerHTML = `<div class="analytics-empty">${escapeHtml(emptyText)}</div>`;
      return;
    }
    el.innerHTML = list.slice(0, 8).map(row => `
      <div class="analytics-row">
        <span class="analytics-row-name" title="${escapeHtml(row.name)}">${escapeHtml(row.name)}</span>
        <span class="analytics-row-stat">${row.tokens !== undefined ? fmtNumber(row.tokens) : fmtNumber(row.count)}</span>
        <small>${escapeHtml(row.source || 'unknown')}</small>
      </div>
    `).join('');
  }

  function renderAlerts(summary) {
    const el = $('analyticsAlertList');
    if (!el) return;
    const alerts = Array.isArray(summary?.alerts?.active) ? summary.alerts.active : [];
    const unseen = Number(summary?.alerts?.unseen_count || 0);
    setText('analyticsAlertMeta', `${fmtNumber(alerts.length)} aktiv | ${fmtNumber(unseen)} unseen`);
    if (!alerts.length) {
      el.innerHTML = '<div class="analytics-empty">Keine aktiven Alerts.</div>';
      return;
    }
    el.innerHTML = alerts.slice(0, 8).map(alert => {
      const sev = String(alert.severity || 'warning').toUpperCase();
      const count = Number(alert.count || 1);
      return `
        <div class="analytics-row">
          <span class="analytics-row-name" title="${escapeHtml(alert.message || '')}">${escapeHtml(alert.title || alert.type || 'Alert')}</span>
          <span class="analytics-row-stat">${escapeHtml(sev)}</span>
          <small>${count > 1 ? `${fmtNumber(count)}x` : (alert.is_seen || alert.isSeen ? 'seen' : 'new')}</small>
        </div>
      `;
    }).join('');
  }

  function renderHealth(health) {
    const el = $('analyticsHealthGrid');
    if (!el) return;
    const services = Array.isArray(health?.services) ? health.services : [];
    setText(
      'analyticsHealthMeta',
      services.length ? `${health.ok_count || 0}/${health.total || services.length} online` : 'Keine Health-Daten'
    );
    if (!services.length) {
      el.innerHTML = '<div class="analytics-empty">Health-Daten noch nicht geladen.</div>';
      return;
    }
    el.innerHTML = services.map(item => {
      const ok = Boolean(item.ok);
      const latency = item.latency_ms === null || item.latency_ms === undefined ? '' : `${fmtMs(item.latency_ms)}`;
      const detail = item.detail || item.model || item.status_text || '';
      return `
        <div class="analytics-health-card ${ok ? 'ok' : 'bad'}">
          <span class="analytics-health-dot"></span>
          <div class="analytics-health-main">
            <strong>${escapeHtml(item.name || 'Service')}</strong>
            <small title="${escapeHtml(detail)}">${escapeHtml(detail || item.status_text || '')}</small>
          </div>
          <span class="analytics-health-status">${escapeHtml(item.status_text || item.status || '')}</span>
          ${latency ? `<span class="analytics-health-latency">${latency}</span>` : ''}
        </div>
      `;
    }).join('');
  }

  function renderChart(timeseries) {
    const el = $('analyticsChart');
    if (!el) return;
    const buckets = Array.isArray(timeseries?.buckets) ? timeseries.buckets : [];
    if (!buckets.length) {
      el.innerHTML = '<div class="analytics-empty">Noch keine Timeline-Daten.</div>';
      setText('analyticsChartMeta', 'Requests und p95');
      return;
    }

    const maxRequests = Math.max(1, ...buckets.map(b => Number(b.requests || 0)));
    const maxLatency = Math.max(1, ...buckets.map(b => Number(b.e2e_p95 || b.e2e_p50 || 0)));
    const maxErrors = Math.max(1, ...buckets.map(b => Number(b.errors || 0)));
    const last = buckets[buckets.length - 1];
    setText('analyticsChartMeta', `${buckets.length} Buckets | zuletzt ${fmtTime(last.ts)}`);

    el.innerHTML = buckets.map(bucket => {
      const requestH = Math.max(4, Math.round((Number(bucket.requests || 0) / maxRequests) * 92));
      const latencyH = Math.max(4, Math.round((Number(bucket.e2e_p95 || bucket.e2e_p50 || 0) / maxLatency) * 92));
      const errorH = Math.max(0, Math.round((Number(bucket.errors || 0) / maxErrors) * 92));
      const label = fmtTime(bucket.ts).split(',')[0];
      const title = [
        fmtTime(bucket.ts),
        `Requests: ${bucket.requests || 0}`,
        `Errors: ${bucket.errors || 0}`,
        `E2E p95: ${fmtMs(bucket.e2e_p95)}`,
        `LLM p50: ${fmtMs(bucket.llm_p50)}`,
        `Memory Search p50: ${fmtMs(bucket.memory_search_p50)}`,
        `RAM Cache: ${fmtPct(bucket.memory_hit_rate)}`,
        `Diary p50: ${fmtMs(bucket.diary_p50)}`,
        `TTFT p50: ${fmtMs(bucket.ttft_p50)}`,
        `TTS Cache: ${fmtPct(bucket.tts_hit_rate)}`,
        `Output: ${fmtPerSec(bucket.tps_avg)}`
      ].join('\n');
      return `
        <div class="analytics-chart-bucket" title="${escapeHtml(title)}">
          <div class="analytics-chart-bars">
            <span class="analytics-bar requests" style="height:${requestH}%"></span>
            <span class="analytics-bar latency" style="height:${latencyH}%"></span>
            ${errorH ? `<span class="analytics-bar errors" style="height:${errorH}%"></span>` : ''}
          </div>
          <small>${escapeHtml(label)}</small>
        </div>
      `;
    }).join('');
  }

  function render(summary, timeseries, health) {
    renderKpis(summary || {});
    renderAlerts(summary || {});
    renderHealth(health || {});
    renderChart(timeseries || {});
    renderDurationList('analyticsNodeList', summary?.node_latency, 'Noch keine Node-Latenzen.');
    renderDurationList('analyticsModelList', summary?.models, 'Noch keine LLM-Modelldaten.');
    renderDurationList('analyticsExpertList', summary?.expert_domains, 'Noch keine Expert-Domain-Daten.');
    renderDurationList('analyticsExpertPassList', summary?.expert_passes, 'Noch keine Expert-Pass-Daten.');
    renderDurationList('analyticsExpertModelList', summary?.expert_models, 'Noch keine Expert-Modelldaten.');
    renderCounterList('analyticsExpertFallbackList', summary?.expert_fallbacks, 'Noch keine Expert-Fallbacks.');
    renderCostList('analyticsCostModelList', summary?.costs?.by_model, 'Noch keine bepreisten LLM-Kosten.');
    renderCostList('analyticsCostUserList', summary?.costs?.by_user, 'Noch keine Kosten pro User.');
    renderCostList('analyticsCostSourceList', summary?.costs?.by_source, 'Noch keine Kosten pro Source.');
    renderCostList('analyticsCostDayList', summary?.costs?.by_day, 'Noch keine Tageskosten.');
    renderCostList('analyticsCostServiceList', summary?.costs?.by_service, 'Noch keine Service-Kosten.');
    renderUnknownCostList('analyticsCostUnknownList', summary?.costs?.unknown_models, 'Keine unbekannten LLM-Preise im Fenster.');
    renderCounterList('analyticsUserList', summary?.users, 'Noch keine User-Requests.');
    renderCounterList('analyticsErrorList', summary?.error_nodes, 'Keine Errors im Fenster.');
    renderCounterList('analyticsErrorCodeList', summary?.error_codes, 'Keine Error-Codes im Fenster.');
    renderCounterList('analyticsErrorModuleList', summary?.error_modules, 'Keine Error-Module im Fenster.');
    renderRepeatList('analyticsErrorRepeatList', summary?.error_repeats, 'Keine wiederholten Inbox-Errors.');

    const brain = summary?.brain || {};
    const brainLabel = brain.running ? 'Brain online' : 'Brain offline';
    setText(
      'analyticsMeta',
      `${brainLabel} | letzte Metrik: ${fmtTime(summary?.latest_event_at)} | ${fmtNumber(summary?.event_count)} Events`
    );
  }

  async function refresh() {
    if (!initialized) init();
    setLoading(true);
    const hours = selectedHours();
    const params = queryParams(hours);
    const timelineParams = `${params}&bucket_minutes=${bucketMinutes(hours)}`;
    try {
      const [summary, timeseries, health] = await Promise.all([
        YourAIAPI.json(`/api/analytics/summary?${params}`),
        YourAIAPI.json(`/api/analytics/timeseries?${timelineParams}`),
        YourAIAPI.json('/api/analytics/health')
      ]);
      renderFilterOptions(summary);
      render(summary, timeseries, health);
    } catch (err) {
      setText('analyticsMeta', `Analytics konnte nicht geladen werden: ${err.message}`);
    } finally {
      setLoading(false);
    }
  }

  function startTimer() {
    stopTimer();
    refreshTimer = setInterval(refresh, 30000);
  }

  function stopTimer() {
    clearInterval(refreshTimer);
    refreshTimer = null;
  }

  function onActive(isActive) {
    active = Boolean(isActive);
    if (active) {
      refresh();
      startTimer();
    } else {
      stopTimer();
    }
  }

  async function clearAnalytics() {
    if (!confirm('All Analytics-Daten löschen? Das kann nicht rückgängig gemacht werden.')) return;
    try {
      await YourAIAPI.json('/api/analytics/clear', { method: 'DELETE' });
      if (typeof App !== 'undefined' && App.toast) App.toast('Analytics gelöscht', 'success');
      refresh();
    } catch (err) {
      if (typeof App !== 'undefined' && App.toast) App.toast('Fehler: ' + err.message, 'error');
    }
  }

  function init() {
    if (initialized) return;
    initialized = true;
    $('analyticsRefreshBtn')?.addEventListener('click', refresh);
    $('analyticsClearBtn')?.addEventListener('click', clearAnalytics);
    $('analyticsWindow')?.addEventListener('change', () => {
      if (active) refresh();
    });
    ['analyticsUserFilter', 'analyticsSourceFilter', 'analyticsModelFilter'].forEach(id => {
      $(id)?.addEventListener('change', () => {
        if (active) refresh();
      });
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  return { init, refresh, onActive };
})();
