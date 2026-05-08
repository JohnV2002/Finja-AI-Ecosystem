/* ══════════════════════════════════════════════════════════════════
   yourai-uuid.js — Persistente Browser-UUID für DSGVO-konforme
   Session-Identifikation. Kein PII, nur eine zufällige UUID.
   User kann Löschung aller Daten mit dieser UUID beantragen.
══════════════════════════════════════════════════════════════════ */

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
