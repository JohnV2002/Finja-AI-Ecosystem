/* ══════════════════════════════════════════════════════════════════
   chat.js — Chat Panel Logik
══════════════════════════════════════════════════════════════════ */

const Chat = (() => {
  // ─── Marked + Highlight.js Setup ──────────────────────────
  if (typeof marked !== 'undefined') {
    const renderer = new marked.Renderer();
    renderer.code = function(code, lang) {
      // Handle marked v5+ object param or plain string
      let text = typeof code === 'object' ? code.text : code;
      let language = typeof code === 'object' ? code.lang : lang;
      let highlighted = text;
      if (typeof hljs !== 'undefined') {
        if (language && hljs.getLanguage(language)) {
          highlighted = hljs.highlight(text, { language }).value;
        } else {
          highlighted = hljs.highlightAuto(text).value;
        }
      }
      const langAttr = language ? ` data-lang="${language}"` : '';
      const langClass = language ? ` class="hljs language-${language}"` : ' class="hljs"';
      return `<pre${langAttr}><code${langClass}>${highlighted}</code></pre>`;
    };
    marked.setOptions({ renderer, breaks: true });
  }

  // ─── DOM Refs ───────────────────────────────────────────────
  const messagesEl   = document.getElementById('chatMessages');
  const inputEl      = document.getElementById('chatInput');
  const sendBtnEl    = document.getElementById('sendBtn');
  const chatEmptyEl  = document.getElementById('chatEmpty');
  const typingIndEl  = document.getElementById('typingIndicator');
  const chatUserLbl  = document.getElementById('chatUserLabel');

  // ─── State ──────────────────────────────────────────────────
  let isBusy = false;
  let typingBubble = null;
  let _attachments = [];  // { type: 'image'|'text', name, data }

  // ─── Auth Helper ─────────────────────────────────────────────
  function _chatAuthHeaders() {
    const h = {};
    const k = localStorage.getItem('yourai_access_key');
    if (k) h['Authorization'] = `Bearer ${k}`;
    const uuid = (typeof YourAIUUID !== 'undefined') ? YourAIUUID.get() : null;
    if (uuid) h['X-Session-UUID'] = uuid;
    return h;
  }

  // ─── Discord Emoji Map ───────────────────────────────────────
  let _emojiMap = {};  // name → cdn url

  async function _loadEmojis() {
    try {
      const res = await fetch('/api/emojis', { headers: _chatAuthHeaders() });
      if (res.ok) {
        _emojiMap = await res.json();
        console.log('🦊 [Emojis] Geladen:', Object.keys(_emojiMap).length, 'Emojis', Object.keys(_emojiMap).slice(0, 10));
      }
    } catch (e) { console.warn('🦊 [Emojis] Nicht verfügbar:', e.message); }
  }

  function _applyEmojis(html) {
    if (!Object.keys(_emojiMap).length) return html;
    return html.replace(/:(\w+):/g, (match, name) => {
      const url = _emojiMap[name];
      if (!url) return match;
      return `<img src="${url}" alt=":${name}:" class="discord-emoji" title=":${name}:">`;
    });
  }

  // ─── Dedup: seen tracking IDs (prevents WS replay showing messages twice) ───
  const _seenIds = new Set();

  // ─── localStorage Chat History (per-mode) ────────────────────
  const _MAX_HISTORY = 150;
  const _accessKey = localStorage.getItem('yourai_access_key') || 'guest';

  function _storageKey() {
    const mode = (typeof App !== 'undefined' && App.getMode) ? App.getMode() : 'yourai';
    return `yourai_chat_${mode}_${_accessKey}`;
  }

  function _loadRaw() {
    try { return JSON.parse(localStorage.getItem(_storageKey()) || '[]'); }
    catch { return []; }
  }

  function _saveMsg(entry) {
    const key = _storageKey();
    const history = _loadRaw();
    history.push({ ...entry, ts: Date.now() });
    if (history.length > _MAX_HISTORY) history.splice(0, history.length - _MAX_HISTORY);
    try { localStorage.setItem(key, JSON.stringify(history)); }
    catch (e) { console.warn('[Chat] localStorage voll:', e); }
  }

  function _restoreHistory() {
    const history = _loadRaw();
    if (!history.length) return;
    chatEmptyEl.hidden = true;
    // Nur die allerletzte YourAI-Nachricht bekommt TTS + Feedback-Buttons
    const lastYourAIIdx = history.reduce((last, e, i) => e.role === 'yourai' ? i : last, -1);
    for (let i = 0; i < history.length; i++) {
      const entry = history[i];
      if (entry.role === 'user') {
        _appendBubble('user', entry.sender || 'Du', entry.text, false, null, true);
      } else if (entry.role === 'yourai') {
        if (entry.trackingId) _seenIds.add(entry.trackingId);
        const _cls = App.getBotClass();
        const _name = App.getBotName();
        const _bubble = _appendBubble(_cls, _name, entry.text, true, entry.model || null, entry.expertDomain || null, entry.expertModel || null, true);
        if (_bubble && i === lastYourAIIdx) {
          _addTTSButton(_bubble.parentElement, entry.text);
          if (entry.trackingId) _addFeedbackButtons(_bubble.parentElement, entry.trackingId);
        }
      } else if (entry.role === 'image') {
        if (entry.url) _seenIds.add(entry.url);
        _appendImageBubble(entry.url, entry.prompt || '', true);
      }
    }
  }

  function _clearedIdsKey() {
    const mode = (typeof App !== 'undefined' && App.getMode) ? App.getMode() : 'yourai';
    return `yourai_cleared_ids_${mode}_${_accessKey}`;
  }

  function _loadClearedIds() {
    try {
      const arr = JSON.parse(localStorage.getItem(_clearedIdsKey()) || '[]');
      arr.forEach(id => _seenIds.add(id));
    } catch { /* ignore */ }
  }

  function clearHistory() {
    // Save all currently known IDs so they stay suppressed after refresh
    try {
      localStorage.setItem(_clearedIdsKey(), JSON.stringify([..._seenIds]));
    } catch { /* ignore */ }
    localStorage.removeItem(_storageKey());
    // Remove all bubbles except the empty placeholder
    Array.from(messagesEl.querySelectorAll('.chat-bubble-wrap')).forEach(el => el.remove());
    chatEmptyEl.hidden = false;
  }

  // ─── Public API ─────────────────────────────────────────────

  /**
   * Called by app.js when we get a chat response event from the server.
   * Shows YourAI's message bubble.
   */
  function showYourAIMessage(text, trackingId, modelName = null, expertDomain = null, expertModel = null) {
    if (trackingId && _seenIds.has(trackingId)) return;  // WS replay dedup
    if (trackingId) _seenIds.add(trackingId);
    // New message came in → cleared-ids list no longer needed
    localStorage.removeItem(_clearedIdsKey());
    removeTyping();
    const bubble = _appendBubble(App.getBotClass(), App.getBotName(), text, true, modelName, expertDomain, expertModel);
    _saveMsg({ role: 'yourai', text, model: modelName || null, expertDomain: expertDomain || null, expertModel: expertModel || null, trackingId: trackingId || null });
    // Add TTS speaker button + feedback buttons
    if (bubble) {
      _addTTSButton(bubble.parentElement, text);
    }
    if (trackingId && bubble) {
      _addFeedbackButtons(bubble.parentElement, trackingId);
    }
    // Auto-play TTS if enabled
    if (typeof TTS !== 'undefined' && TTS.isAutoPlay()) {
      TTS.speak(text);
    }
    isBusy = false;
    sendBtnEl.disabled = false;
    typingIndEl.hidden = true;
  }

  /**
   * Called when an image_ready event arrives — shows generated image in chat.
   */
  function _appendImageBubble(imageUrl, prompt, skipSave = false) {
    chatEmptyEl.hidden = true;

    const _cls = App.getBotClass();
    const wrap = document.createElement('div');
    wrap.className = `chat-bubble-wrap ${_cls}`;

    const senderEl = document.createElement('div');
    senderEl.className = 'chat-bubble-sender';
    senderEl.textContent = App.getBotName();

    const bubble = document.createElement('div');
    bubble.className = `chat-bubble ${_cls}`;

    const img = document.createElement('img');
    img.src = imageUrl;
    img.alt = prompt || 'Generated image';
    img.className = 'chat-generated-image';
    img.loading = 'lazy';
    img.onerror = () => console.error('🎨 [Chat] Bild konnte nicht geladen werden:', imageUrl);
    img.onload  = () => console.log('🎨 [Chat] Bild erfolgreich geladen:', imageUrl);
    img.onclick = () => window.open(imageUrl, '_blank');
    img.title = '🔍 Click to open full size';

    bubble.appendChild(img);
    if (prompt) {
      const caption = document.createElement('div');
      caption.className = 'chat-image-caption';
      caption.textContent = `🎨 "${prompt.substring(0, 120)}${prompt.length > 120 ? '…' : ''}"`;
      bubble.appendChild(caption);
    }

    wrap.appendChild(senderEl);
    wrap.appendChild(bubble);
    messagesEl.appendChild(wrap);
    messagesEl.scrollTop = messagesEl.scrollHeight;

    if (!skipSave) _saveMsg({ role: 'image', url: imageUrl, prompt });
  }

  function showMaintenanceError() {
    removeTyping();
    isBusy = false;
    sendBtnEl.disabled = false;
    typingIndEl.hidden = true;
    const _name = App.getBotName();
    _appendBubble(App.getBotClass(), _name, `⚠️ ${_name} is currently in maintenance mode — please copy your message and try again in a few minutes!`, false, null, true);
  }

  function showYourAIImage(imageUrl, prompt = '') {
    if (_seenIds.has(imageUrl)) return;  // WS replay dedup
    _seenIds.add(imageUrl);
    console.log('🎨 [Chat] showYourAIImage aufgerufen:', { imageUrl, prompt: prompt?.substring(0, 80) });
    removeTyping();
    _appendImageBubble(imageUrl, prompt);
  }

  /**
   * Called when user switches user — update the display label.
   */
  function updateUserLabel(displayName) {
    chatUserLbl.textContent = `Als: ${displayName}`;
  }

  /**
   * Called by app.js with incoming WebSocket messages.
   */
  function handleMessage(msg) {
    if (msg.type === 'input_received') {
      // The server echoed our message — show it (the user bubble was already
      // shown optimistically; skip if we already rendered it)
      return;
    }
    if (msg.type === 'pipeline_end_chat') {
      showYourAIMessage(msg.data.response || '', msg.data.tracking_id || null);
      return;
    }
  }

  // ─── Internal helpers ────────────────────────────────────────

  function _appendBubble(who, sender, text, renderMd, modelName = null, expertDomain = null, expertModel = null, skipSave = false) {
    chatEmptyEl.hidden = true;

    const wrap = document.createElement('div');
    wrap.className = `chat-bubble-wrap ${who}`;

    const senderEl = document.createElement('div');
    senderEl.className = 'chat-bubble-sender';
    senderEl.textContent = sender;
    if (who !== 'user') {
      // ZDR-Badge: nur wenn Modell-ZDR-Flag gesetzt (kein Modellname!)
      if (modelName === 'ZDR') {
        const zdrEl = document.createElement('span');
        zdrEl.className = 'chat-model-label';
        zdrEl.textContent = 'ZDR ✅';
        senderEl.appendChild(zdrEl);
      }
      // Expert-Badge: nur wenn tatsächlich ein Experte benutzt wurde
      if (expertDomain && expertModel) {
        const expEl = document.createElement('span');
        expEl.className = 'chat-expert-label';
        const shortModel = expertModel.split('/').pop();
        expEl.textContent = `🔬 ${expertDomain} · ${shortModel}`;
        expEl.title = expertModel;  // voller Modellname als Tooltip
        senderEl.appendChild(expEl);
      }
    }

    const bubble = document.createElement('div');
    bubble.className = `chat-bubble ${who}`;

    if (renderMd && typeof marked !== 'undefined') {
      bubble.innerHTML = _applyEmojis(marked.parse(text));
    } else {
      bubble.textContent = text;
      if (_emojiMap && Object.keys(_emojiMap).length) {
        bubble.innerHTML = _applyEmojis(bubble.innerHTML);
      }
    }

    if (who === 'user') {
      wrap.appendChild(bubble);
      wrap.appendChild(senderEl);
    } else {
      wrap.appendChild(senderEl);
      wrap.appendChild(bubble);
    }

    messagesEl.appendChild(wrap);
    setTimeout(() => {
      messagesEl.scrollTop = messagesEl.scrollHeight;
    }, 50);
    return bubble;
  }

  function _addTTSButton(wrapEl, text) {
    if (typeof TTS === 'undefined') return;
    const btn = document.createElement('button');
    btn.className = 'tts-speak-btn';
    btn.title = 'Vorlesen';
    btn.innerHTML = '🔊';

    const _reset = () => { btn.classList.remove('playing'); btn.innerHTML = '🔊'; };

    btn.addEventListener('click', () => {
      if (btn.classList.contains('playing')) {
        TTS.stop();
        _reset();
      } else {
        btn.classList.add('playing');
        btn.innerHTML = '⏹️';
        TTS.speak(text, _reset);  // _reset called when audio finishes
      }
    });
    wrapEl.appendChild(btn);
  }

  function _addFeedbackButtons(wrapEl, trackingId) {
    const bar = document.createElement('div');
    bar.className = 'feedback-bar';
    bar.dataset.trackingId = trackingId;

    const upBtn = document.createElement('button');
    upBtn.className = 'feedback-btn';
    upBtn.dataset.rating = 'up';
    upBtn.innerHTML = '👍';
    upBtn.title = 'Gute Antwort';

    const downBtn = document.createElement('button');
    downBtn.className = 'feedback-btn';
    downBtn.dataset.rating = 'down';
    downBtn.innerHTML = '👎';
    downBtn.title = 'Schlechte Antwort';

    function handleClick(rating) {
      // Visual feedback
      upBtn.classList.toggle('active', rating === 'up');
      downBtn.classList.toggle('active', rating === 'down');
      bar.classList.add('rated');

      // Send to server
      App.sendWs({ type: 'feedback', tracking_id: trackingId, rating });
    }

    upBtn.addEventListener('click', () => handleClick('up'));
    downBtn.addEventListener('click', () => handleClick('down'));

    bar.appendChild(upBtn);
    bar.appendChild(downBtn);
    wrapEl.appendChild(bar);
  }

  // ─── File Attachment Helpers ─────────────────────────────────

  function _renderChip(attachment, index) {
    const chipsEl = document.getElementById('attachChips');
    if (!chipsEl) return;
    chipsEl.hidden = false;
    document.getElementById('attachBtn')?.classList.add('has-files');

    const chip = document.createElement('div');
    chip.className = 'attach-chip';
    chip.dataset.index = index;

    const icon = document.createElement('span');
    icon.className = 'chip-icon';
    icon.textContent = attachment.type === 'image' ? '🖼️' : '📄';

    const name = document.createElement('span');
    name.className = 'chip-name';
    name.textContent = attachment.name;
    name.title = attachment.name;

    const removeBtn = document.createElement('button');
    removeBtn.className = 'chip-remove';
    removeBtn.textContent = '✕';
    removeBtn.title = 'Entfernen';
    removeBtn.addEventListener('click', () => _removeAttachment(index));

    chip.appendChild(icon);
    chip.appendChild(name);
    chip.appendChild(removeBtn);
    chipsEl.appendChild(chip);
  }

  function _removeAttachment(index) {
    _attachments.splice(index, 1);
    const chipsEl = document.getElementById('attachChips');
    if (!chipsEl) return;
    chipsEl.innerHTML = '';
    if (_attachments.length === 0) {
      chipsEl.hidden = true;
      document.getElementById('attachBtn')?.classList.remove('has-files');
    } else {
      _attachments.forEach((a, i) => _renderChip(a, i));
    }
  }

  function _clearAttachments() {
    _attachments = [];
    const chipsEl = document.getElementById('attachChips');
    if (chipsEl) { chipsEl.innerHTML = ''; chipsEl.hidden = true; }
    document.getElementById('attachBtn')?.classList.remove('has-files');
  }

  async function _handleFile(file) {
    const MAX_SIZE = 5 * 1024 * 1024; // 5 MB
    if (file.size > MAX_SIZE) {
      alert(`"${file.name}" ist zu groß (max 5 MB)`);
      return;
    }
    const isImage = file.type.startsWith('image/');
    return new Promise((resolve) => {
      const reader = new FileReader();
      reader.onload = (e) => {
        const attachment = { type: isImage ? 'image' : 'text', name: file.name, data: e.target.result };
        _attachments.push(attachment);
        _renderChip(attachment, _attachments.length - 1);
        resolve();
      };
      reader.onerror = () => { console.warn('[Attach] Konnte Datei nicht lesen:', file.name); resolve(); };
      if (isImage) reader.readAsDataURL(file);
      else reader.readAsText(file);
    });
  }

  function _buildMessageWithAttachments(text) {
    const image_urls = [];
    const parts = [];
    if (text) parts.push(text);
    _attachments.forEach(a => {
      if (a.type === 'image') {
        image_urls.push(a.data);
      } else {
        const ext = a.name.split('.').pop() || 'txt';
        parts.push(`\`\`\`${ext}\n// ${a.name}\n${a.data}\n\`\`\``);
      }
    });
    return { text: parts.join('\n\n'), image_urls };
  }

  function _setupFileInput() {
    const fileInput = document.getElementById('attachFileInput');
    const attachBtn = document.getElementById('attachBtn');
    if (!fileInput || !attachBtn) return;
    attachBtn.addEventListener('click', () => fileInput.click());
    fileInput.addEventListener('change', async (e) => {
      const files = Array.from(e.target.files || []);
      for (const f of files) await _handleFile(f);
      fileInput.value = ''; // reset so same file can re-trigger
    });
    // Drag & drop onto input bar
    const inputBar = document.querySelector('.chat-input-bar');
    if (inputBar) {
      inputBar.addEventListener('dragover', (e) => { e.preventDefault(); inputBar.classList.add('drag-over'); });
      inputBar.addEventListener('dragleave', () => inputBar.classList.remove('drag-over'));
      inputBar.addEventListener('drop', async (e) => {
        e.preventDefault();
        inputBar.classList.remove('drag-over');
        const files = Array.from(e.dataTransfer.files || []);
        for (const f of files) await _handleFile(f);
      });
    }
  }

  function _showTyping() {
    if (typingBubble) return;
    chatEmptyEl.hidden = true;

    const _cls = App.getBotClass();
    const wrap = document.createElement('div');
    wrap.className = `chat-bubble-wrap ${_cls}`;

    const senderEl = document.createElement('div');
    senderEl.className = 'chat-bubble-sender';
    senderEl.textContent = App.getBotName();

    const bubble = document.createElement('div');
    bubble.className = `chat-bubble ${_cls} typing-bubble`;
    for (let i = 0; i < 3; i++) {
      const dot = document.createElement('span');
      dot.className = 'typing-dot';
      bubble.appendChild(dot);
    }

    wrap.appendChild(senderEl);
    wrap.appendChild(bubble);
    messagesEl.appendChild(wrap);
    setTimeout(() => {
      messagesEl.scrollTop = messagesEl.scrollHeight;
    }, 50);
    typingBubble = wrap;
  }

  function removeTyping() {
    if (typingBubble) {
      typingBubble.remove();
      typingBubble = null;
    }
  }

  function _sendMessage() {
    const text = inputEl.value.trim();
    const hasAttachments = _attachments.length > 0;
    if (!text && !hasAttachments) return;
    if (isBusy) return;

    // Build final payload (text + image_urls)
    const { text: finalText, image_urls } = _buildMessageWithAttachments(text);
    const displayText = text || (hasAttachments ? '📎 Anhang' : '');

    // Optimistic: show user bubble immediately
    const senderName = App.getCurrentUserDisplay();
    const bubble = _appendBubble('user', senderName, displayText, false);

    // Show attachment previews inside the bubble
    if (bubble && hasAttachments) {
      const imgs = _attachments.filter(a => a.type === 'image');
      const txts = _attachments.filter(a => a.type === 'text');
      if (imgs.length || txts.length) {
        const preview = document.createElement('div');
        preview.className = 'bubble-attachments';
        imgs.forEach(a => {
          const img = document.createElement('img');
          img.src = a.data;
          img.className = 'attach-thumb';
          img.title = a.name;
          img.onclick = () => window.open(a.data, '_blank');
          preview.appendChild(img);
        });
        txts.forEach(a => {
          const fc = document.createElement('span');
          fc.className = 'attach-file-chip';
          fc.textContent = `📄 ${a.name}`;
          preview.appendChild(fc);
        });
        bubble.appendChild(preview);
      }
    }

    _saveMsg({ role: 'user', text: displayText, sender: senderName });

    // Clear input + attachments
    inputEl.value = '';
    inputEl.style.height = 'auto';
    _clearAttachments();

    // Mark busy
    isBusy = true;
    sendBtnEl.disabled = true;
    typingIndEl.hidden = false;
    _showTyping();

    // Send via WebSocket
    const wsMsg = { type: 'user_input', text: finalText };
    if (image_urls.length) wsMsg.image_urls = image_urls;
    if (typeof YourAIUUID !== 'undefined') wsMsg.session_uuid = YourAIUUID.get();
    App.sendWs(wsMsg);
  }

  // ─── Event Listeners ─────────────────────────────────────────

  document.getElementById('clearChatBtn').addEventListener('click', () => {
    if (confirm('Chat-Verlauf löschen? Das entfernt alle Nachrichten nur in deinem Browser — der Server weiß davon nichts.')) {
      clearHistory();
    }
  });

  sendBtnEl.addEventListener('click', _sendMessage);

  inputEl.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      _sendMessage();
    }
  });

  // Auto-resize textarea
  inputEl.addEventListener('input', () => {
    inputEl.style.height = 'auto';
    inputEl.style.height = Math.min(inputEl.scrollHeight, 120) + 'px';
  });

  // ─── Image Usage Pill ──────────────────────────────────────
  const _usagePill = document.getElementById('imageUsagePill');

  async function _loadImageUsage() {
    try {
      const res = await fetch('/api/image-usage', { headers: _chatAuthHeaders() });
      if (!res.ok) {
        console.warn('🎨 [Usage] API error:', res.status);
        return;
      }
      const data = await res.json();
      console.log('🎨 [Usage]', data);

      if (!_usagePill) {
        console.warn('🎨 [Usage] Pill element not found in DOM');
        return;
      }

      if (data.unlimited) {
        _usagePill.hidden = true;  // Admins don't need to see it
        console.log('🎨 [Usage] Unlimited — pill hidden');
        return;
      }

      _usagePill.hidden = false;
      _usagePill.textContent = `🎨 ${data.used}/${data.limit} Images`;
      _usagePill.title = `Image budget: ${data.remaining} remaining this month`;

      // Color coding
      _usagePill.classList.remove('low', 'empty');
      if (data.remaining <= 0) {
        _usagePill.classList.add('empty');
      } else if (data.remaining <= 5) {
        _usagePill.classList.add('low');
      }
    } catch (e) {
      console.warn('🎨 [Usage] Failed:', e.message);
    }
  }

  function refreshImageUsage() {
    _loadImageUsage();
  }

  /**
   * Called by app.js when mode switches (yourai ↔ altpersona).
   * Clears current chat bubbles and restores the new mode's history.
   */
  function reloadForMode() {
    // Clear current bubbles
    Array.from(messagesEl.querySelectorAll('.chat-bubble-wrap')).forEach(el => el.remove());
    _seenIds.clear();
    typingBubble = null;
    chatEmptyEl.hidden = false;
    // Load from the new mode's storage
    _loadClearedIds();
    _restoreHistory();
  }

  // Load cleared IDs first (so WS replay skips cleared messages), then emojis + history
  _loadClearedIds();
  _loadEmojis().then(_restoreHistory);
  _loadImageUsage();
  _setupFileInput();

  return { showYourAIMessage, showYourAIImage, showMaintenanceError, updateUserLabel, handleMessage, removeTyping, clearHistory, refreshImageUsage, reloadForMode };
})();
