# 🦊 autonom_website/

Hier liegen YourAIs aktuelle Website-Dateien.
Der Docker-Container liest sie **lokal** → kein Cloudflare-Scrape nötig!

## Dateien hier ablegen:

| Datei | Was es ist |
|-------|-----------|
| `yourai.html` | YourAIs Haupt-HTML (`https://your-domain.example.com/yourai.html`) |
| `yourai.css` | Das zugehörige CSS (`https://your-domain.example.com/CSS/yourai.css`) |
| `scroll_reveal.js` | Das JS (`https://your-domain.example.com/scripts/scroll_reveal.js`) |

## Workflow:

1. Datei auf deinem PC bearbeiten / downloaden
2. Hier rein kopieren (SCP / NAS-Mount)
3. YourAI liest beim nächsten `[REDESIGN:]` automatisch die lokale Version
4. Nach erfolgreichem Deploy schreibt YourAI die neue Version zurück hierhin

## Pfade im Docker:

```
/app/autonom_website/yourai.html
/app/autonom_website/yourai.css
/app/autonom_website/scroll_reveal.js
```

Gesetzt via `.env`:
```
YOURAI_HTML_PATH=/app/autonom_website/yourai.html
YOURAI_CSS_PATH=/app/autonom_website/yourai.css
YOURAI_JS_PATH=/app/autonom_website/scroll_reveal.js
```
