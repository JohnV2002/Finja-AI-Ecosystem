/*
  YourAI Cookie Consent Frontend
  =============================
  Frontend module for the YourAI dashboard.

  Main Responsibilities:
  - Show and manage the analytics consent banner.
  - Persist the user consent decision locally.
  - Initialize analytics behavior based on consent state.

  Side Effects:
  - Reads and writes cookie consent in localStorage.
  - Updates the cookie banner DOM state.
*/
// cookies.js — Umami Analytics Consent (YourAI Dashboard)

document.addEventListener('DOMContentLoaded', () => {
  const banner   = document.getElementById('cookieConsentBanner');
  const acceptBtn = document.getElementById('cookieAcceptBtn');
  const rejectBtn = document.getElementById('cookieRejectBtn');

  // ── Umami ──────────────────────────────────────────────
  function loadUmami() {
    if (document.querySelector('script[src="https://umami.your-domain.example.com/script.js"]')) return;
    const s = document.createElement('script');
    s.defer = true;
    s.src = 'https://umami.your-domain.example.com/script.js';
    s.setAttribute('data-website-id', '3b4dc4b6-2f33-4444-a9ee-dd933f1c2f3e');
    document.head.appendChild(s);
  }

  function removeUmami() {
    const s = document.querySelector('script[src="https://umami.your-domain.example.com/script.js"]');
    if (s) s.remove();
  }

  // ── Cookie helpers ─────────────────────────────────────
  function getCookie(name) {
    const v = `; ${document.cookie}`;
    const parts = v.split(`; ${name}=`);
    if (parts.length === 2) return parts.pop().split(';').shift();
  }

  function setCookie(name, value, maxAge) {
    const secure = location.protocol === 'https:' ? '; Secure' : '';
    document.cookie = `${name}=${value}; max-age=${maxAge}; SameSite=Lax${secure}; path=/`;
  }

  // ── Consent logic ──────────────────────────────────────
  function applyConsent() {
    if (!banner) return;
    const consent = getCookie('yourai_analytics');
    if (consent === 'yes') {
      banner.classList.add('hide');
      loadUmami();
    } else if (consent === 'no') {
      banner.classList.add('hide');
      removeUmami();
    } else {
      banner.classList.remove('hide');
    }
  }

  if (acceptBtn) {
    acceptBtn.onclick = () => {
      setCookie('yourai_analytics', 'yes', 60 * 60 * 24 * 180); // 180 Tage
      banner?.classList.add('hide');
      loadUmami();
    };
  }

  if (rejectBtn) {
    rejectBtn.onclick = () => {
      setCookie('yourai_analytics', 'no', 60 * 60 * 24 * 180);
      banner?.classList.add('hide');
      removeUmami();
    };
  }

  applyConsent();
});
