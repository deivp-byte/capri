"""
Agent Interaction Engine: In-app automation, smart web navigation, and keyboard/mouse simulation.
Enables Spider-Man / Capri to interact inside applications, type text, trigger shortcuts,
and execute multi-engine browser searches with native zero-latency execution.
"""
from __future__ import annotations

import os
import sys
import time
import urllib.parse
import webbrowser
import subprocess
import shutil
from typing import Optional


# ==============================================================================
# SECTION 1: SMART BROWSER SEARCH & NAVIGATION
# ==============================================================================

SEARCH_ENGINES = {
    "google": "https://www.google.com/search?q={query}",
    "youtube": "https://www.youtube.com/results?search_query={query}",
    "github": "https://github.com/search?q={query}",
    "duckduckgo": "https://duckduckgo.com/?q={query}",
    "wikipedia": "https://es.wikipedia.org/wiki/Special:Search?search={query}",
    "reddit": "https://www.reddit.com/search/?q={query}",
    "bing": "https://www.bing.com/search?q={query}",
}


from abilities.app_finder import find_browser_executable, KNOWN_WEB_SERVICES
from abilities.window_manager import ensure_app_windowed


def browser_search(query: str, engine: str = "google", browser: str = "", **kwargs) -> str:
    """
    Performs a direct search or navigation within a web engine or specific browser.

    Args:
        query: Search keywords, question, or target website name (e.g. 'youtube', 'coches deportivos').
        engine: Target engine ('google', 'youtube', 'github', 'duckduckgo', 'wikipedia', 'reddit', 'bing').
        browser: Specific browser executable to use ('brave', 'chrome', 'edge', 'firefox').

    Returns:
        str: Status message with search URL and confirmation.
    """
    clean_query = (query or kwargs.get("q") or kwargs.get("text") or "").strip()
    if not clean_query:
        return "Status: Error - No se ha proporcionado ninguna consulta para buscar en el navegador."

    target_browser = (browser or kwargs.get("nav") or "").strip().lower()
    eng_key = (engine or "google").strip().lower()
    low_q = clean_query.lower()

    # If the query itself is a direct known service (e.g. "youtube", "twitch", "github", "reddit")
    if low_q in KNOWN_WEB_SERVICES:
        target_url = KNOWN_WEB_SERVICES[low_q]
        disp_engine = low_q.capitalize()
    else:
        # Detect if query specifies an engine
        if "youtube" in low_q or eng_key == "youtube":
            eng_key = "youtube"
            clean_query = clean_query.replace("en youtube", "").replace("de youtube", "").strip()
        elif "github" in low_q or eng_key == "github":
            eng_key = "github"
            clean_query = clean_query.replace("en github", "").strip()
        elif "wikipedia" in low_q or eng_key == "wikipedia":
            eng_key = "wikipedia"
            clean_query = clean_query.replace("en wikipedia", "").strip()
        elif "reddit" in low_q or eng_key == "reddit":
            eng_key = "reddit"
            clean_query = clean_query.replace("en reddit", "").strip()
        elif "google" in low_q or eng_key == "google":
            eng_key = "google"
            clean_query = clean_query.replace("en google", "").strip()

        template = SEARCH_ENGINES.get(eng_key, SEARCH_ENGINES["google"])
        encoded = urllib.parse.quote_plus(clean_query)
        target_url = template.format(query=encoded)
        disp_engine = eng_key.capitalize()

    # 1. Try launching with specific browser if requested (e.g. Brave, Chrome)
    if target_browser:
        browser_bin = find_browser_executable(target_browser)
        if browser_bin:
            try:
                # Launch in normal windowed mode with designated window dimensions
                cmd = [browser_bin, "--start-normal", "--window-size=1200,800", target_url]
                subprocess.Popen(cmd, start_new_session=True)
                ensure_app_windowed(target_browser)
                return f"Status: Búsqueda abierta con éxito en {target_browser.capitalize()} ({disp_engine}: '{clean_query}')."
            except Exception:
                pass

    # 2. Standard cross-platform default browser launch
    try:
        webbrowser.open(target_url, new=2)
        ensure_app_windowed(target_browser or "browser")
        return f"Status: Búsqueda iniciada con éxito en {disp_engine} para '{clean_query}'. (URL: {target_url})"
    except Exception as err:
        # Fallback to os.startfile on Windows
        if sys.platform == "win32" and hasattr(os, "startfile"):
            try:
                os.startfile(target_url)
                ensure_app_windowed(target_browser or "browser")
                return f"Status: Búsqueda abierta en Windows shell en {disp_engine} para '{clean_query}'."
            except Exception:
                pass
        return f"Status: Error al abrir la búsqueda en el navegador: {err}"


