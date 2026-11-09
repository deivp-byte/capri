"""
abilities/web_search_engine.py - Real-Time Web Search & Live News Engine for Capri / Spider-Man

Provides live internet access, current affairs retrieval, and search synthesis:
- Real-time news via Google News RSS (~0.5s latency, zero API keys, no rate limits).
- Web snippet extraction via DuckDuckGo (~1s latency, zero API keys).
- Topic-specific search (companies, finance, technology, world news, current events).
- Designed for offline local SLMs to grant 100% real-time internet awareness.
"""

from __future__ import annotations

import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional


USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


def get_live_news(topic: str = "", limit: int = 4, **kwargs) -> str:
    """
    Retrieves live breaking news and current affairs from the web in real-time.

    Args:
        topic: Specific news topic or keyword (e.g. 'Nvidia', 'inteligencia artificial', 'tecnologia').
               Leave blank for general top breaking news.
        limit: Number of news headlines to retrieve (default 4).

    Returns:
        str: Structured news headlines with sources and publication info for Spider-Man.
    """
    clean_topic = (topic or kwargs.get("query") or kwargs.get("q") or "").strip()
    
    # Filter out generic filler words
    for filler in ("noticias", "noticia", "hoy", "mundo", "actualidad", "del dia", "en el mundo", "importantes", "que pasa"):
        clean_topic = re.sub(rf'\b{filler}\b', '', clean_topic, flags=re.I).strip()

    try:
        if clean_topic:
            encoded = urllib.parse.quote(clean_topic)
            url = f"https://news.google.com/rss/search?q={encoded}&hl=es&gl=ES&ceid=ES:es"
        else:
            url = "https://news.google.com/rss?hl=es&gl=ES&ceid=ES:es"

        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=4.5) as resp:
            content = resp.read()

        root = ET.fromstring(content)
        items = root.findall(".//item")[:limit]
        if not items:
            # Fallback to general news if topic search yielded nothing
            if clean_topic:
                return search_web_information(clean_topic, limit=limit)
            return "Status: No se encontraron noticias de última hora en este momento."

        report = [
            f"Status: Noticias y actualidad en tiempo real" + (f" sobre '{clean_topic}':" if clean_topic else " (Titulares de hoy):")
        ]
        for idx, item in enumerate(items, 1):
            title = item.find("title").text if item.find("title") is not None else "Sin título"
            pub = item.find("pubDate").text if item.find("pubDate") is not None else ""
            desc = item.find("description").text if item.find("description") is not None else ""
            clean_desc = re.sub(r'<[^<]+?>', '', desc).strip()
            # Clean source from title if duplicate
            report.append(f"{idx}. {title}")
            if clean_desc and len(clean_desc) > 20 and clean_desc != title:
                report.append(f"   Detalle: {clean_desc[:180]}")

        return "\n".join(report)

    except Exception as err:
        # Fallback to web search
        if clean_topic:
            return search_web_information(clean_topic, limit=limit)
        return f"Status: Error al conectar con el servicio de noticias ({err})."


def search_web_information(query: str = "", limit: int = 4, **kwargs) -> str:
    """
    Searches the live web for factual information, questions, or entities.

    Args:
        query: Search query or question.
        limit: Max search result snippets.

    Returns:
        str: Factual snippets extracted from the live internet.
    """
    clean_q = (query or kwargs.get("q") or kwargs.get("target") or "").strip()
    if not clean_q:
        return "Status: Error - Consulta de búsqueda vacía."

    # Try DuckDuckGo HTML search
    try:
        url = "https://html.duckduckgo.com/html/"
        data = urllib.parse.urlencode({"q": clean_q}).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "User-Agent": USER_AGENT,
                "Referer": "https://html.duckduckgo.com/",
            }
        )
        with urllib.request.urlopen(req, timeout=4.5) as resp:
            html = resp.read().decode("utf-8", errors="ignore")

        snippets = re.findall(r'<a class="result__snippet[^"]*"[^>]*>(.*?)</a>', html, re.S)
        if snippets:
            results = []
            for s in snippets[:limit]:
                clean_s = re.sub(r'<[^<]+?>', '', s).strip()
                clean_s = re.sub(r'\s+', ' ', clean_s)
                if clean_s:
                    results.append(clean_s)

            if results:
                report = [f"Status: Información encontrada en internet para '{clean_q}':"]
                for i, r in enumerate(results, 1):
                    report.append(f"- {r}")
                return "\n".join(report)

    except Exception:
        pass

    # Fallback: Google News search for entity
    try:
        news_res = get_live_news(topic=clean_q, limit=limit)
        if "Status: Error" not in news_res and "No se encontraron" not in news_res:
            return news_res
    except Exception:
        pass

    return f"Status: No se pudieron extraer datos web directos para '{clean_q}'. Intenta reformular los términos de búsqueda."


def smart_web_research(query: str = "", **kwargs) -> str:
    """
    Hybrid intelligent research tool:
    Automatically routes between real-time news headlines and factual web search.
    """
    raw = (query or kwargs.get("q") or kwargs.get("topic") or "").strip()
    if not raw:
        return get_live_news()

    low = raw.lower()
    # Check if query is news or recent event oriented
    is_news = any(w in low for w in (
        "noticia", "noticias", "hoy", "ayer", "reciente", "caida", "caída",
        "subida", "mercado", "actualidad", "suceso", "pasa en", "paso con", "pasó con"
    ))

    if is_news:
        res = get_live_news(topic=raw)
        if "Status: Error" not in res:
            return res

    return search_web_information(query=raw)
