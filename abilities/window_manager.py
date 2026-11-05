"""
abilities/window_manager.py - High-Performance X11 / EWMH & Windows Window Management

Provides native X11 window geometry discovery, window manipulation, and state
queries using python-xlib (Xlib.display). Designed for zero-overhead, non-OCR,
real-time desktop pet interactions (such as swinging, web-pulling, dragging,
minimizing, maximizing, restoring, and closing windows).
Includes cross-platform fallbacks for Windows desktop environments.
"""

from __future__ import annotations

import os
import re
import sys
from typing import Optional, Tuple

# Try loading Xlib for Linux X11
_XLIB_AVAILABLE = False
_DISPLAY = None
_ROOT = None

try:
    import Xlib
    import Xlib.display
    import Xlib.X
    import Xlib.protocol.event

    # Connect to local X11 display server
    _DISPLAY = Xlib.display.Display()
    _ROOT = _DISPLAY.screen().root
    _XLIB_AVAILABLE = True
except Exception:
    _XLIB_AVAILABLE = False
    _DISPLAY = None
    _ROOT = None


# Cache common EWMH / ICCCM atoms if Xlib is active
_ATOMS: dict[str, int] = {}

def _get_atom(name: str) -> int:
    """Retrieves and caches X11 intern atom ID."""
    global _ATOMS, _DISPLAY
    if not _DISPLAY:
        return 0
    if name not in _ATOMS:
        try:
            _ATOMS[name] = _DISPLAY.intern_atom(name)
        except Exception:
            return 0
    return _ATOMS[name]


def _get_x11_window_name(win) -> str:
    """Extracts UTF-8 or ASCII window title or WM_CLASS from an X11 window."""
    if not win:
        return ""
    try:
        # 1. Try _NET_WM_NAME (UTF-8)
        atom_net_wm_name = _get_atom("_NET_WM_NAME")
        prop = win.get_full_property(atom_net_wm_name, 0)
        if prop and prop.value:
            val = prop.value
            return val.decode("utf-8", errors="replace") if isinstance(val, bytes) else str(val)

        # 2. Try WM_NAME (ICCCM)
        name = win.get_wm_name()
        if name:
            return name

        # 3. Try WM_CLASS
        wm_class = win.get_wm_class()
        if wm_class:
            return " ".join(wm_class)
    except Exception:
        pass
    return ""


def _is_maximized_x11(wid: int) -> bool:
    """Checks whether an X11 window has horizontal or vertical maximized EWMH states."""
    if not _DISPLAY:
        return False
    try:
        win = _DISPLAY.create_resource_object("window", wid)
        atom_net_wm_state = _get_atom("_NET_WM_STATE")
        atom_max_horz = _get_atom("_NET_WM_STATE_MAXIMIZED_HORZ")
        atom_max_vert = _get_atom("_NET_WM_STATE_MAXIMIZED_VERT")

        prop = win.get_full_property(atom_net_wm_state, Xlib.X.AnyPropertyType)
        if prop and prop.value:
            states = set(prop.value)
            return atom_max_horz in states or atom_max_vert in states
    except Exception:
        pass
    return False


def _normalize_app_query(app_name: str) -> list[str]:
    """Generates search variants for common application names including typos."""
    clean = (app_name or "").strip().lower()
    for prefix in ("app de ", "la app de ", "el programa ", "la aplicacion de ", "la aplicación de ", "la ventana de ", "ventana de ", "la pantalla de ", "pantalla de "):
        if clean.startswith(prefix):
            clean = clean[len(prefix):].strip()
            break

    for suffix in (" del ordenador", " de mi pc", " de windows", " de linux"):
        if clean.endswith(suffix):
            clean = clean[:-len(suffix)].strip()
            break

    variants = [clean]
    if any(k in clean for k in ("visual", "studo", "studio", "vscode", "code")):
        variants.extend(["visual studio code", "visual studio", "code", "vscode", "studo"])
    elif "brave" in clean:
        variants.extend(["brave", "brave-browser"])
    elif "chrome" in clean:
        variants.extend(["chrome", "google-chrome"])
    elif "firefox" in clean:
        variants.extend(["firefox", "mozilla"])
    elif any(k in clean for k in ("terminal", "consola", "powershell", "cmd", "bash")):
        variants.extend(["terminal", "powershell", "cmd", "bash", "konsole", "wt"])
    elif "calc" in clean or "calculadora" in clean:
        variants.extend(["calc", "calculadora", "calculator"])
    elif "bloc" in clean or "notepad" in clean:
        variants.extend(["notepad", "bloc de notas", "editor"])
    elif "spotify" in clean:
        variants.extend(["spotify"])
    return list(dict.fromkeys(v for v in variants if v))