# ==============================================================================
# SECTION 2: IN-APP KEYBOARD SIMULATION & TEXT INPUT
# ==============================================================================

def _set_clipboard_text_win32(text: str) -> bool:
    """Sets text in Windows global clipboard with Unicode CF_UNICODETEXT support."""
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        CF_UNICODETEXT = 13
        GMEM_MOVEABLE = 0x0002

        if not user32.OpenClipboard(0):
            return False

        user32.EmptyClipboard()

        data_bytes = (text + "\0").encode("utf-16le")
        h_mem = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data_bytes))
        if not h_mem:
            user32.CloseClipboard()
            return False

        ptr = kernel32.GlobalLock(h_mem)
        ctypes.memmove(ptr, data_bytes, len(data_bytes))
        kernel32.GlobalUnlock(h_mem)

        user32.SetClipboardData(CF_UNICODETEXT, h_mem)
        user32.CloseClipboard()
        return True
    except Exception as err:
        print(f"[clipboard] Error: {err}")
        return False


def type_in_app(text: str, press_enter: bool = True, delay: float = 0.05, **kwargs) -> str:
    """
    Types text into the currently active desktop application (browser, editor, terminal, Discord, etc.)
    using high-speed clipboard paste (Ctrl+V) or virtual keystrokes, optionally followed by Enter.

    Args:
        text: Text string to type into the focused application.
        press_enter: If True, simulates pressing Enter after typing.
        delay: Milliseconds buffer before typing to let window settle.

    Returns:
        str: Status report of the typing action.
    """
    clean_text = (text or kwargs.get("content") or kwargs.get("msg") or "").strip()
    if not clean_text:
        return "Status: Error - No se ha proporcionado texto para escribir."

    if sys.platform == "win32":
        try:
            import ctypes
            user32 = ctypes.windll.user32
            VK_CONTROL = 0x11
            VK_V = 0x56
            VK_RETURN = 0x0D

            # Small delay to ensure active focus
            time.sleep(max(0.02, delay))

            # Set clipboard and trigger Ctrl+V paste
            if _set_clipboard_text_win32(clean_text):
                # Press Ctrl+V
                user32.keybd_event(VK_CONTROL, 0, 0, 0)
                user32.keybd_event(VK_V, 0, 0, 0)
                time.sleep(0.03)
                user32.keybd_event(VK_V, 0, 2, 0)
                user32.keybd_event(VK_CONTROL, 0, 2, 0)

                if press_enter:
                    time.sleep(0.04)
                    user32.keybd_event(VK_RETURN, 0, 0, 0)
                    time.sleep(0.02)
                    user32.keybd_event(VK_RETURN, 0, 2, 0)

                return f"Status: Texto introducido correctamente en la aplicación activa ({len(clean_text)} caracteres)."

            # Fallback unicode SendInput
            for char in clean_text:
                # KEYEVENTF_UNICODE = 0x0004
                code = ord(char)
                # Send key down & up
                user32.keybd_event(0, code, 4, 0)
                user32.keybd_event(0, code, 6, 0)
                time.sleep(0.005)

            if press_enter:
                user32.keybd_event(VK_RETURN, 0, 0, 0)
                time.sleep(0.02)
                user32.keybd_event(VK_RETURN, 0, 2, 0)

            return f"Status: Texto escrito mediante teclado virtual ({len(clean_text)} caracteres)."
        except Exception as err:
            return f"Status: Error al escribir en la aplicación en Windows: {err}"

    # Linux fallback via xdotool if present
    if shutil.which("xdotool"):
        try:
            cmd = ["xdotool", "type", "--delay", "10", clean_text]
            subprocess.run(cmd, check=True)
            if press_enter:
                subprocess.run(["xdotool", "key", "Return"], check=True)
            return f"Status: Texto escrito en Linux vía xdotool."
        except Exception as err:
            return f"Status: Error al escribir con xdotool en Linux: {err}"

    return f"Status: No se dispone de controlador de teclado nativo en esta plataforma."


