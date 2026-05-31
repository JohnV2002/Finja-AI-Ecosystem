/**
 * Glorpo HTML Functional Shim
 * ===========================
 * Adds browser behavior to Glorpo custom elements.
 *
 * Main Responsibilities:
 * - Mirror key native HTML behaviors for Glorpo tags.
 * - Handle dynamic table markup, forms, links, images, and inputs.
 * - Provide optional debug output when enabled.
 *
 * Side Effects:
 * - Reads and writes cookies/localStorage for debug mode.
 * - Mutates DOM behavior and event handling.
 * - Logs debug output when requested.
 */
(function () {
    'use strict';

    var DEBUG = false;
    try {
        DEBUG = window.localStorage.getItem('glorpoDebug') === '1';
    } catch (_) {}

    try {
        if (DEBUG) {
            document.cookie = 'glorpoDebug=1; path=/; SameSite=Lax';
        } else if (document.cookie.indexOf('glorpoDebug=1') !== -1) {
            document.cookie = 'glorpoDebug=; path=/; Max-Age=0; SameSite=Lax';
        }
    } catch (_) {}

    function debug() {
        if (!DEBUG || !window.console) return;
        var args = Array.prototype.slice.call(arguments);
        args.unshift('[GlorpoFront]');
        console.log.apply(console, args);
    }

    debug('script loaded', {
        readyState: document.readyState,
        href: window.location.href
    });

    var TABLE_HTML_TAGS = {
        table: 'glorptable',
        thead: 'glorpthead',
        tbody: 'glorptbod',
        tr: 'glorprow',
        td: 'glorpcell',
        th: 'glorpthcell',
        div: 'glorpbox',
        span: 'glorpspan'
    };

    var TABLE_HOST_TAGS = {
        GLORPTABLE: true,
        GLORPTHEAD: true,
        GLORPTBOD: true,
        GLORPROW: true,
        GLORPCELL: true,
        GLORPTHCELL: true
    };

    function glorpifyDynamicTableHtml(html) {
        return String(html).replace(/<(\/?)(table|thead|tbody|tr|td|th|div|span)([^>]*?)(\/?)\s*>/gi, function (_, close, tag, attrs, selfclose) {
            return '<' + close + TABLE_HTML_TAGS[tag.toLowerCase()] + attrs + selfclose + '>';
        });
    }

    function installTableInnerHTMLShim() {
        var descriptor = Object.getOwnPropertyDescriptor(Element.prototype, 'innerHTML');
        if (!descriptor || !descriptor.get || !descriptor.set || descriptor.set._glorpoShim) return;

        var nativeGet = descriptor.get;
        var nativeSet = descriptor.set;

        function setInnerHTML(value) {
            if (this && TABLE_HOST_TAGS[this.tagName]) {
                value = glorpifyDynamicTableHtml(value);
            }
            return nativeSet.call(this, value);
        }
        setInnerHTML._glorpoShim = true;

        Object.defineProperty(Element.prototype, 'innerHTML', {
            configurable: true,
            enumerable: descriptor.enumerable,
            get: nativeGet,
            set: setInnerHTML
        });

        debug('table innerHTML shim installed');
    }

    installTableInnerHTMLShim();

    // -- Warp (Link) Handling ---------------------------------------------------
    // <glorpwarp href="..." target="..."> behaves like <a>.
    document.addEventListener('click', function (e) {
        var el = e.target.closest('glorpwarp');
        if (!el) return;
        var href = el.getAttribute('href');
        if (!href) return;
        e.preventDefault();
        var target = el.getAttribute('target') || '_self';
        if (target === '_blank') {
            window.open(href, '_blank', 'noopener,noreferrer');
        } else {
            window.location.href = href;
        }
    });

    // -- Input Styling ----------------------------------------------------------
    // <glorpask type="text" ...> needs a small JS behavior polish beyond CSS.
    function upgradeInputs() {
        var inputs = document.querySelectorAll('glorpask');
        inputs.forEach(function (el) {
            if (el.dataset.glorpUpgraded) return;
            el.dataset.glorpUpgraded = '1';

            var type = el.getAttribute('type') || 'text';

            // Inline styles for a basic input look when not already styled.
            if (!el.style.display || el.style.display === '') {
                el.style.display        = 'inline-block';
                el.style.padding        = '0.3em 0.5em';
                el.style.border         = '1px solid #ccc';
                el.style.borderRadius   = '4px';
                el.style.fontFamily     = 'inherit';
                el.style.fontSize       = '1em';
                el.style.lineHeight     = '1.4';
                el.style.background     = '#fff';
                el.style.color          = '#1a1a1a';
                el.style.outline        = 'none';
            }

            // Checkbox / Radio: kleiner
            if (type === 'checkbox' || type === 'radio') {
                el.style.display = 'inline';
                el.style.width   = 'auto';
                el.style.padding = '0';
            }

            // Placeholder text as a CSS content fallback because real placeholder is unavailable.
            var placeholder = el.getAttribute('placeholder');
            if (placeholder && !el.textContent.trim()) {
                el.setAttribute('data-placeholder', placeholder);
            }

            // Focus Ring
            el.addEventListener('focus', function () {
                el.style.borderColor = '#0066cc';
                el.style.boxShadow   = '0 0 0 2px rgba(0,102,204,0.2)';
            });
            el.addEventListener('blur', function () {
                el.style.borderColor = '#ccc';
                el.style.boxShadow   = 'none';
            });
        });
    }

    // -- Pic (Image) Rendering --------------------------------------------------
    // <glorppic src="..." alt="..." width="..." height="...">
    // Insert a real <img> while keeping the outer Glorpo tag.
    function upgradePics() {
        var pics = document.querySelectorAll('glorppic');
        pics.forEach(function (el) {
            if (el.dataset.glorpUpgraded) return;
            el.dataset.glorpUpgraded = '1';

            var src    = el.getAttribute('src');
            if (!src) return;

            var img    = document.createElement('img');
            img.src    = src;
            img.alt    = el.getAttribute('alt')    || '';
            img.style.maxWidth  = '100%';
            img.style.display   = 'block';
            if (el.getAttribute('width'))  img.width  = el.getAttribute('width');
            if (el.getAttribute('height')) img.height = el.getAttribute('height');

            el.innerHTML = '';
            el.appendChild(img);
        });
    }

    // -- Click (Button) --------------------------------------------------------
    // <glorpclick type="submit" ...> behaves like <button>.
    function upgradeButtons() {
        var btns = document.querySelectorAll('glorpclick');
        btns.forEach(function (el) {
            if (el.dataset.glorpUpgraded) return;
            el.dataset.glorpUpgraded = '1';

            el.style.display     = 'inline-block';
            el.style.cursor      = 'pointer';
            el.style.padding     = '0.4em 1em';
            el.style.border      = '1px solid #0066cc';
            el.style.borderRadius = '4px';
            el.style.background  = '#0066cc';
            el.style.color       = '#fff';
            el.style.fontFamily  = 'inherit';
            el.style.fontSize    = '1em';
            el.style.lineHeight  = '1.4';
            el.style.userSelect  = 'none';

            if (el.hasAttribute('disabled')) {
                el.style.opacity = '0.5';
                el.style.cursor  = 'not-allowed';
            }

            el.addEventListener('click', function () {
                var type   = el.getAttribute('type') || 'button';
                var formId = el.getAttribute('form');
                var form   = formId
                    ? document.getElementById(formId)
                    : el.closest('glorpform');

                if (type === 'submit' && form) {
                    // Trigger native form submit on the glorpform
                    var realForm = form._glorpForm;
                    if (realForm) realForm.submit();
                }
                if (type === 'reset' && form && form._glorpForm) {
                    form._glorpForm.reset();
                }
            });
        });
    }

    // -- Form Handling ----------------------------------------------------------
    // <glorpform action="..." method="...">
    // Attach an invisible real <form> underneath for submit behavior.
    function upgradeForms() {
        var forms = document.querySelectorAll('glorpform');
        forms.forEach(function (el) {
            if (el.dataset.glorpUpgraded) return;
            el.dataset.glorpUpgraded = '1';

            var realForm = document.createElement('form');
            realForm.style.display = 'none';
            realForm.action = el.getAttribute('action') || '';
            realForm.method = el.getAttribute('method') || 'get';
            document.body.appendChild(realForm);
            el._glorpForm = realForm;

            el.style.display = 'block';
        });
    }

    // -- Snap (br) -------------------------------------------------------------
    // <glorpsnap> already uses CSS display:block/line-height:0; keep it explicit.
    function upgradeSnaps() {
        document.querySelectorAll('glorpsnap').forEach(function (el) {
            if (el.dataset.glorpUpgraded) return;
            el.dataset.glorpUpgraded = '1';
            el.innerHTML = '&nbsp;';
            el.style.lineHeight = '0';
            el.style.fontSize   = '0';
            el.style.display    = 'block';
            el.style.margin     = '0';
        });
    }

    // -- Placeholder CSS -------------------------------------------------------
    var placeholderStyle = document.createElement('style');
    placeholderStyle.textContent = [
        'glorpask[data-placeholder]:empty::before {',
        '    content: attr(data-placeholder);',
        '    color: #aaa;',
        '    pointer-events: none;',
        '}',
        'glorpwarp { cursor: pointer; }',
        'glorpclick { box-sizing: border-box; }',
    ].join('\n');
    document.head.appendChild(placeholderStyle);

    // -- Run on DOM ready ------------------------------------------------------
    var isUpgrading = false;
    function upgradeAll() {
        if (isUpgrading) return;
        debug('upgrade start', { readyState: document.readyState });
        isUpgrading = true;
        upgradeInputs();
        upgradePics();
        upgradeButtons();
        upgradeForms();
        upgradeSnaps();
        isUpgrading = false;
        window.GlorpoFront = window.GlorpoFront || {};
        window.GlorpoFront.ready = true;
        debug('upgrade done', {
            bodyChildren: document.body ? document.body.children.length : null,
            ready: window.GlorpoFront.ready
        });
    }

    function runOnceBeforeAppSettles() {
        if (window.GlorpoFront && window.GlorpoFront.ready) {
            debug('auto fallback skipped, already ready');
            return;
        }
        debug('auto fallback running');
        upgradeAll();
        window.GlorpoFront = window.GlorpoFront || {};
        window.GlorpoFront.ready = true;
        window.dispatchEvent(new CustomEvent('glorpo:ready'));
        debug('glorpo:ready dispatched');
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', runOnceBeforeAppSettles, { once: true });
    } else {
        runOnceBeforeAppSettles();
    }

    // No global MutationObserver here.
    // Real websites often run Lottie, analytics, consent widgets, Cloudflare scripts,
    // and other code that mutates the DOM constantly. Observing the whole page would
    // make Glorpo rescan forever and can degrade or break the site after a while.
    window.GlorpoFront = window.GlorpoFront || {};
    window.GlorpoFront.upgrade = upgradeAll;

})();
