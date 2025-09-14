# main.py
# Hybrid Proxy: TOR + DuckDuckGo + Crawler-Fallback

"""
======================================================================
                     Web Crawler API – Main
======================================================================

  Project: Web Crawler API
  Version: 1.0.0
  Author:  J. Apps (Sodakiller1)
  License: MIT License (c) 2025 J. Apps

----------------------------------------------------------------------
 Features:
 ---------------------------------------------------------------------
  • Schneller, hybrider Web-Crawler mit Tor-Support
  • Primäre Suche über DuckDuckGo (ddgs)
  • Automatischer Fallback auf Google-HTML-Scraping bei zu wenigen Ergebnissen
  • Läuft über Tor (socks5h://tor:9050) für mehr Privatsphäre
  • REST-API mit FastAPI bereitgestellt
  • Sichere Authentifizierung via Bearer-Token
  • Parsing via BeautifulSoup (Titel, Link, Snippet)
  • CLI-Logging mit Statusmeldungen
  • Konfigurierbarer Timeout & Retry-Delay beim Google-Fallback
  • Docker- & Compose-ready für Containerbetrieb
  • Saubere JSON-Responses für einfache Integration in andere Systeme

----------------------------------------------------------------------
 Neu in v1.0.0:
 ---------------------------------------------------------------------

----------------------------------------------------------------------
 To-Dos:
 ---------------------------------------------------------------------
 
 • Implementierung von Rate-Limiting
 • Verbesserung der Fehlerbehandlung und Security (Mehr schecks? - Mehr Auth).
 • Optimierung der Google-HTML-Scrap <-- vllt auch weg von GOOGLE! <--
    <-- Benutzung anderer "Such"-Maschinen als fallback
  

======================================================================
"""


import uvicorn
from fastapi import FastAPI, Header, Body, HTTPException
from pydantic import BaseModel
import requests
from bs4 import BeautifulSoup, Tag
from ddgs import DDGS
import logging
import time
import random
from dotenv import load_dotenv
import os

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Tor SOCKS Proxy für DDGS
TOR_PROXY = 'socks5h://tor:9050'

# User-Agents für Crawler
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
]

app = FastAPI()

# Optional: API-Key für Auth !WIRD EMPFOLEN ZUÄNDERN UND ZU BENUTZEN! - änderung in der .env
load_dotenv()
EXPECTED_BEARER_TOKEN = os.getenv("BEARER_TOKEN")

class SearchRequest(BaseModel):
    query: str
    count: int

class SearchResult(BaseModel):
    link: str
    title: str | None = None
    snippet: str | None = None

@app.post("/search")
async def external_search(
    search_request: SearchRequest = Body(...),
    authorization: str | None = Header(None),
):
    if EXPECTED_BEARER_TOKEN:
        expected_auth_header = f"Bearer {EXPECTED_BEARER_TOKEN}"
        if authorization != expected_auth_header:
            raise HTTPException(status_code=401, detail="Unauthorized")

    query = search_request.query
    count = search_request.count

    logger.info(f"Suche gestartet: {query} (max {count} Ergebnisse)")

    results = ddg_search(query, count)

    if len(results) < count:
        logger.info(f"DuckDuckGo zu wenig Ergebnisse ({len(results)}/{count}) -> Aktiviere Fallback-Crawler!")
        crawler_results = google_crawler(query, count - len(results))
        results.extend(crawler_results)

    if not results:
        logger.warning("Keine Ergebnisse gefunden, nutze Fallback-Link!")
        results.append(SearchResult(
            link="https://de.wikipedia.org/wiki/Tabby",
            title="🐾 Tabby-Katzen-Fallback",
            snippet="Ich konnte nichts finden... Aber hier ist eine Katze. Manchmal hilft sie mehr als Google. 😊"
        ))

    logger.info(f"Gebe {len(results)} Ergebnisse zurück")
    return results

def ddg_search(query, count):
    try:
        logger.info(f"Starte DuckDuckGo-Suche mit Proxy: {TOR_PROXY}")
        with DDGS(proxy=TOR_PROXY) as ddgs:
            search_results = ddgs.text(query, safesearch="moderate", max_results=count)
        return [SearchResult(
            link=result["href"],
            title=result.get("title"),
            snippet=result.get("body")
        ) for result in search_results]
    except Exception as e:
        logger.error(f"Fehler bei DuckDuckGo-Suche: {e}")
        return []

def google_crawler(query, count):
    logger.info(f"Starte Google-Fallback-Crawler für Query: {query}")
    headers = {
        "User-Agent": random.choice(USER_AGENTS)
    }
    try:
        
        proxies = {
            "http": TOR_PROXY,
            "https": TOR_PROXY
        }

        response = requests.get(
            f"https://www.google.com/search?q={query}",
            proxies=proxies,
            headers=headers,
            timeout=10
        )
        logger.info(f"Google Crawler HTTP Status: {response.status_code}")

        #  HIER KOMMT DER SLEEP DAMIT GOOGLE UNS NICHT BANNT ⬇⬇⬇
        time.sleep(3)

        if response.status_code != 200:
            logger.error(f"Crawler HTTP Error: {response.status_code}")
            return []

        soup = BeautifulSoup(response.text, 'html.parser')
        result_elements = soup.select('div.g')
        results = []

        for element in result_elements[:count]:
            link_tag = element.find('a', href=True)
            title_tag = element.find('h3')
            snippet_tag = element.find('span', {'class': 'aCOpRe'})

            if link_tag and title_tag and isinstance(link_tag, Tag):
                href = link_tag.get('href')  # ✅ Safe Methode!
                if isinstance(href, str):
                    if href.startswith('/url?q='):
                        from urllib.parse import urlparse, parse_qs
                        parsed = parse_qs(urlparse(href).query)
                        href = parsed.get('q', [None])[0]
                    
                    if href and isinstance(href, str) and href.startswith('http'):
                        results.append(SearchResult(
                            link=href,
                            title=title_tag.get_text(strip=True),
                            snippet=snippet_tag.get_text(strip=True) if snippet_tag else None
                ))

        logger.info(f"Crawler hat {len(results)} Ergebnisse gefunden")
        return results

    except Exception as e:
        logger.error(f"Fehler im Crawler: {e}")
        return []

if __name__ == "__main__":
    logger.info("Starte DuckDuckGo-Tor-Proxy auf Port 80...")
    uvicorn.run("main:app", host="0.0.0.0", port=80)