def _get_active_or_target_x11(app_name: str = "") -> Optional[Tuple[int, Tuple[int, int, int, int]]]:
    """
    X11 EWMH implementation:
    Finds active window or window matching app_name, returning (wid, (x, y, w, h)).
    """
    if not _DISPLAY or not _ROOT:
        return None

    try:
        target_wid: Optional[int] = None
        atom_net_client_list = _get_atom("_NET_CLIENT_LIST")
        atom_net_active = _get_atom("_NET_ACTIVE_WINDOW")

        variants = _normalize_app_query(app_name) if app_name else []

        # If app_name is specified, search across managed windows in _NET_CLIENT_LIST
        if variants:
            client_list_prop = _ROOT.get_full_property(atom_net_client_list, Xlib.X.AnyPropertyType)
            if client_list_prop and client_list_prop.value:
                for candidate_wid in reversed(client_list_prop.value):
                    try:
                        c_win = _DISPLAY.create_resource_object("window", candidate_wid)
                        title = _get_x11_window_name(c_win).lower()
                        if any(v in title for v in variants):
                            target_wid = candidate_wid
                            break
                    except Exception:
                        continue

        # If no specific app requested or not found, query _NET_ACTIVE_WINDOW
        if not target_wid:
            active_prop = _ROOT.get_full_property(atom_net_active, Xlib.X.AnyPropertyType)
            if active_prop and active_prop.value:
                target_wid = active_prop.value[0]

        if not target_wid:
            return None

        win = _DISPLAY.create_resource_object("window", target_wid)
        geom = win.get_geometry()
        coords = win.translate_coords(_ROOT, 0, 0)
        abs_x = coords.x
        abs_y = coords.y
        w = geom.width
        h = geom.height

        return target_wid, (abs_x, abs_y, w, h)

    except Exception as err:
        print(f"[window_manager] X11 discovery warning: {err}")
        return None


def _move_window_x11(wid: int, new_x: int, new_y: int) -> bool:
    """Moves an X11 window using win.configure(x=..., y=...) and d.sync()."""
    if not _DISPLAY:
        return False
    try:
        win = _DISPLAY.create_resource_object("window", wid)
        win.configure(x=int(new_x), y=int(new_y))
        _DISPLAY.sync()
        return True
    except Exception as err:
        print(f"[window_manager] X11 move error: {err}")
        return False


def _minimize_window_x11(wid: int) -> bool:
    """Minimizes an X11 window using win.iconify() and sync()."""
    if not _DISPLAY or not _ROOT:
        return False
    try:
        win = _DISPLAY.create_resource_object("window", wid)
        win.iconify()
        _DISPLAY.sync()
        return True
    except Exception as err:
        print(f"[window_manager] X11 minimize error: {err}")
        return False


def _maximize_window_x11(wid: int) -> bool:
    """Maximizes an X11 window via EWMH ClientMessage _NET_WM_STATE_ADD."""
    if not _DISPLAY or not _ROOT:
        return False
    try:
        atom_state = _get_atom("_NET_WM_STATE")
        atom_max_h = _get_atom("_NET_WM_STATE_MAXIMIZED_HORZ")
        atom_max_v = _get_atom("_NET_WM_STATE_MAXIMIZED_VERT")
        ev = Xlib.protocol.event.ClientMessage(
            window=wid,
            client_type=atom_state,
            data=(32, [1, atom_max_h, atom_max_v, 1, 0])
        )
        _ROOT.send_event(ev, event_mask=Xlib.X.SubstructureRedirectMask | Xlib.X.SubstructureNotifyMask)
        _DISPLAY.sync()
        return True
    except Exception as err:
        print(f"[window_manager] X11 maximize error: {err}")
        return False


