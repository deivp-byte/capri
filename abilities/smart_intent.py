"""
Smart Semantic Intent Parser: Expands Spider-Man / Capri's comprehension
of natural language desktop, browser, and file system requests.
Handles compound instructions, preposition variations ("en brave busca youtube"),
browser targeting, web service routing, file/folder navigation, and proactive advice.
"""
from __future__ import annotations

import re
import unicodedata
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

    # 3B. Pattern: "[busca|buscar|search] [en|por] <platform/browser> <query>"
    # e.g. "busca en youtube lo fi chill", "busca en google recetas", "busca en brave noticias"
    m_search_prefix = re.match(
        r'^(?:por\s+favor\s+)?(?:busca|buscar|search|googlea|pon)\s+(?:en|por)\s+([a-zA-Z0-9_-]+)\s+(.+)$',
        low
    )
    if m_search_prefix:
        target_part = m_search_prefix.group(1).strip()
        query_part = m_search_prefix.group(2).strip()

        if target_part in KNOWN_SEARCH_PLATFORMS:
            return {
                "action": "browser_search",
                "browser": "",
                "query": query_part,
                "engine": target_part,
            }
        if target_part in KNOWN_BROWSERS or any(b in target_part for b in ("brave", "chrome", "edge", "firefox", "navegador")):
            b_key = "brave" if "brave" in target_part else ("chrome" if "chrome" in target_part else ("firefox" if "firefox" in target_part else "navegador"))
            return {
                "action": "browser_search",
                "browser": b_key,
                "query": query_part,
                "engine": "google",
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


def parse_file_or_folder_request(text: str) -> Optional[Dict[str, Any]]:
    """
    Parses natural language requests to navigate, open, search or inspect files and folders:
      - 'abre la carpeta descargas' -> open_folder('descargas')
      - 'abre descargas' -> open_folder('descargas')
      - 'abre el explorador de archivos' -> open_folder('')
      - 'abre la carpeta del proyecto' -> open_folder('capri')
      - 'qué hay en descargas' -> list_folder('descargas')
      - 'qué tengo en documentos' -> list_folder('documentos')
      - 'busca el archivo notas.txt' -> find_files('notas.txt')
      - 'dónde está config.json' -> find_files('config.json')
      - 'léeme el archivo config.json' -> read_file('config.json')
      - 'dame un consejo' / 'alguna recomendación' -> care_advice()
    """
    raw = (text or "").strip()
    if not raw:
        return None

    # Normalize accents for resilient matching
    nfkd = unicodedata.normalize("NFKD", raw)
    clean = "".join(ch for ch in nfkd if not unicodedata.combining(ch)).lower().strip(" .!?¿¡")

    # 1. Proactive Advice Request
    if re.match(r'^(?:por favor\s+)?(?:dame\s+(?:un\s+)?consejo|algun\s+consejo|alguna\s+recomendacion|como\s+me\s+ves|que\s+opinas|que\s+tal\s+voy|sentido\s+aracnido)$', clean):
        return {"action": "care_advice"}

    # 2. Open Explorer directly
    if re.match(r'^(?:por favor\s+)?(?:abre|abrir|open|entra a|accede a)\s+(?:el\s+explorador(?:\s+de\s+archivos)?|explorer)$', clean):
        return {"action": "open_folder", "target": ""}

    # 3. Open Specific Folder
    m_open = re.match(
        r'^(?:por favor\s+)?(?:abre|abrir|open|entra a|accede a)\s+(?:la\s+carpeta\s+(?:del?\s+)?|el\s+directorio\s+(?:del?\s+)?|el\s+folder\s+(?:del?\s+)?|mis\s+|el\s+|la\s+)?(descargas|downloads|documentos|documents|escritorio|desktop|imagenes|fotos|pictures|videos|musica|music|proyecto|capri|archivos|[a-z]:[\\/][a-z0-9_\\/.-]*)$',
        clean
    )
    if m_open:
        target_folder = m_open.group(1).strip()
        return {"action": "open_folder", "target": target_folder}

    # 4. List Folder Contents
    m_list = re.match(
        r'^(?:por favor\s+)?(?:(?:que\s+hay\s+en|que\s+tengo\s+en)\s+|lista\s+(?:los\s+archivos\s+(?:del?\s+)?|la\s+carpeta\s+(?:del?\s+)?|el\s+contenido\s+de\s+)|muestra\s+los\s+archivos\s+de\s+)(?:la\s+carpeta\s+(?:del?\s+)?|mis\s+|el\s+|la\s+)?([a-z0-9_:\\/.-]+)$',
        clean
    )
    if m_list:
        target_folder = m_list.group(1).strip()
        return {"action": "list_folder", "target": target_folder}

    # 5. Read / Explain File
    m_read = re.match(
        r'^(?:por favor\s+)?(?:lee|leeme|leer|que\s+dice|muestra\s+el\s+contenido\s+de)\s+(?:el\s+archivo\s+|el\s+fichero\s+)?([a-z0-9_:\\/.-]+\.[a-z0-9]+)$',
        clean
    )
    if m_read:
        target_file = m_read.group(1).strip()
        return {"action": "read_file", "target": target_file}

    # 6. Find / Locate File or Folder on PC
    m_find = re.match(
        r'^(?:por favor\s+)?(?:busca|buscar|encuentra|donde\s+esta|localiza|find)\s+(?:el\s+archivo\s+|la\s+carpeta\s+|el\s+fichero\s+)?([a-z0-9_.-]+(?:\.[a-z0-9]+)?)(?:\s+en\s+el\s+(?:pc|ordenador|disco|sistema)|\s+en\s+mis\s+archivos)?$',
        clean
    )
    if m_find:
        query_file = m_find.group(1).strip()
        if not any(clean.endswith(web) for web in ("en google", "en youtube", "en internet", "en la web", "en brave", "en chrome")):
            has_ext = "." in query_file and not query_file.endswith(".")
            has_explicit_term = any(w in clean for w in ("archivo", "fichero", "carpeta", "donde esta", "en el pc", "en el ordenador"))
            if has_ext or has_explicit_term:
                return {"action": "find_files", "query": query_file}

    return None
