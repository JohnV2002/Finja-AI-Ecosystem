# main.py
# Hybrid Proxy: TOR + DuckDuckGo + Crawler-Fallback

"""
======================================================================
                     Web Crawler API – Main
======================================================================

  Project: Web Crawler API
  Version: 1.0.0
  Author:  J. Apps (Sodakiller1)
  License: MIT License (c) 2026 J. Apps

----------------------------------------------------------------------
 Features:
 ---------------------------------------------------------------------
  • Fast, hybrid web crawler with Tor support
  • Primary search via DuckDuckGo (ddgs)
  • Automatic fallback to Google HTML scraping when results are low
  • Runs via Tor (socks5h://tor:9050) for enhanced privacy
  • REST API provided with FastAPI
  • Secure authentication via Bearer Token
  • Parsing via BeautifulSoup (Title, Link, Snippet)
  • CLI Logging with status messages
  • Configurable timeout & retry delay for Google fallback
  • Docker & Compose ready for containerized deployment
  • Clean JSON responses for easy integration into other systems

----------------------------------------------------------------------
 New in v1.0.0:
 ---------------------------------------------------------------------

----------------------------------------------------------------------
 To-Dos:
 ---------------------------------------------------------------------
 
  • Implement rate limiting
  • Improve error handling and security (More checks, advanced Auth)
  • Optimize Google HTML scraping (or move away from Google entirely!)
  • Implement other search engines as fallback
  
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
from urllib.parse import urlparse, parse_qs
from typing import Annotated

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Tor SOCKS Proxy for DDGS
TOR_PROXY = 'socks5h://tor:9050'

# User-Agents for the Crawler
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
]

app = FastAPI()

# Optional: API Key for authentication. It is highly recommended to change and use this in the .env!
load_dotenv()
EXPECTED_BEARER_TOKEN = os.getenv("BEARER_TOKEN")

class SearchRequest(BaseModel):
    query: str
    count: int

class SearchResult(BaseModel):
    link: str
    title: str | None = None
    snippet: str | None = None

@app.post("/search", responses={401: {"description": "Unauthorized"}})
async def external_search(
    search_request: Annotated[SearchRequest, Body(...)],
    authorization: Annotated[str | None, Header()] = None,
):
    if EXPECTED_BEARER_TOKEN:
        expected_auth_header = f"Bearer {EXPECTED_BEARER_TOKEN}"
        if authorization != expected_auth_header:
            raise HTTPException(status_code=401, detail="Unauthorized")

    query = search_request.query
    count = search_request.count

    logger.info(f"Search started: {query} (max {count} results)")

    results = ddg_search(query, count)

    if len(results) < count:
        logger.info(f"DuckDuckGo returned too few results ({len(results)}/{count}) -> Activating fallback crawler!")
        crawler_results = google_crawler(query, count - len(results))
        results.extend(crawler_results)

    if not results:
        logger.warning("No results found, returning fallback link!")
        results.append(SearchResult(
            link="https://en.wikipedia.org/wiki/Tabby_cat",
            title="🐾 Tabby Cat Fallback",
            snippet="I couldn't find anything... But here is a cat. Sometimes they help more than Google. 😊"
        ))

    logger.info(f"Returning {len(results)} results")
    return results

def ddg_search(query: str, count: int) -> list[SearchResult]:
    try:
        logger.info(f"Starting DuckDuckGo search with proxy: {TOR_PROXY}")
        with DDGS(proxy=TOR_PROXY) as ddgs:
            search_results = ddgs.text(query, safesearch="moderate", max_results=count)
        return [SearchResult(
            link=result["href"],
            title=result.get("title"),
            snippet=result.get("body")
        ) for result in search_results]
    except Exception as e:
        logger.error(f"Error during DuckDuckGo search: {e}")
        return []

def _parse_google_html(html_text: str, count: int) -> list[SearchResult]:
    """Helper method to parse Google HTML and reduce cognitive complexity."""
    soup = BeautifulSoup(html_text, 'html.parser')
    result_elements = soup.select('div.g')
    results = []

    for element in result_elements[:count]:
        link_tag = element.find('a', href=True)
        title_tag = element.find('h3')
        snippet_tag = element.find('span', {'class': 'aCOpRe'})

        if not (link_tag and title_tag and isinstance(link_tag, Tag)):
            continue

        href = link_tag.get('href')
        if not isinstance(href, str):
            continue

        if href.startswith('/url?q='):
            parsed = parse_qs(urlparse(href).query)
            href = parsed.get('q', [None])[0]
            
        if not (href and isinstance(href, str) and href.startswith('http')):
            continue

        results.append(SearchResult(
            link=href,
            title=title_tag.get_text(strip=True),
            snippet=snippet_tag.get_text(strip=True) if snippet_tag else None
        ))
    return results

def google_crawler(query: str, count: int) -> list[SearchResult]:
    logger.info(f"Starting Google Fallback Crawler for query: {query}")
    headers = {
        "User-Agent": secrets.choice(USER_AGENTS)
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

        # REQUIRED SLEEP TO PREVENT GOOGLE IP BANS ⬇⬇⬇
        time.sleep(3)

        if response.status_code != 200:
            logger.error(f"Crawler HTTP Error: {response.status_code}")
            return []

        results = _parse_google_html(response.text, count)
        logger.info(f"Crawler found {len(results)} results")
        return results

    except Exception as e:
        logger.error(f"Error in crawler: {e}")
        return []

if __name__ == "__main__":
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "80"))
    logger.info(f"Starting DuckDuckGo Tor Proxy on {host}:{port}...")
    uvicorn.run("main:app", host=host, port=port)