def _restore_window_x11(wid: int) -> bool:
    """Restores (unmaximizes) an X11 window via EWMH ClientMessage _NET_WM_STATE_REMOVE."""
    if not _DISPLAY or not _ROOT:
        return False
    try:
        atom_state = _get_atom("_NET_WM_STATE")
        atom_max_h = _get_atom("_NET_WM_STATE_MAXIMIZED_HORZ")
        atom_max_v = _get_atom("_NET_WM_STATE_MAXIMIZED_VERT")
        ev = Xlib.protocol.event.ClientMessage(
            window=wid,
            client_type=atom_state,
            data=(32, [0, atom_max_h, atom_max_v, 1, 0])
        )
        _ROOT.send_event(ev, event_mask=Xlib.X.SubstructureRedirectMask | Xlib.X.SubstructureNotifyMask)
        _DISPLAY.sync()
        return True
    except Exception as err:
        print(f"[window_manager] X11 restore error: {err}")
        return False


def _close_window_x11(wid: int) -> bool:
    """Closes an X11 window via EWMH _NET_CLOSE_WINDOW."""
    if not _DISPLAY or not _ROOT:
        return False
    try:
        atom_close = _get_atom("_NET_CLOSE_WINDOW")
        ev = Xlib.protocol.event.ClientMessage(
            window=wid,
            client_type=atom_close,
            data=(32, [0, 0, 0, 0, 0])
        )
        _ROOT.send_event(ev, event_mask=Xlib.X.SubstructureRedirectMask | Xlib.X.SubstructureNotifyMask)
        _DISPLAY.sync()
        return True
    except Exception as err:
        print(f"[window_manager] X11 close error: {err}")
        return False


# ==============================================================================
# WINDOWS WIN32 FALLBACK IMPLEMENTATION
# ==============================================================================

def _get_input_desktop_win32():
    """Ensures thread attachment to active interactive desktop session on Windows."""
    try:
        import ctypes
        user32 = ctypes.windll.user32
        input_desk = user32.OpenInputDesktop(0, False, 0x01FF)
        if input_desk:
            user32.SetThreadDesktop(input_desk)
        return input_desk
    except Exception:
        return None


def _get_window_bounds_win32(hwnd: int) -> Optional[Tuple[int, int, int, int]]:
    """Gets accurate window bounds using DwmGetWindowAttribute (excluding invisible margins)."""
    try:
        import ctypes
        from ctypes import wintypes
        dwmapi = ctypes.windll.dwmapi
        user32 = ctypes.windll.user32

        rect = wintypes.RECT()
        DWMWA_EXTENDED_FRAME_BOUNDS = 9
        res = dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_EXTENDED_FRAME_BOUNDS, ctypes.byref(rect), ctypes.sizeof(rect))
        if res == 0:
            w = rect.right - rect.left
            h = rect.bottom - rect.top
            return (rect.left, rect.top, w, h)

        # Fallback to standard GetWindowRect
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        w = max(100, rect.right - rect.left)
        h = max(100, rect.bottom - rect.top)
        return (rect.left, rect.top, w, h)
    except Exception:
        return None


def _is_window_valid_app_win32(hwnd: int, user32, dwmapi, exclude_hwnds: set[int] = None) -> bool:
    """Verifies that an HWND represents an active, visible, non-cloaked desktop application window."""
    if not hwnd or (exclude_hwnds and hwnd in exclude_hwnds):
        return False
    if not user32.IsWindow(hwnd) or not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
        return False

    # Check for cloaked window (DWMWA_CLOAKED = 14)
    import ctypes
    cloaked = ctypes.c_int(0)
    dwmapi.DwmGetWindowAttribute(hwnd, 14, ctypes.byref(cloaked), ctypes.sizeof(cloaked))
    if cloaked.value != 0:
        return False

    # Check class name
    class_buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, class_buf, 256)
    cls_name = class_buf.value
    shell_classes = {
        "Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd",
        "Windows.UI.Core.CoreWindow", "XamlExplorerHostIslandWindow",
        "#32768", "tooltips_class32"
    }
    if cls_name in shell_classes:
        return False

    return True