def press_hotkey(keys: str, **kwargs) -> str:
    """
    Simulates keyboard shortcuts in the active application.

    Supported shortcuts:
        'ctrl+t': New tab (browser)
        'ctrl+w': Close tab
        'ctrl+l': Focus address bar
        'ctrl+f': Find in page
        'enter': Press Enter key
        'f5': Refresh page
        'alt+f4': Close window
        'esc': Escape
    """
    clean = (keys or kwargs.get("shortcut") or kwargs.get("key") or "").strip().lower()
    if not clean:
        return "Status: Error - No se ha indicado el atajo de teclado."

    if sys.platform == "win32":
        try:
            import ctypes
            user32 = ctypes.windll.user32

            VK_CONTROL = 0x11
            VK_SHIFT = 0x10
            VK_ALT = 0x12
            VK_RETURN = 0x0D
            VK_ESCAPE = 0x1B
            VK_F5 = 0x74
            VK_F4 = 0x73

            key_map = {
                "t": 0x54,
                "w": 0x57,
                "l": 0x4C,
                "f": 0x46,
                "c": 0x43,
                "v": 0x56,
                "a": 0x41,
                "z": 0x5A,
                "r": 0x52,
            }

            if clean in ("enter", "intro"):
                user32.keybd_event(VK_RETURN, 0, 0, 0)
                time.sleep(0.02)
                user32.keybd_event(VK_RETURN, 0, 2, 0)
                return "Status: Tecla Enter pulsada."

            if clean in ("esc", "escape"):
                user32.keybd_event(VK_ESCAPE, 0, 0, 0)
                time.sleep(0.02)
                user32.keybd_event(VK_ESCAPE, 0, 2, 0)
                return "Status: Tecla Esc pulsada."

            if clean == "f5":
                user32.keybd_event(VK_F5, 0, 0, 0)
                time.sleep(0.02)
                user32.keybd_event(VK_F5, 0, 2, 0)
                return "Status: Tecla F5 (actualizar) pulsada."

            if clean.startswith("ctrl+"):
                char = clean.split("+")[1]
                vk_char = key_map.get(char)
                if vk_char:
                    user32.keybd_event(VK_CONTROL, 0, 0, 0)
                    user32.keybd_event(vk_char, 0, 0, 0)
                    time.sleep(0.02)
                    user32.keybd_event(vk_char, 0, 2, 0)
                    user32.keybd_event(VK_CONTROL, 0, 2, 0)
                    return f"Status: Atajo {clean.upper()} ejecutado con éxito."

            if clean == "alt+f4":
                user32.keybd_event(VK_ALT, 0, 0, 0)
                user32.keybd_event(VK_F4, 0, 0, 0)
                time.sleep(0.02)
                user32.keybd_event(VK_F4, 0, 2, 0)
                user32.keybd_event(VK_ALT, 0, 2, 0)
                return "Status: Atajo Alt+F4 ejecutado."

            return f"Status: Atajo '{clean}' no soportado directamente."
        except Exception as err:
            return f"Status: Error al ejecutar atajo: {err}"

    if shutil.which("xdotool"):
        try:
            subprocess.run(["xdotool", "key", clean], check=True)
            return f"Status: Atajo {clean} enviado con xdotool."
        except Exception as err:
            return f"Status: Error en atajo Linux: {err}"

    return f"Status: Simulación de atajos no soportada."
