"""
Smart Semantic Intent Parser: Expands Spider-Man / Capri's comprehension
of natural language desktop and browser requests.
Handles compound instructions, preposition variations ("en brave busca youtube"),
browser targeting, web service routing, and multi-step chained actions.
"""
from __future__ import annotations

import re
from typing import Optional, Tuple, Dict, Any, List

from abilities.app_finder import KNOWN_WEB_SERVICES


# Common browser names recognized in natural speech
KNOWN_BROWSERS = {
    "brave": "brave",
    "brave browser": "brave",
    "chrome": "chrome",
    "google chrome": "chrome",
    "edge": "edge",
    "microsoft edge": "edge",
    "firefox": "firefox",
    "mozilla": "firefox",
    "opera": "opera",
    "navegador": "navegador",
    "el navegador": "navegador",
    "mi navegador": "navegador",
    "browser": "navegador",
    "internet": "navegador",
}

# Recognized search engines and platforms
KNOWN_SEARCH_PLATFORMS = {
    "youtube": "youtube",
    "google": "google",
    "github": "github",
    "wikipedia": "wikipedia",
    "reddit": "reddit",
    "twitch": "twitch",
    "duckduckgo": "duckduckgo",
    "bing": "bing",
    "twitter": "twitter",
    "x": "x",
}