def _get_active_or_target_win32(app_name: str = "", exclude_hwnds: set[int] = None) -> Optional[Tuple[int, Tuple[int, int, int, int]]]:
    """Windows ctypes implementation for window identification and accurate geometry."""
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        dwmapi = ctypes.windll.dwmapi
        _get_input_desktop_win32()

        variants = _normalize_app_query(app_name) if app_name else []
        target_hwnd = 0

        # If specific app name is requested, search enumerated windows
        if variants:
            found_windows: list[int] = []

            def _enum_callback(hwnd, _):
                if _is_window_valid_app_win32(hwnd, user32, dwmapi, exclude_hwnds):
                    length = user32.GetWindowTextLengthW(hwnd)
                    if length > 0:
                        buff = ctypes.create_unicode_buffer(length + 1)
                        user32.GetWindowTextW(hwnd, buff, length + 1)
                        title_lower = buff.value.lower()
                        if any(v in title_lower for v in variants):
                            found_windows.append(hwnd)
                return True

            WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
            user32.EnumWindows(WNDENUMPROC(_enum_callback), 0)
            if found_windows:
                target_hwnd = found_windows[0]

        # If no specific app requested, first check foreground window
        if not target_hwnd:
            fg = user32.GetForegroundWindow()
            if _is_window_valid_app_win32(fg, user32, dwmapi, exclude_hwnds):
                target_hwnd = fg

        # If foreground is invalid, our own window, or shell, pick the topmost valid app window
        if not target_hwnd:
            topmost: list[int] = []

            def _top_cb(hwnd, _):
                if _is_window_valid_app_win32(hwnd, user32, dwmapi, exclude_hwnds):
                    length = user32.GetWindowTextLengthW(hwnd)
                    if length > 0:
                        bounds = _get_window_bounds_win32(hwnd)
                        if bounds and bounds[2] >= 250 and bounds[3] >= 200:
                            topmost.append(hwnd)
                            return False  # stop enumeration on first match
                return True

            WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
            user32.EnumWindows(WNDENUMPROC(_top_cb), 0)
            if topmost:
                target_hwnd = topmost[0]

        if not target_hwnd:
            return None

        bounds = _get_window_bounds_win32(target_hwnd)
        if bounds:
            return int(target_hwnd), bounds
        return None
    except Exception:
        return None


def _is_maximized_win32(wid: int) -> bool:
    """Windows check if window is maximized."""
    try:
        import ctypes
        return ctypes.windll.user32.IsZoomed(wid) != 0
    except Exception:
        return False


def _move_window_win32(wid: int, new_x: int, new_y: int) -> bool:
    """Windows MoveWindow / SetWindowPos."""
    try:
        import ctypes
        SWP_NOSIZE = 0x0001
        SWP_NOZORDER = 0x0004
        ctypes.windll.user32.SetWindowPos(wid, 0, int(new_x), int(new_y), 0, 0, SWP_NOSIZE | SWP_NOZORDER)
        return True
    except Exception:
        return False


def _minimize_window_win32(wid: int) -> bool:
    """Windows ShowWindow(..., SW_MINIMIZE)."""
    try:
        import ctypes
        SW_MINIMIZE = 6
        ctypes.windll.user32.ShowWindow(wid, SW_MINIMIZE)
        return True
    except Exception:
        return False


def _maximize_window_win32(wid: int) -> bool:
    """Windows ShowWindow(..., SW_MAXIMIZE)."""
    try:
        import ctypes
        SW_MAXIMIZE = 3
        ctypes.windll.user32.ShowWindow(wid, SW_MAXIMIZE)
        return True
    except Exception:
        return False


def _restore_window_win32(wid: int) -> bool:
    """Windows ShowWindow(..., SW_RESTORE)."""
    try:
        import ctypes
        SW_RESTORE = 9
        ctypes.windll.user32.ShowWindow(wid, SW_RESTORE)
        return True
    except Exception:
        return False


def _close_window_win32(wid: int) -> bool:
    """Windows PostMessage(..., WM_CLOSE)."""
    try:
        import ctypes
        WM_CLOSE = 0x0010
        ctypes.windll.user32.PostMessageW(wid, WM_CLOSE, 0, 0)
        return True
    except Exception:
        return False


# ==============================================================================
# SIMULATION / MOCK STATE FOR VIRTUAL / TEST ENVIRONMENTS
# ==============================================================================

