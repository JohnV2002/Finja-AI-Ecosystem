/*
  YourAI Chat Frontend
  ===================
  Frontend module for the YourAI dashboard.

  Main Responsibilities:
  - Manage chat input, uploads, message rendering, and voice interaction controls.
  - Send user messages to the dashboard WebSocket/API layer.
  - Persist local chat history in the browser.

  Side Effects:
  - Reads microphone permissions and browser speech APIs.
  - Stores chat history in localStorage.
  - Uploads temporary files to the dashboard server.
*/
const Chat = (() => {
  // ─── Notification Sound ───────────────────────────────────
  const _notifAudio = new Audio('/notification.mp3');
  _notifAudio.volume = 0.5;

  function _playNotif() {
    try {
      _notifAudio.currentTime = 0;
      _notifAudio.play().catch(() => {});  // ignore autoplay policy errors
    } catch (_) {}
  }

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
  const queueIndEl   = document.getElementById('queueIndicator');
  const queueTextEl  = document.getElementById('queueIndicatorText');
  const chatUserLbl  = document.getElementById('chatUserLabel');
  const attachBtnEl  = document.getElementById('attachBtn');

  // ─── State ──────────────────────────────────────────────────
  let isBusy = false;
  let typingBubble = null;
  let _attachments = [];  // { type: 'image'|'text', name, data }

  const _localWaitLines = [
    'Bitte warten, YourAI kocht Cocoa...',
    'YourAI sortiert gerade ihre Gedanken...',
    'Kurz warten, YourAI poliert die Glitzerleitung...',
    'YourAI hebt gleich ab, einen Moment...',
  ];

  function _pickWaitLine() {
    return _localWaitLines[Math.floor(Math.random() * _localWaitLines.length)];
  }

  function _setInputLocked(locked, placeholder = '') {
    isBusy = locked;
    sendBtnEl.disabled = locked;
    if (inputEl) {
      inputEl.disabled = locked;
      const botName = (typeof App !== 'undefined' && App.getBotName) ? App.getBotName() : 'YourAI';
      inputEl.placeholder = locked ? placeholder : `Nachricht an ${botName}...`;
    }
    if (attachBtnEl) attachBtnEl.disabled = locked;
    const mic = document.getElementById('micBtn');
    if (mic && !mic.classList.contains('recording') && !mic.classList.contains('processing')) mic.disabled = locked;
  }

  function _setQueueStatus(status, message = '', position = 0) {
    const text = message || (status === 'queued' ? _pickWaitLine() : 'YourAI denkt...');
    if (queueIndEl && queueTextEl) {
      queueIndEl.hidden = status === 'idle';
      queueIndEl.dataset.status = status;
      if (status === 'queued' && position > 1) {
        queueTextEl.textContent = `${text} Platz ${position} in der Queue.`;
      } else {
        queueTextEl.textContent = text;
      }
    }

    if (status === 'queued') {
      removeTyping();
      typingIndEl.hidden = true;
      _setInputLocked(true, 'Nachricht ist in der Queue...');
      return;
    }

    if (status === 'flush') {
      removeTyping();
      typingIndEl.hidden = true;
      _setInputLocked(true, 'YourAI komprimiert gerade Kontext...');
      return;
    }

    if (status === 'processing') {
      typingIndEl.hidden = false;
      _showTyping();
      _setInputLocked(true, 'YourAI antwortet gleich...');
      return;
    }

    if (status === 'idle') {
      removeTyping();
      typingIndEl.hidden = true;
      _setInputLocked(false);
    }
  }

  // ─── Auth Helper ─────────────────────────────────────────────
  function _chatAuthHeaders() {
    return YourAIAPI.authHeaders();
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
    } catch (e) { console.warn('🦊 [Emojis] Not available:', e.message); }
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
  function _loadRaw() {
    return ChatHistory.loadRaw();
  }

  function _saveMsg(entry) {
    ChatHistory.saveMsg(entry);
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

  function _loadClearedIds() {
    ChatHistory.loadClearedIds(_seenIds);
  }

  function clearHistory() {
    // Save all currently known IDs so they stay suppressed after refresh
    ChatHistory.saveClearedIds(_seenIds);
    ChatHistory.clearHistory();
    // Remove all bubbles except the empty placeholder
    Array.from(messagesEl.querySelectorAll('.chat-bubble-wrap')).forEach(el => el.remove());
    chatEmptyEl.hidden = false;
  }

  // Public API

  function showYourAIMessage(text, trackingId, modelName = null, expertDomain = null, expertModel = null) {
    if (trackingId && _seenIds.has(trackingId)) return;  // WS replay dedup
    if (trackingId) _seenIds.add(trackingId);
    // New message came in → cleared-ids list no longer needed
    ChatHistory.clearClearedIds();
    removeTyping();
    _playNotif();
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
    _setQueueStatus('idle');
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
    img.onerror = () => console.error('🎨 [Chat] Image could not be loaded:', imageUrl);
    img.onload  = () => console.log('🎨 [Chat] Image loaded successfully:', imageUrl);
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

  function showMaintenanceError(data = {}) {
    _setQueueStatus('idle');
    const _name = App.getBotName();
    _appendBubble(App.getBotClass(), _name, `⚠️ ${_name} is currently in maintenance mode — please copy your message and try again in a few minutes!`, false, null, null, null);
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
      const pos = msg.data?.queue_position || 1;
      _setQueueStatus('queued', _pickWaitLine(), pos);
      // The server echoed our message — show it (the user bubble was already
      // shown optimistically; skip if we already rendered it)
      return;
    }
    if (msg.type === 'queue_status') {
      const data = msg.data || {};
      _setQueueStatus(data.status || 'processing', data.message || '', data.position || 0);
      return;
    }
    if (msg.type === 'event' && msg.data?.event_type === 'system_info' && msg.data?.node_name === 'queue_status') {
      const title = msg.data.title || 'YourAI arbeitet...';
      const phase = msg.data.phase || (/komprim|räumt|raeumt/i.test(title) ? 'flush' : 'processing');
      _setQueueStatus(phase === 'flush' ? 'flush' : 'processing', title, 0);
      return;
    }
    if (msg.type === 'pipeline_end_chat') {
      showYourAIMessage(msg.data.response || '', msg.data.tracking_id || null);
      return;
    }
  }

  // ─── Internal helpers ────────────────────────────────────────

  // ─── Friendly model names (no params, no org prefix) ────────
  function _friendlyModelName(modelId) {
    return YourAIText.friendlyModelName(modelId);
  }

  function _appendBubble(who, sender, text, renderMd, modelName = null, expertDomain = null, expertModel = null, skipSave = false) {
    chatEmptyEl.hidden = true;

    const wrap = document.createElement('div');
    wrap.className = `chat-bubble-wrap ${who}`;

    const senderEl = document.createElement('div');
    senderEl.className = 'chat-bubble-sender';
    senderEl.textContent = sender;
    if (who !== 'user') {
      // Expert label: shows friendly model name when an expert was used
      if (expertDomain && expertModel) {
        const friendly = _friendlyModelName(expertModel);
        const expEl = document.createElement('span');
        expEl.className = 'chat-expert-label';
        expEl.textContent = `Expert: ${friendly}`;
        expEl.title = `${expertDomain} · ${expertModel}`;  // full info as tooltip
        senderEl.appendChild(expEl);
      }
      // ZDR badge: always shown for bot messages (no model name leaked)
      if (modelName === 'ZDR') {
        const zdrEl = document.createElement('span');
        zdrEl.className = 'chat-model-label';
        zdrEl.textContent = 'ZDR ✅';
        senderEl.appendChild(zdrEl);
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
      reader.onerror = () => { console.warn('[Attach] Could not read file:', file.name); resolve(); };
      if (isImage) reader.readAsDataURL(file);
      else reader.readAsText(file);
    });
  }

  function _buildMessageWithAttachments(text) {
    const image_urls = [];
    const text_attachments = [];
    const parts = [];
    if (text) parts.push(text);
    _attachments.forEach(a => {
      if (a.type === 'image') {
        image_urls.push(a.data);
      } else {
        text_attachments.push({ name: a.name, data: a.data });
      }
    });
    if (text_attachments.length) {
      const names = text_attachments.map(a => a.name).join(', ');
      parts.push(`[Attached text file(s): ${names}]`);
    }
    return { text: parts.join('\n\n'), image_urls, text_attachments };
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
    const { text: finalText, image_urls, text_attachments } = _buildMessageWithAttachments(text);
    const sentAttachments = _attachments.slice();
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

    // Lock until the server confirms queue/processing; this prevents lost-feeling double sends.
    _setQueueStatus('queued', _pickWaitLine(), 1);

    // Send via WebSocket
    const wsMsg = { type: 'user_input', text: finalText };
    if (image_urls.length) wsMsg.image_urls = image_urls;
    if (text_attachments.length) wsMsg.text_attachments = text_attachments;
    if (typeof YourAIUUID !== 'undefined') wsMsg.session_uuid = YourAIUUID.get();
    const sent = App.sendWs(wsMsg);
    if (sent === false) {
      _setQueueStatus('idle');
      inputEl.value = text;
      inputEl.style.height = Math.min(inputEl.scrollHeight, 120) + 'px';
      _attachments = sentAttachments;
      const chipsEl = document.getElementById('attachChips');
      if (chipsEl) {
        chipsEl.innerHTML = '';
        chipsEl.hidden = _attachments.length === 0;
      }
      _attachments.forEach((a, i) => _renderChip(a, i));
    }
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

  // ─── STT (Speech-to-Text) — Mic Button ──────────────────────
  const micBtnEl = document.getElementById('micBtn');
  let _mediaRecorder = null;
  let _audioChunks = [];
  let _isRecording = false;

  function _setupMic() {
    if (!micBtnEl) return;

    // Check microphone availability; getUserMedia needs HTTPS and a matching Permissions-Policy.
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      const isSecure = location.protocol === 'https:';
      const hint = isSecure
        ? '🔒 Mikrofon wird von Cloudflare blockiert (Permissions-Policy). Versuche über die direkte LAN-IP zu öffnen.'
        : '🔒 Mic braucht HTTPS! Entweder über yourai.your-domain.example.com öffnen, oder in chrome://flags → "Insecure origins treated as secure" → ' + location.origin + ' eintragen.';
      micBtnEl.title = hint;
      micBtnEl.addEventListener('click', () => {
        if (typeof App !== 'undefined' && App.toast) App.toast(hint, 'warning', 10000);
      });
      micBtnEl.style.opacity = '0.4';
      return;
    }
    micBtnEl.addEventListener('click', _toggleRecording);
  }

  async function _toggleRecording() {
    if (_isRecording) {
      _stopRecording();
    } else {
      await _startRecording();
    }
  }

  async function _startRecording() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      // Prefer webm/opus, fallback to whatever the browser supports
      const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
        ? 'audio/webm;codecs=opus'
        : MediaRecorder.isTypeSupported('audio/webm')
          ? 'audio/webm'
          : '';  // Let browser pick default

      _audioChunks = [];
      _mediaRecorder = new MediaRecorder(stream, mimeType ? { mimeType } : {});

      _mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) _audioChunks.push(e.data);
      };

      _mediaRecorder.onstop = async () => {
        // Stop all tracks to release mic
        stream.getTracks().forEach(t => t.stop());
        await _sendAudioToSTT();
      };

      _mediaRecorder.onerror = (e) => {
        console.error('🎙️ MediaRecorder error:', e);
        stream.getTracks().forEach(t => t.stop());
        _resetMicState();
      };

      _mediaRecorder.start();
      _isRecording = true;
      micBtnEl.classList.add('recording');
      micBtnEl.title = 'Aufnahme stoppen...';
      console.log('🎙️ Recording started');
    } catch (err) {
      console.error('🎙️ Mic access denied:', err);
      if (typeof App !== 'undefined' && App.toast) {
        App.toast('🎙️ Mikrofon-Zugriff verweigert', 'error');
      }
    }
  }

  function _stopRecording() {
    if (_mediaRecorder && _mediaRecorder.state !== 'inactive') {
      _mediaRecorder.stop();
    }
    _isRecording = false;
    micBtnEl.classList.remove('recording');
    micBtnEl.classList.add('processing');
    micBtnEl.title = 'Transkribiere...';
    micBtnEl.disabled = true;
  }

  async function _sendAudioToSTT() {
    if (!_audioChunks.length) {
      _resetMicState();
      return;
    }
    const blob = new Blob(_audioChunks, { type: _mediaRecorder?.mimeType || 'audio/webm' });
    _audioChunks = [];

    if (blob.size < 100) {
      console.warn('🎙️ Audio too short');
      _resetMicState();
      return;
    }

    console.log(`🎙️ Sending ${(blob.size/1024).toFixed(1)} KB audio to STT...`);
    const formData = new FormData();
    formData.append('audio', blob, 'recording.webm');

    try {
      const headers = _chatAuthHeaders();
      // Don't set Content-Type — FormData sets it with boundary
      const res = await fetch('/api/stt' + (localStorage.getItem('yourai_access_key') ? `?key=${localStorage.getItem('yourai_access_key')}` : ''), {
        method: 'POST',
        headers,
        body: formData,
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
        throw new Error(err.detail || `STT Error: ${res.status}`);
      }

      const data = await res.json();
      const text = (data.text || '').trim();

      if (text) {
        // Insert transcribed text into chat input
        const current = inputEl.value;
        inputEl.value = current ? (current + ' ' + text) : text;
        inputEl.style.height = 'auto';
        inputEl.style.height = Math.min(inputEl.scrollHeight, 120) + 'px';
        inputEl.focus();
        console.log('🎙️ STT result:', text);
      } else {
        if (typeof App !== 'undefined' && App.toast) {
          App.toast('🎙️ Keine Sprache erkannt', 'warning');
        }
      }
    } catch (err) {
      console.error('🎙️ STT Error:', err);
      if (typeof App !== 'undefined' && App.toast) {
        App.toast(`🎙️ STT Fehler: ${err.message}`, 'error');
      }
    } finally {
      _resetMicState();
    }
  }

  function _resetMicState() {
    _isRecording = false;
    _mediaRecorder = null;
    _audioChunks = [];
    if (micBtnEl) {
      micBtnEl.classList.remove('recording', 'processing');
      micBtnEl.disabled = false;
      micBtnEl.title = 'Spracheingabe (STT)';
    }
  }

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

  // ─── Promise Confirmation Widget ─────────────────────────────
  function _promiseLabel(promiseData) {
    const lang = (typeof App !== 'undefined' && App.getCurrentLanguage)
      ? App.getCurrentLanguage()
      : 'en';
    const labels = promiseData.labels || {};
    if (labels[lang]) return labels[lang];
    if (promiseData.display_label) return promiseData.display_label;

    const fallbackDe = {
      drink_cocoa_with_caffeine: 'Kakao mit Koffein trinken',
      talk_about_conversation: 'ueber das Gespraech sprechen',
      tell_about_conversation: 'vom Gespraech erzaehlen',
      call_friend: 'einen Freund anrufen',
      watch_anime: 'Anime schauen',
      play_minecraft: 'Minecraft spielen',
      offer_love: 'Liebe anbieten',
    };
    const key = promiseData.promise_name || '';
    if (lang === 'de' && fallbackDe[key]) return fallbackDe[key];
    return key.replace(/_/g, ' ');
  }

  function showPromiseConfirmation(data) {
    chatEmptyEl.hidden = true;
    const promiseData = data.promise_data || {};
    const action = promiseData.action || 'MADE';
    const name = _promiseLabel(promiseData);
    const reasoning = data.content || '';

    const wrap = document.createElement('div');
    wrap.className = 'chat-bubble-wrap yourai promise-confirm-wrap';

    const bubble = document.createElement('div');
    bubble.className = 'chat-bubble yourai promise-confirm';

    const icon = action === 'MADE' ? '🤝' : '💔';
    const label = action === 'MADE' ? 'Promise erkannt' : 'Promise gebrochen';

    bubble.innerHTML = `
      <div class="promise-confirm-header">${icon} ${label}</div>
      <div class="promise-confirm-name">${name.replace(/_/g, ' ')}</div>
      <div class="promise-confirm-detail">${reasoning}</div>
      <div class="promise-confirm-buttons">
        <button class="promise-btn promise-yes" title="Ja, stimmt">Ja</button>
        <button class="promise-btn promise-no" title="Nein, kein Promise">Nein</button>
      </div>
    `;

    const yesBtn = bubble.querySelector('.promise-yes');
    const noBtn = bubble.querySelector('.promise-no');

    function _respond(userAction) {
      yesBtn.disabled = true;
      noBtn.disabled = true;
      App.sendWs({ type: 'promise_response', action: userAction, promise_data: promiseData });
      const resultText = userAction === 'confirm' ? 'Gespeichert' : 'Verworfen';
      const resultIcon = userAction === 'confirm' ? '✅' : '❌';
      bubble.querySelector('.promise-confirm-buttons').innerHTML =
        `<span class="promise-result">${resultIcon} ${resultText}</span>`;
    }

    yesBtn.addEventListener('click', () => _respond('confirm'));
    noBtn.addEventListener('click', () => _respond('reject'));

    wrap.appendChild(bubble);
    messagesEl.appendChild(wrap);
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  // Load cleared IDs first (so WS replay skips cleared messages), then emojis + history
  _loadClearedIds();
  _loadEmojis().then(_restoreHistory);
  _loadImageUsage();
  _setupFileInput();
  _setupMic();

  return { showYourAIMessage, showYourAIImage, showMaintenanceError, showPromiseConfirmation, updateUserLabel, handleMessage, removeTyping, clearHistory, refreshImageUsage, reloadForMode };
})();