def parse_browser_or_search_request(text: str) -> Optional[Dict[str, Any]]:
    """
    Parses requests like:
      - "en brave busca youtube" -> browser="brave", query="youtube"
      - "en chrome busca recetas" -> browser="chrome", query="recetas"
      - "entra a brave y busca canciones" -> browser="brave", query="canciones"
      - "abre brave y busca youtube" -> browser="brave", query="youtube"
      - "busca youtube en brave" -> browser="brave", query="youtube"
      - "en youtube busca videos de risa" -> platform="youtube", query="videos de risa"
      - "abre youtube y busca musica" -> platform="youtube", query="musica"
      - "busca musica en youtube" -> platform="youtube", query="musica"
      - "entra a youtube" -> direct_url="https://www.youtube.com"

    Returns a dict with intent specification or None.
    """
    t = (text or "").strip()
    if not t:
        return None

    low = t.lower().strip(" .!?¿¡")

    # 1. Pattern: "[en|desde|con] <browser/app> [y]? [busca|buscar|pon|ver] <query>"
    # e.g. "en brave busca youtube", "en brave pon youtube", "en chrome busca noticias"
    m_en_app = re.match(
        r'^(?:por\s+favor\s+)?(?:en|desde|usando|con)\s+([a-zA-Z0-9_-]+(?:\s+browser)?)\s+(?:y\s+)?(?:busca|buscar|search|pon|reproduce|mira|ver)\s+(.+)$',
        low
    )
    if m_en_app:
        app_part = m_en_app.group(1).strip()
        query_part = m_en_app.group(2).strip()

        # Is the target a browser?
        if app_part in KNOWN_BROWSERS or "brave" in app_part or "chrome" in app_part or "edge" in app_part or "firefox" in app_part:
            browser_name = KNOWN_BROWSERS.get(app_part, app_part)
            return {
                "action": "browser_search",
                "browser": browser_name,
                "query": query_part,
                "engine": "google",
            }
        # Is the target a search platform? (e.g. "en youtube busca videos")
        if app_part in KNOWN_SEARCH_PLATFORMS:
            return {
                "action": "browser_search",
                "browser": "",
                "query": query_part,
                "engine": app_part,
            }

    # 2. Pattern: "[entra a|abre|accede a|inicia] <browser> y [busca|buscar|pon|ver] <query>"
    # e.g. "entra a brave y busca youtube", "abre el navegador y busca recetas"
    m_open_and_search = re.match(
        r'^(?:por\s+favor\s+)?(?:entra|ve|accede|abre|inicia)\s*(?:a|en)?\s*(?:el\s+|mi\s+)?([a-zA-Z0-9_-]+(?:\s+web|\s+browser)?)\s+y\s+(?:busca|buscar|search|pon|mira)\s+(.+)$',
        low
    )
    if m_open_and_search:
        app_part = m_open_and_search.group(1).strip()
        query_part = m_open_and_search.group(2).strip()

        if app_part in KNOWN_BROWSERS or any(b in app_part for b in ("brave", "chrome", "edge", "firefox", "navegador")):
            b_key = "brave" if "brave" in app_part else ("chrome" if "chrome" in app_part else ("firefox" if "firefox" in app_part else ("edge" if "edge" in app_part else "navegador")))
            return {
                "action": "browser_search",
                "browser": b_key,
                "query": query_part,
                "engine": "google",
            }
        if app_part in KNOWN_SEARCH_PLATFORMS:
            return {
                "action": "browser_search",
                "browser": "",
                "query": query_part,
                "engine": app_part,
            }

    # 3. Pattern: "[busca|buscar|search] <query> [en|dentro de|por] <browser/platform>"
    # e.g. "busca youtube en brave", "busca canciones en youtube", "busca python en github"
    m_search_in = re.match(
        r'^(?:por\s+favor\s+)?(?:busca|buscar|search|googlea|pon)\s+(.+?)\s+(?:en|dentro\s+de|por)\s+([a-zA-Z0-9_-]+(?:\s+browser)?)$',
        low
    )
    if m_search_in:
        query_part = m_search_in.group(1).strip()
        target_part = m_search_in.group(2).strip()

        if target_part in KNOWN_BROWSERS or any(b in target_part for b in ("brave", "chrome", "edge", "firefox", "navegador")):
            b_key = "brave" if "brave" in target_part else ("chrome" if "chrome" in target_part else ("firefox" if "firefox" in target_part else "navegador"))
            return {
                "action": "browser_search",
                "browser": b_key,
                "query": query_part,
                "engine": "google",
            }
        if target_part in KNOWN_SEARCH_PLATFORMS:
            return {
                "action": "browser_search",
                "browser": "",
                "query": query_part,
                "engine": target_part,
            }

    # 4. Pattern: "[entra a|abre|accede a] <known_web_service>"
    # e.g. "abre youtube", "entra a twitch", "accede a github", "abre reddit"
    m_direct_web = re.match(
        r'^(?:por\s+favor\s+)?(?:entra|ve|accede|abre|inicia)\s*(?:a|en)?\s*(?:la\s+web\s+de\s+|el\s+sitio\s+de\s+|la\s+p[aá]gina\s+de\s+|la\s+|el\s+)?([a-zA-Z0-9_-]+)$',
        low
    )
    if m_direct_web:
        site_cand = m_direct_web.group(1).strip()
        if site_cand in KNOWN_WEB_SERVICES:
            return {
                "action": "open_website",
                "url": KNOWN_WEB_SERVICES[site_cand],
                "service": site_cand,
            }

    return None


def parse_compound_chained_request(text: str) -> Optional[List[str]]:
    """
    Detects if the user submitted two distinct commands chained by ' y ' or ' and '.
    Example: 'abre discord y abre spotify' -> ['abre discord', 'abre spotify']
             'minimiza brave y abre la calculadora' -> ['minimiza brave', 'abre la calculadora']
    """
    raw = (text or "").strip()
    if not raw:
        return None

    low = raw.lower()

    # Avoid splitting if it's a search query containing 'y' like "recetas de pan y queso"
    if any(low.startswith(p) for p in ("busca ", "buscar ", "search ", "googlea ", "escribe ")):
        return None

    splitters = [" y ", " and ", " e "]
    for sp in splitters:
        if sp in low:
            parts = [p.strip(" .!?") for p in re.split(re.escape(sp), raw, flags=re.I) if p.strip()]
            # Verify that both parts look like action phrases (start with action verb)
            action_verbs = ("abre", "abrir", "cierra", "cerrar", "minimiza", "maximiza", "pon", "ajusta", "busca", "silencia", "sube", "baja")
            if len(parts) >= 2 and all(any(p.lower().startswith(v) for v in action_verbs) for p in parts):
                return parts

    return None