_SIMULATED_WINDOWS: dict[int, dict] = {
    1001: {
        "title": "Brave - Web Browser",
        "rect": [200, 180, 800, 520],
        "maximized": False,
        "minimized": False,
    },
    1002: {
        "title": "Visual Studio Code - capri",
        "rect": [400, 220, 960, 600],
        "maximized": False,
        "minimized": False,
    },
    1003: {
        "title": "Terminal - spider@queens:~",
        "rect": [150, 100, 700, 450],
        "maximized": False,
        "minimized": False,
    },
}
_SIMULATED_ACTIVE_WID = 1001


# ==============================================================================
# PUBLIC API (CALLED BY BRAIN.PY AND BODY.PY)
# ==============================================================================

def is_maximized(wid: int) -> bool:
    """
    Checks if the specified window is maximized.
    On Linux X11: inspects _NET_WM_STATE for horizontal/vertical maximized atoms.
    On Windows: uses IsZoomed().
    """
    if wid in _SIMULATED_WINDOWS:
        return bool(_SIMULATED_WINDOWS[wid].get("maximized", False))

    if _XLIB_AVAILABLE and _DISPLAY:
        return _is_maximized_x11(wid)
    elif sys.platform == "win32":
        return _is_maximized_win32(wid)
    return False


def get_active_or_target_window(app_name: str = "") -> Optional[Tuple[int, Tuple[int, int, int, int]]]:
    """
    Retrieves the Window ID (wid) and bounding box (x, y, width, height) of the
    active window or target app requested.

    Returns:
        tuple[int, tuple[int, int, int, int]] | None:
        (wid, (x, y, width, height)) or None if no suitable window is found.
    """
    # 1. Native Linux X11 via python-xlib
    if _XLIB_AVAILABLE and _DISPLAY:
        res = _get_active_or_target_x11(app_name)
        if res:
            return res

    # 2. Windows Win32 native fallback
    if sys.platform == "win32":
        res = _get_active_or_target_win32(app_name)
        if res:
            return res

    # 3. Simulated environment fallback for headless tests or missing desktop sessions
    variants = _normalize_app_query(app_name) if app_name else []
    for wid, data in _SIMULATED_WINDOWS.items():
        if variants and any(v in data["title"].lower() for v in variants):
            r = data["rect"]
            return wid, (r[0], r[1], r[2], r[3])

    # Default to simulated active window
    sim_wid = _SIMULATED_ACTIVE_WID
    r = _SIMULATED_WINDOWS[sim_wid]["rect"]
    return sim_wid, (r[0], r[1], r[2], r[3])


def move_window(wid: int, new_x: int, new_y: int) -> bool:
    """Updates the position of the window on screen."""
    if wid in _SIMULATED_WINDOWS:
        _SIMULATED_WINDOWS[wid]["rect"][0] = int(new_x)
        _SIMULATED_WINDOWS[wid]["rect"][1] = int(new_y)
        return True

    if _XLIB_AVAILABLE and _DISPLAY:
        return _move_window_x11(wid, new_x, new_y)
    elif sys.platform == "win32":
        return _move_window_win32(wid, new_x, new_y)
    return False


def minimize_window(wid: int) -> bool:
    """Minimizes the window to the taskbar/dock."""
    if wid in _SIMULATED_WINDOWS:
        _SIMULATED_WINDOWS[wid]["minimized"] = True
        return True

    if _XLIB_AVAILABLE and _DISPLAY:
        return _minimize_window_x11(wid)
    elif sys.platform == "win32":
        return _minimize_window_win32(wid)
    return False


def maximize_window(wid: int) -> bool:
    """Maximizes the window to full screen."""
    if wid in _SIMULATED_WINDOWS:
        _SIMULATED_WINDOWS[wid]["maximized"] = True
        return True

    if _XLIB_AVAILABLE and _DISPLAY:
        return _maximize_window_x11(wid)
    elif sys.platform == "win32":
        return _maximize_window_win32(wid)
    return False


def restore_window(wid: int) -> bool:
    """Restores (un-maximizes) the window."""
    if wid in _SIMULATED_WINDOWS:
        _SIMULATED_WINDOWS[wid]["maximized"] = False
        _SIMULATED_WINDOWS[wid]["minimized"] = False
        return True

    if _XLIB_AVAILABLE and _DISPLAY:
        return _restore_window_x11(wid)
    elif sys.platform == "win32":
        return _restore_window_win32(wid)
    return False


