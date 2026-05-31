/*
  YourAI Chat History Frontend
  ===========================
  Frontend module for the YourAI dashboard.

  Main Responsibilities:
  - Load historical chat messages from the backend.
  - Render chat history entries into the dashboard.
  - Provide small utilities for history refresh and formatting.

  Side Effects:
  - Reads chat history through API calls.
  - Updates chat history DOM nodes.
*/
const ChatHistory = (() => {
  const MAX_HISTORY = 150;

  function _mode() {
    return (typeof App !== 'undefined' && App.getMode) ? App.getMode() : 'yourai';
  }

  function _accessKey() {
    return YourAIAPI.accessKey() || 'guest';
  }

  function storageKey() {
    return `yourai_chat_${_mode()}_${_accessKey()}`;
  }

  function clearedIdsKey() {
    return `yourai_cleared_ids_${_mode()}_${_accessKey()}`;
  }

  function loadRaw() {
    try {
      return JSON.parse(localStorage.getItem(storageKey()) || '[]');
    } catch {
      return [];
    }
  }

  function saveMsg(entry) {
    const key = storageKey();
    const history = loadRaw();
    history.push({ ...entry, ts: Date.now() });
    if (history.length > MAX_HISTORY) history.splice(0, history.length - MAX_HISTORY);
    try {
      localStorage.setItem(key, JSON.stringify(history));
    } catch (e) {
      console.warn('[Chat] localStorage voll:', e);
    }
  }

  function loadClearedIds(targetSet) {
    try {
      const arr = JSON.parse(localStorage.getItem(clearedIdsKey()) || '[]');
      arr.forEach(id => targetSet.add(id));
    } catch {
      /* ignore */
    }
  }

  function saveClearedIds(ids) {
    try {
      localStorage.setItem(clearedIdsKey(), JSON.stringify([...ids]));
    } catch {
      /* ignore */
    }
  }

  function clearClearedIds() {
    localStorage.removeItem(clearedIdsKey());
  }

  function clearHistory() {
    localStorage.removeItem(storageKey());
  }

  return { loadRaw, saveMsg, loadClearedIds, saveClearedIds, clearClearedIds, clearHistory };
})();
