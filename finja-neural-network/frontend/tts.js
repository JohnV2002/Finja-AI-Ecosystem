/*
  YourAI TTS Frontend
  ==================
  Frontend module for the YourAI dashboard.

  Main Responsibilities:
  - Manage browser and premium text-to-speech playback.
  - Select TTS providers and voices for dashboard responses.
  - Coordinate TTS API calls and local speech synthesis.

  Side Effects:
  - Uses browser speechSynthesis when available.
  - Requests audio from backend TTS endpoints.
  - Plays audio in the browser.
*/
const TTS = (() => {
  const _accessKey  = localStorage.getItem('yourai_access_key') || 'guest';
  const _TIER_KEY   = `yourai_tts_tier_${_accessKey}`;
  const _AUTO_KEY   = `yourai_tts_autoplay_${_accessKey}`;

  function _authHeaders() {
    return YourAIAPI.authHeaders();
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
    return YourAIText.cleanForSpeech(text);
  }

  // ─── Main speak entry point ──────────────────────────────────
  // onEnd: optional callback — called when audio finished playing
  async function speak(rawText, onEnd) {
    let text = cleanText(rawText);
    if (!text) { onEnd?.(); return; }
    stop();

    if (_tier === 'browser') {
      _speakBrowser(text, onEnd);

    } else if (_tier === 'yourai') {
      // Tier 2: Text kappen — Backend chunkt bei 1800 Zeichen, Cloudflare Timeout 100s
      if (text.length > 1500) {
        const cut = text.lastIndexOf(' ', 1500);
        text = text.substring(0, cut > 500 ? cut : 1500);
      }
      await _speakYourAI(text, onEnd);

    } else if (_tier === 'elevenlabs') {
      await _speakElevenLabs(text, onEnd);
    }
  }

  // ─── Tier 1: Web Speech API ───────────────────────────────────
  function _speakBrowser(text, onEnd) {
    if (!window.speechSynthesis) {
      console.warn('🔊 [TTS] speechSynthesis is not available');
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
        const detail = err.detail || res.statusText || `HTTP ${res.status}`;
        const status = res.status;
        if (status === 524) {
          console.warn(`🦊 [TTS] Cloudflare Timeout (524) — Generierung dauerte zu lange`);
          if (typeof App !== 'undefined') App.toast('🦊 TTS Timeout — Text war zu lang oder Server überlastet', 'info');
        } else if (status === 503) {
          console.warn(`🦊 [TTS] Service Unavailable: ${detail}`);
          if (typeof App !== 'undefined') App.toast(`🦊 ${detail}`, 'info');
        } else {
          console.warn(`🦊 [TTS] Error ${status}: ${detail}`);
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
      console.warn('🔊 [TTS] YourAI Voice error:', e);
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
      console.error('🔊 [TTS] ElevenLabs error:', e);
      if (typeof App !== 'undefined') App.toast(`⭐ TTS Fehler: ${e.message}`, 'error');
      _speakBrowser(text, onEnd);
    }
  }

  return { speak, stop, cleanText, getTier, setTier, isAutoPlay, setAutoPlay };
})();