def ensure_windowed_mode(wid: int, default_w: int = 1180, default_h: int = 760) -> bool:
    """
    Ensures a target window is in floating windowed mode (not maximized or full-screen).
    If the window is zoomed / maximized, restores it (SW_RESTORE) and resizes if needed.
    """
    if wid in _SIMULATED_WINDOWS:
        _SIMULATED_WINDOWS[wid]["maximized"] = False
        _SIMULATED_WINDOWS[wid]["minimized"] = False
        return True

    if sys.platform == "win32":
        try:
            import time
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32

            # 1. Check if window is maximized (zoomed)
            if user32.IsZoomed(wid):
                SW_RESTORE = 9
                user32.ShowWindow(wid, SW_RESTORE)
                time.sleep(0.08)

            # 2. Inspect rectangle bounds; if window is filling the entire monitor, resize to comfortable bounds
            rect = wintypes.RECT()
            if user32.GetWindowRect(wid, ctypes.byref(rect)):
                w = rect.right - rect.left
                h = rect.bottom - rect.top
                sw = user32.GetSystemMetrics(0)
                sh = user32.GetSystemMetrics(1)
                if w >= sw - 20 or h >= sh - 50:
                    new_w = min(default_w, sw - 120)
                    new_h = min(default_h, sh - 120)
                    new_x = max(60, (sw - new_w) // 2)
                    new_y = max(40, (sh - new_h) // 2)
                    user32.MoveWindow(wid, new_x, new_y, new_w, new_h, True)
            return True
        except Exception:
            return False
    elif _XLIB_AVAILABLE and _DISPLAY:
        return _restore_window_x11(wid)
    return False


def ensure_app_windowed(app_name: str, attempts: int = 8, interval: float = 0.25) -> None:
    """
    Asynchronously monitors for newly opened application windows and enforces
    windowed (non-maximized) display mode.
    """
    import threading
    import time

    def _worker():
        for _ in range(attempts):
            time.sleep(interval)
            target = get_active_or_target_window(app_name)
            if target:
                wid, _ = target
                ensure_windowed_mode(wid)
                break

    threading.Thread(target=_worker, daemon=True).start()


def get_window_title(wid: int) -> str:
    """Returns the title of the window identified by wid."""
    if wid in _SIMULATED_WINDOWS:
        return _SIMULATED_WINDOWS[wid].get("title", "")

    if sys.platform == "win32":
        try:
            import ctypes
            user32 = ctypes.windll.user32
            length = user32.GetWindowTextLengthW(wid)
            if length > 0:
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(wid, buf, length + 1)
                return buf.value
        except Exception:
            pass
    elif _XLIB_AVAILABLE and _DISPLAY:
        try:
            w = _DISPLAY.create_resource_object("window", wid)
            return _get_x11_window_name(w)
        except Exception:
            pass
    return ""


def get_topmost_app_window(exclude_hwnds: set[int] = None) -> Optional[Tuple[int, str, Tuple[int, int, int, int]]]:
    """
    Finds the topmost visible application window on the desktop.

    Returns:
        (wid, title, (x, y, width, height)) or None
    """
    if sys.platform == "win32":
        res = _get_active_or_target_win32("", exclude_hwnds=exclude_hwnds)
        if res:
            wid, bounds = res
            title = get_window_title(wid)
            return wid, title, bounds
    elif _XLIB_AVAILABLE and _DISPLAY:
        res = _get_active_or_target_x11("")
        if res:
            wid, bounds = res
            title = get_window_title(wid)
            return wid, title, bounds

    sim_wid = _SIMULATED_ACTIVE_WID
    data = _SIMULATED_WINDOWS[sim_wid]
    r = data["rect"]
    return sim_wid, data["title"], (r[0], r[1], r[2], r[3])


def close_window(wid: int) -> bool:
    """Closes the window."""
    if wid in _SIMULATED_WINDOWS:
        _SIMULATED_WINDOWS.pop(wid, None)
        return True

    if _XLIB_AVAILABLE and _DISPLAY:
        return _close_window_x11(wid)
    elif sys.platform == "win32":
        return _close_window_win32(wid)
    return False
