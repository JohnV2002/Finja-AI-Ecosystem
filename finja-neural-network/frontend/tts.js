/* ══════════════════════════════════════════════════════════════════
   tts.js — Text-to-Speech Module (3 Tiers)

   Tier 1: browser     → Web Speech API (speechSynthesis), immer gratis
   Tier 2: yourai       → Chatterbox Multilingual via DeepInfra, gratis, YourAIs Stimme
   Tier 3: elevenlabs  → ElevenLabs Premium API, YourAIs echte Stimme (3×/Monat gratis)

   Settings werden in localStorage gespeichert (pro User/Key).
══════════════════════════════════════════════════════════════════ */

const TTS = (() => {
  const _accessKey  = localStorage.getItem('yourai_access_key') || 'guest';
  const _TIER_KEY   = `yourai_tts_tier_${_accessKey}`;
  const _AUTO_KEY   = `yourai_tts_autoplay_${_accessKey}`;

  function _authHeaders() {
    const h = {};
    if (_accessKey && _accessKey !== 'guest') h['Authorization'] = `Bearer ${_accessKey}`;
    const uuid = (typeof YourAIUUID !== 'undefined') ? YourAIUUID.get() : null;
    if (uuid) h['X-Session-UUID'] = uuid;
    return h;
  }

  let _tier     = localStorage.getItem(_TIER_KEY)   || 'browser';
  let _autoPlay = localStorage.getItem(_AUTO_KEY)   === 'true';
  let _currentAudio = null;

  // ─── Getters / Setters ───────────────────────────────────────
  function getTier()     { return _tier; }
  function isAutoPlay()  { return _autoPlay; }

  function setTier(tier) {
    _tier = tier;
    localStorage.setItem(_TIER_KEY, tier);
  }

  function setAutoPlay(val) {
    _autoPlay = Boolean(val);
    localStorage.setItem(_AUTO_KEY, _autoPlay);
  }

  // ─── Stop current playback ───────────────────────────────────
  function stop() {
    try { window.speechSynthesis?.cancel(); } catch { /* ignore */ }
    if (_currentAudio) {
      _currentAudio.pause();
      _currentAudio = null;
    }
  }

  // ─── Text cleaner (strip markdown for TTS) ───────────────────
  function cleanText(text) {
    return text
      .replace(/```[\s\S]*?```/g, '')            // code blocks
      .replace(/`[^`]+`/g, '')                   // inline code
      .replace(/\*\*?([^*\n]+)\*\*?/g, '$1')    // bold / italic
      .replace(/#{1,6}\s*/g, '')                 // headers
      .replace(/!\[[^\]]*\]\([^)]+\)/g, '')      // images
      .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')  // links
      .replace(/[>|\-*+]{1,2}\s/g, '')           // blockquotes / lists
      .replace(/\n+/g, ' ')
      .replace(/\s+/g, ' ')
      .trim();
  }

  // ─── Main speak entry point ──────────────────────────────────
  // onEnd: optional callback — called when audio finished playing
  async function speak(rawText, onEnd) {
    const text = cleanText(rawText);
    if (!text) { onEnd?.(); return; }
    stop();

    if (_tier === 'browser') {
      _speakBrowser(text, onEnd);

    } else if (_tier === 'yourai') {
      await _speakYourAI(text, onEnd);

    } else if (_tier === 'elevenlabs') {
      await _speakElevenLabs(text, onEnd);
    }
  }

  // ─── Tier 1: Web Speech API ───────────────────────────────────
  function _speakBrowser(text, onEnd) {
    if (!window.speechSynthesis) {
      console.warn('🔊 [TTS] speechSynthesis nicht verfügbar');
      onEnd?.();
      return;
    }
    const utt    = new SpeechSynthesisUtterance(text);
    utt.lang     = 'de-DE';
    utt.rate     = 1.0;
    utt.pitch    = 1.0;
    utt.onend    = () => onEnd?.();
    utt.onerror  = () => onEnd?.();
    window.speechSynthesis.speak(utt);
  }

  // ─── Tier 2: YourAI Voice (XTTS via VM) ───────────────────────
  async function _speakYourAI(text, onEnd) {
    try {
      const res = await fetch('/api/tts', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json', ..._authHeaders() },
        body:    JSON.stringify({ text, tier: 'yourai', lang: 'de' }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        const detail = err.detail || res.statusText;
        console.warn(`🦊 [TTS] YourAI 503 Detail: ${detail}`);
        if (res.status === 503) {
          if (typeof App !== 'undefined') {
            App.toast(`🦊 ${detail}`, 'info');
          }
        } else {
          if (typeof App !== 'undefined') App.toast(`🦊 TTS Fehler: ${detail}`, 'error');
        }
        _speakBrowser(text, onEnd);
        return;
      }

      const blob = await res.blob();
      const url  = URL.createObjectURL(blob);
      _currentAudio = new Audio(url);
      _currentAudio.onended = () => {
        URL.revokeObjectURL(url);
        _currentAudio = null;
        onEnd?.();
      };
      _currentAudio.onerror = () => {
        URL.revokeObjectURL(url);
        _currentAudio = null;
        _speakBrowser(text, onEnd);  // fallback on playback error
      };
      await _currentAudio.play();

    } catch (e) {
      console.warn('🔊 [TTS] YourAI Voice Fehler:', e);
      _speakBrowser(text, onEnd);
    }
  }

  // ─── Tier 3: ElevenLabs API ───────────────────────────────────
  async function _speakElevenLabs(text, onEnd) {
    try {
      const res = await fetch('/api/tts', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json', ..._authHeaders() },
        body:    JSON.stringify({ text, tier: 'elevenlabs', lang: 'de' }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        const msg = err.detail || res.statusText;

        // 429 = Monatslimit erreicht → spezielle Nachricht
        if (res.status === 429) {
          if (typeof App !== 'undefined') {
            App.toast(`⭐ ${msg}`, 'info');
          }
          // Dispatch event so config.js can update the usage display
          window.dispatchEvent(new CustomEvent('tts_limit_reached'));
        } else {
          if (typeof App !== 'undefined') App.toast(`⭐ TTS Fehler: ${msg}`, 'error');
          _speakBrowser(text, onEnd);  // fallback only on real errors
        }
        onEnd?.();
        return;
      }

      // Update remaining from response header
      const remaining = res.headers.get('X-TTS-Remaining');
      if (remaining !== null) {
        window.dispatchEvent(new CustomEvent('tts_usage_update', { detail: { remaining: parseInt(remaining) } }));
      }

      const blob = await res.blob();
      const url  = URL.createObjectURL(blob);
      _currentAudio = new Audio(url);
      _currentAudio.onended = () => {
        URL.revokeObjectURL(url);
        _currentAudio = null;
        onEnd?.();
      };
      _currentAudio.onerror = () => {
        URL.revokeObjectURL(url);
        _currentAudio = null;
        if (typeof App !== 'undefined') App.toast('⭐ Audio konnte nicht abgespielt werden', 'error');
        onEnd?.();
      };
      await _currentAudio.play();

    } catch (e) {
      console.error('🔊 [TTS] ElevenLabs Fehler:', e);
      if (typeof App !== 'undefined') App.toast(`⭐ TTS Fehler: ${e.message}`, 'error');
      _speakBrowser(text, onEnd);
    }
  }

  return { speak, stop, cleanText, getTier, setTier, isAutoPlay, setAutoPlay };
})();
