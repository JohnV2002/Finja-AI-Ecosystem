/*
  YourAI Frontend API Client
  =========================
  Frontend module for the YourAI dashboard.

  Main Responsibilities:
  - Wrap dashboard HTTP requests behind shared helpers.
  - Attach access-key authentication headers consistently.
  - Normalize JSON and error handling for frontend callers.

  Side Effects:
  - Reads the access key from browser localStorage.
  - Performs network requests to the YourAI dashboard API.
*/
const YourAIAPI = (() => {
  function accessKey() {
    return localStorage.getItem('yourai_access_key') || '';
  }

  function sessionUUID() {
    return (typeof YourAIUUID !== 'undefined') ? YourAIUUID.get() : null;
  }

  function authHeaders(extra = {}) {
    const headers = { ...(extra || {}) };
    const key = accessKey();
    const uuid = sessionUUID();
    if (key) headers.Authorization = `Bearer ${key}`;
    if (uuid) headers['X-Session-UUID'] = uuid;
    return headers;
  }

  function withNoStore(url, options = {}) {
    const next = { ...options, headers: authHeaders(options.headers || {}), cache: 'no-store' };
    const method = (next.method || 'GET').toUpperCase();
    let nextUrl = url;
    if (method === 'GET') {
      nextUrl += (nextUrl.includes('?') ? '&' : '?') + '_=' + Date.now();
    }
    return [nextUrl, next];
  }

  async function json(url, options = {}) {
    const [nextUrl, nextOptions] = withNoStore(url, options);
    const res = await fetch(nextUrl, nextOptions);
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || res.statusText);
    }
    return res.json();
  }

  return { accessKey, sessionUUID, authHeaders, withNoStore, json };
})();
