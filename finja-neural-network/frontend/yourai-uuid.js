/*
  YourAI Browser UUID Helper
  =========================
  Frontend module for the YourAI dashboard.

  Main Responsibilities:
  - Create and persist an anonymous browser session UUID.
  - Expose the UUID for privacy export and deletion requests.
  - Keep session identity separate from personal account data.

  Side Effects:
  - Reads and writes the session UUID in localStorage.
*/
const YourAIUUID = (() => {
  const _STORAGE_KEY = 'yourai_session_uuid';

  function _generate() {
    const arr = new Uint8Array(16);
    crypto.getRandomValues(arr);
    arr[6] = (arr[6] & 0x0f) | 0x40; // version 4
    arr[8] = (arr[8] & 0x3f) | 0x80; // variant
    return [
      arr.slice(0, 4), arr.slice(4, 6), arr.slice(6, 8),
      arr.slice(8, 10), arr.slice(10, 16)
    ].map(s => Array.from(s).map(b => b.toString(16).padStart(2, '0')).join('')).join('-');
  }

  function get() {
    let uuid = localStorage.getItem(_STORAGE_KEY);
    if (!uuid) {
      uuid = _generate();
      localStorage.setItem(_STORAGE_KEY, uuid);
    }
    return uuid;
  }

  // Initialise on load
  get();

  return { get };
})();
