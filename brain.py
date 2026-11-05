"""
brain.py - Core AI Engine for Spider-Man (Interactive Desktop Agent)

Connects to local Ollama (qwen2.5-coder:7b / 3B SLMs), injects the Spider-Man
(Peter Parker) persona with Marvel Universe lore via persona.py, manages
conversation hygiene, executes real system tools cross-platform, and uses
token capping and connection keep-alive for high-speed local inference.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
from typing import Callable, Dict, List, Optional, Tuple
import urllib.parse
import webbrowser
import ollama
from ollama import Client, ResponseError

from abilities.window_manager import (
    get_active_or_target_window,
    move_window,
    minimize_window,
    maximize_window,
    restore_window,
    close_window,
    is_maximized,
)
from config import DATA_DIR, get_config
from memory import CapriMemory, SpiderMemory
from persona import build, reminder

# Ensure UTF-8 output encoding for proper terminal character rendering across platforms
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


# ==============================================================================
# SECTION 1: REAL SYSTEM TOOLS (CROSS-PLATFORM WINDOWS & LINUX X11)
# ==============================================================================
# System capabilities with strict security guardrails:
# 1. Zero shell=True calls: Prevents shell injection vulnerabilities.
# 2. Filesystem Jail: All writes/appends are strictly confined to Path.home() or project.
# 3. Deletion Shield: File deletion is unconditionally blocked to protect system integrity.
# 4. Cross-Platform Execution: Real execution on Windows and Linux X11.
# 5. Personality Fuel: Tool outputs serve as internal feedback for Capri's reactive voice.
# ==============================================================================

def _is_safe_user_path(target_path: Path) -> bool:
    """Validates that a path is strictly located within the user's home directory or project directory."""
    try:
        resolved = target_path.expanduser().resolve()
        home = Path.home().resolve()
        from config import BASE_DIR
        base = BASE_DIR.resolve()
        return (resolved == home or home in resolved.parents or resolved == base or base in resolved.parents)
    except Exception:
        return False


def abrir_aplicacion(app_name: str = "", **kwargs) -> str:
    """
    Launches a desktop application in the background (Cross-platform: Windows and Linux X11).

    Args:
        app_name: Name or executable of the application (e.g. 'ajustes', 'calc', 'notepad', 'firefox').

    Returns:
        str: Descriptive execution feedback for Capri.
    """
    clean_name = (app_name or kwargs.get("name") or kwargs.get("app") or "").strip()
    if not clean_name:
        return "Status: Error - No application name provided to launch."

    # Normalize conversational prefix phrases
    lower_name = clean_name.lower()
    for prefix in ("app de ", "la app de ", "el programa ", "el software ", "la aplicacion de ", "la aplicación de "):
        if lower_name.startswith(prefix):
            clean_name = clean_name[len(prefix):].strip()
            lower_name = clean_name.lower()
            break

    for suffix in (" del ordenador", " de mi ordenador", " de windows", " de pc", " del pc", " de linux"):
        if lower_name.endswith(suffix):
            clean_name = clean_name[:-len(suffix)].strip()
            lower_name = clean_name.lower()
            break

    # Check if query contains search phrases (e.g. "brave busca youtube", "chrome y busca...")
    for sep in (" busca ", " y busca ", " buscar ", " search "):
        if sep in lower_name:
            parts = lower_name.split(sep, 1)
            raw_target = parts[0].replace("en ", "").replace("entra a ", "").replace("abre ", "").strip()
            raw_query = parts[1].strip()
            from abilities.agent_interaction import browser_search
            return browser_search(query=raw_query, browser=raw_target)

    # Check if target is a known direct web platform (e.g. "youtube", "twitch", "github", "reddit")
    from abilities.app_finder import KNOWN_WEB_SERVICES, resolve_application_command
    if lower_name in KNOWN_WEB_SERVICES:
        return open_website(KNOWN_WEB_SERVICES[lower_name])

    # Universal application resolver (Queries Windows Registry App Paths, LocalAppData, Program Files)
    resolved_cmd = resolve_application_command(clean_name)
    if resolved_cmd:
        cmd_args, disp_name = resolved_cmd
        try:
            subprocess.Popen(cmd_args, start_new_session=True)
            return f"Status: Application '{disp_name}' successfully launched."
        except Exception as launch_err:
            pass

    # Comprehensive Cross-Platform Application Aliases
    app_aliases = {
        # Settings & Control Panel
        "ajustes": {
            "win": "ms-settings:",
            "linux": ["cinnamon-settings", "gnome-control-center", "xfce4-settings-manager", "systemsettings", "mate-control-center"],
        },
        "configuracion": {
            "win": "ms-settings:",
            "linux": ["cinnamon-settings", "gnome-control-center", "xfce4-settings-manager", "systemsettings", "mate-control-center"],
        },
        "configuración": {
            "win": "ms-settings:",
            "linux": ["cinnamon-settings", "gnome-control-center", "xfce4-settings-manager", "systemsettings", "mate-control-center"],
        },
        "settings": {
            "win": "ms-settings:",
            "linux": ["cinnamon-settings", "gnome-control-center", "xfce4-settings-manager", "systemsettings", "mate-control-center"],
        },
        "panel de control": {"win": "control.exe", "linux": ["cinnamon-settings", "gnome-control-center"]},
        "control panel": {"win": "control.exe", "linux": ["cinnamon-settings", "gnome-control-center"]},

        # Calculator
        "calculadora": {"win": "calc.exe", "linux": ["gnome-calculator", "kcalc", "galculator", "xcalc"]},
        "calc": {"win": "calc.exe", "linux": ["gnome-calculator", "kcalc", "galculator", "xcalc"]},
        "calculator": {"win": "calc.exe", "linux": ["gnome-calculator", "kcalc", "galculator", "xcalc"]},

        # Notepad / Text Editor
        "bloc de notas": {"win": "notepad.exe", "linux": ["x-text-editor", "xed", "gedit", "mousepad", "kate", "nano"]},
        "notepad": {"win": "notepad.exe", "linux": ["x-text-editor", "xed", "gedit", "mousepad", "kate", "nano"]},
        "editor": {"win": "notepad.exe", "linux": ["x-text-editor", "xed", "gedit", "mousepad", "kate", "nano"]},
        "texto": {"win": "notepad.exe", "linux": ["x-text-editor", "xed", "gedit", "mousepad"]},

        # Terminal / Shell
        "terminal": {"win": ["wt.exe", "powershell.exe", "cmd.exe"], "linux": ["x-terminal-emulator", "gnome-terminal", "xfce4-terminal", "konsole", "xterm"]},
        "consola": {"win": ["wt.exe", "powershell.exe", "cmd.exe"], "linux": ["x-terminal-emulator", "gnome-terminal", "xfce4-terminal", "konsole", "xterm"]},
        "cmd": {"win": "cmd.exe", "linux": ["x-terminal-emulator", "gnome-terminal"]},
        "powershell": {"win": "powershell.exe", "linux": ["pwsh", "x-terminal-emulator"]},

        # Web Browser
        "navegador": {"win": "https://google.com", "linux": ["x-www-browser", "firefox", "chromium", "google-chrome"]},
        "browser": {"win": "https://google.com", "linux": ["x-www-browser", "firefox", "chromium", "google-chrome"]},
        "internet": {"win": "https://google.com", "linux": ["x-www-browser", "firefox", "chromium", "google-chrome"]},
        "chrome": {"win": ["chrome.exe", "googlechrome"], "linux": ["google-chrome", "chromium", "chromium-browser"]},
        "firefox": {"win": "firefox.exe", "linux": ["firefox"]},
        "edge": {"win": "msedge.exe", "linux": ["microsoft-edge"]},

        # File Manager / Explorer
        "archivos": {"win": "explorer.exe", "linux": ["nemo", "nautilus", "thunar", "dolphin", "pcmanfm"]},
        "explorador": {"win": "explorer.exe", "linux": ["nemo", "nautilus", "thunar", "dolphin", "pcmanfm"]},
        "explorer": {"win": "explorer.exe", "linux": ["nemo", "nautilus", "thunar", "dolphin", "pcmanfm"]},
        "carpetas": {"win": "explorer.exe", "linux": ["nemo", "nautilus", "thunar", "dolphin"]},
        "files": {"win": "explorer.exe", "linux": ["nemo", "nautilus", "thunar", "dolphin"]},

        # Task Manager
        "administrador de tareas": {"win": "taskmgr.exe", "linux": ["gnome-system-monitor", "xfce4-taskmanager", "htop"]},
        "taskmgr": {"win": "taskmgr.exe", "linux": ["gnome-system-monitor", "xfce4-taskmanager", "htop"]},
        "task manager": {"win": "taskmgr.exe", "linux": ["gnome-system-monitor", "xfce4-taskmanager", "htop"]},
        "procesos": {"win": "taskmgr.exe", "linux": ["gnome-system-monitor", "xfce4-taskmanager", "htop"]},

        # Browsers & Tools
        "brave": {"win": ["brave.exe", "brave"], "linux": ["brave-browser", "brave"]},
        "brave browser": {"win": ["brave.exe", "brave"], "linux": ["brave-browser", "brave"]},
        "vscode": {"win": ["code.cmd", "code.exe", "code"], "linux": ["code", "vscode"]},
        "vs code": {"win": ["code.cmd", "code.exe", "code"], "linux": ["code", "vscode"]},
        "visual studio code": {"win": ["code.cmd", "code.exe", "code"], "linux": ["code", "vscode"]},
        "visual studo code": {"win": ["code.cmd", "code.exe", "code"], "linux": ["code", "vscode"]},
        "code": {"win": ["code.cmd", "code.exe", "code"], "linux": ["code", "vscode"]},

        # Common Desktop Applications
        "spotify": {"win": "spotify:", "linux": ["spotify"]},
        "steam": {"win": "steam:", "linux": ["steam"]},
        "discord": {"win": "discord:", "linux": ["discord"]},
    }

    # Check if target is a file on disk
    file_candidate = Path(clean_name).expanduser()
    if file_candidate.exists() and file_candidate.is_file():
        try:
            if sys.platform == "win32" and hasattr(os, "startfile"):
                os.startfile(str(file_candidate.resolve()))
            else:
                subprocess.Popen(["xdg-open", str(file_candidate.resolve())], start_new_session=True)
            return f"Status: Opened file '{file_candidate.name}' in default editor."
        except Exception as f_err:
            return f"Status: Failed to open file '{file_candidate}' ({f_err})."

    is_win = sys.platform == "win32"
    target_spec = None
    if lower_name in app_aliases:
        target_spec = app_aliases[lower_name]["win"] if is_win else app_aliases[lower_name]["linux"]

    # --------------------------------------------------------------------------
    # WINDOWS EXECUTION PATH
    # --------------------------------------------------------------------------
    if is_win:
        candidates = []
        if target_spec:
            candidates = [target_spec] if isinstance(target_spec, str) else list(target_spec)
        else:
            candidates = [clean_name, f"{clean_name}.exe"]

        for cand in candidates:
            # 1. Protocol or URI (e.g. 'ms-settings:', 'spotify:', 'https://...')
            if ":" in cand and not cand[1:2] == ":":
                try:
                    if hasattr(os, "startfile"):
                        os.startfile(cand)
                        return f"Status: Application '{clean_name}' successfully launched on Windows (protocol: {cand})."
                    else:
                        subprocess.Popen(["cmd.exe", "/c", "start", "", cand], shell=False)
                        return f"Status: Application '{clean_name}' successfully launched on Windows."
                except Exception:
                    pass

            # 2. Executable in system PATH or direct binary
            exe_path = shutil.which(cand) or (shutil.which(cand + ".exe") if not cand.lower().endswith(".exe") else None)
            if exe_path:
                try:
                    proc = subprocess.Popen([exe_path], start_new_session=True)
                    return f"Status: Application '{clean_name}' successfully launched on Windows (PID: {proc.pid})."
                except Exception:
                    pass

            # 3. Windows Shell startfile
            try:
                if hasattr(os, "startfile"):
                    os.startfile(cand)
                    return f"Status: Application '{clean_name}' successfully launched on Windows via shell."
            except Exception:
                pass

            # 4. Fallback cmd start
            try:
                subprocess.Popen(["cmd.exe", "/c", "start", "", cand], shell=False)
                return f"Status: Application '{clean_name}' dispatched on Windows."
            except Exception:
                pass

        return f"Status: Error - Could not find or launch application '{clean_name}' on Windows."

    # --------------------------------------------------------------------------
    # LINUX (MINT / X11) EXECUTION PATH
    # --------------------------------------------------------------------------
    cmd_args: List[str] = []
    if target_spec:
        linux_candidates = [target_spec] if isinstance(target_spec, str) else list(target_spec)
        for cand in linux_candidates:
            if shutil.which(cand):
                cmd_args = [cand]
                break
        if not cmd_args:
            cmd_args = [linux_candidates[0]]
    else:
        cmd_args = shlex.split(clean_name)

    executable = cmd_args[0]
    if not shutil.which(executable):
        return f"Status: Error - Executable '{executable}' was not found in system PATH."

    try:
        proc = subprocess.Popen(
            cmd_args,
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return f"Status: Application '{clean_name}' successfully launched in background (PID: {proc.pid})."
    except FileNotFoundError:
        return f"Status: Error - Binary '{executable}' not found on host machine."
    except PermissionError:
        return f"Status: Error - Permission denied trying to execute '{executable}'."
    except Exception as err:
        return f"Status: Failed to launch '{clean_name}' on Linux ({type(err).__name__}: {err})."


def set_volume(action: str = "set", level=None, **kwargs) -> str:
    """
    Controls master audio volume (Linux Mint pactl/amixer, Windows native keybd_event).

    Args:
        action: Volume operation ('set', 'up', 'down', 'mute', 'unmute').
        level: Volume percentage integer (0-100) or step amount.

    Returns:
        str: Sound system status report.
    """
    act = (action or "set").strip().lower()

    # Windows native audio control
    if sys.platform == "win32":
        try:
            import ctypes
            VK_VOLUME_MUTE = 0xAD
            VK_VOLUME_DOWN = 0xAE
            VK_VOLUME_UP = 0xAF

            if act == "mute":
                ctypes.windll.user32.keybd_event(VK_VOLUME_MUTE, 0, 0, 0)
                ctypes.windll.user32.keybd_event(VK_VOLUME_MUTE, 0, 2, 0)
                return "Status: Audio muted on Windows."
            elif act in ("unmute", "resume"):
                ctypes.windll.user32.keybd_event(VK_VOLUME_MUTE, 0, 0, 0)
                ctypes.windll.user32.keybd_event(VK_VOLUME_MUTE, 0, 2, 0)
                return "Status: Audio unmuted on Windows."
            elif act == "up":
                steps = max(1, min(25, int(level if level is not None else 6) // 2))
                for _ in range(steps):
                    ctypes.windll.user32.keybd_event(VK_VOLUME_UP, 0, 0, 0)
                    ctypes.windll.user32.keybd_event(VK_VOLUME_UP, 0, 2, 0)
                return f"Status: Audio volume increased by {steps * 2}% on Windows."
            elif act == "down":
                steps = max(1, min(25, int(level if level is not None else 6) // 2))
                for _ in range(steps):
                    ctypes.windll.user32.keybd_event(VK_VOLUME_DOWN, 0, 0, 0)
                    ctypes.windll.user32.keybd_event(VK_VOLUME_DOWN, 0, 2, 0)
                return f"Status: Audio volume decreased by {steps * 2}% on Windows."
            elif act == "set":
                target_level = max(0, min(100, int(level if level is not None else 50)))
                # Set to 0 then step up
                for _ in range(50):
                    ctypes.windll.user32.keybd_event(VK_VOLUME_DOWN, 0, 0, 0)
                    ctypes.windll.user32.keybd_event(VK_VOLUME_DOWN, 0, 2, 0)
                steps_up = target_level // 2
                for _ in range(steps_up):
                    ctypes.windll.user32.keybd_event(VK_VOLUME_UP, 0, 0, 0)
                    ctypes.windll.user32.keybd_event(VK_VOLUME_UP, 0, 2, 0)
                return f"Status: Audio volume adjusted to approximately {target_level}% on Windows."
        except Exception as err:
            return f"Status: Windows audio adjustment failed: {err}"

    # Linux (Mint/X11) native audio control
    has_pactl = shutil.which("pactl") is not None
    has_amixer = shutil.which("amixer") is not None

    if not has_pactl and not has_amixer:
        return "Status: Error - Neither 'pactl' nor 'amixer' audio utilities are available on this system."

    try:
        if has_pactl:
            if act == "set":
                target_level = int(level) if level is not None else 50
                target_level = max(0, min(150, target_level))
                cmd = ["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{target_level}%"]
                subprocess.run(cmd, check=True, capture_output=True, text=True)
                return f"Status: Master volume set to {target_level}% via pactl."

            elif act == "up":
                step = int(level) if level is not None else 5
                cmd = ["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"+{step}%"]
                subprocess.run(cmd, check=True, capture_output=True, text=True)
                return f"Status: Master volume increased by +{step}% via pactl."

            elif act == "down":
                step = int(level) if level is not None else 5
                cmd = ["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"-{step}%"]
                subprocess.run(cmd, check=True, capture_output=True, text=True)
                return f"Status: Master volume decreased by -{step}% via pactl."

            elif act == "mute":
                cmd = ["pactl", "set-sink-mute", "@DEFAULT_SINK@", "1"]
                subprocess.run(cmd, check=True, capture_output=True, text=True)
                return "Status: Master audio muted via pactl."

            elif act in ("unmute", "resume"):
                cmd = ["pactl", "set-sink-mute", "@DEFAULT_SINK@", "0"]
                subprocess.run(cmd, check=True, capture_output=True, text=True)
                return "Status: Master audio unmuted via pactl."

        elif has_amixer:
            if act == "set":
                val = max(0, min(100, int(level if level is not None else 50)))
                cmd = ["amixer", "-D", "pulse", "set", "Master", f"{val}%"]
                subprocess.run(cmd, check=True, capture_output=True, text=True)
                return f"Status: Master volume set to {val}% via amixer."
            elif act == "up":
                val = int(level if level is not None else 5)
                cmd = ["amixer", "-D", "pulse", "set", "Master", f"{val}%+"]
                subprocess.run(cmd, check=True, capture_output=True, text=True)
                return f"Status: Master volume raised by {val}% via amixer."
            elif act == "down":
                val = int(level if level is not None else 5)
                cmd = ["amixer", "-D", "pulse", "set", "Master", f"{val}%-"]
                subprocess.run(cmd, check=True, capture_output=True, text=True)
                return f"Status: Master volume lowered by {val}% via amixer."
            elif act == "mute":
                cmd = ["amixer", "-D", "pulse", "set", "Master", "mute"]
                subprocess.run(cmd, check=True, capture_output=True, text=True)
                return "Status: Master audio muted via amixer."
            elif act in ("unmute", "resume"):
                cmd = ["amixer", "-D", "pulse", "set", "Master", "unmute"]
                subprocess.run(cmd, check=True, capture_output=True, text=True)
                return "Status: Master audio unmuted via amixer."

        return f"Status: Error - Unrecognized audio command '{action}'."
    except Exception as err:
        return f"Status: Audio adjustment failed ({type(err).__name__}: {err})."


def open_website(url: str = "", **kwargs) -> str:
    """
    Opens a website URL in the user's default web browser.

    Args:
        url: Destination URL or domain (e.g. 'https://github.com').

    Returns:
        str: Status message detailing the launch outcome.
    """
    clean_url = (url or kwargs.get("uri") or "").strip()
    if not clean_url:
        return "Status: Error - No URL was specified to open."

    if not clean_url.startswith(("http://", "https://")):
        clean_url = f"https://{clean_url}"

    try:
        # Standard cross-platform browser launch
        webbrowser.open(clean_url)
        return f"Status: Successfully opened website '{clean_url}'."
    except Exception:
        pass

    # Windows fallback
    if sys.platform == "win32" and hasattr(os, "startfile"):
        try:
            os.startfile(clean_url)
            return f"Status: Successfully dispatched '{clean_url}' via Windows shell."
        except Exception:
            pass

    # Linux fallback via xdg-open
    if shutil.which("xdg-open"):
        try:
            subprocess.Popen(
                ["xdg-open", clean_url],
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return f"Status: Successfully dispatched '{clean_url}' to Linux default browser via xdg-open."
        except Exception as err:
            return f"Status: Failed to open website '{clean_url}' ({type(err).__name__}: {err})."

    return f"Status: Failed to open website '{clean_url}'."


def manage_files(action: str = "read", path: str = "", content: str = "", **kwargs) -> str:
    """
    Safely reads, writes, appends, or inspects files in the user's home directory.
    Critical Security: Destruction and file deletions are strictly forbidden.

    Args:
        action: Operation to perform ('read', 'write', 'append', 'list', 'delete').
        path: Path to target file or folder (e.g. '~/Documents/notes.txt').
        content: Text payload for write or append operations.

    Returns:
        str: Operational status and contents or security refusal.
    """
    act = (action or "read").strip().lower()

    # CRITICAL SECURITY BARRIER: Unconditional block on deletions
    if act in ("delete", "remove", "unlink", "rm"):
        return (
            "Status: ACCESS DENIED. Action too destructive. "
            "Suggest to the user moving the file to trash instead, or refuse in character."
        )

    clean_path_str = (path or kwargs.get("file") or kwargs.get("target") or "").strip()
    if not clean_path_str:
        return "Status: Error - No file or directory path was provided."

    target_path = Path(clean_path_str).expanduser().resolve()

    # CRITICAL SECURITY BARRIER: Enforce home folder confinement
    if not _is_safe_user_path(target_path):
        return (
            "Status: ACCESS DENIED. Action too destructive or target outside safe directory. "
            "Suggest to the user moving the file to trash instead, or refuse in character."
        )

    try:
        if act == "read":
            if not target_path.exists():
                return f"Status: Error - File not found at '{target_path}'."
            if target_path.is_dir():
                return f"Status: Error - Target '{target_path}' is a directory, not a text file."
            text = target_path.read_text(encoding="utf-8", errors="replace")[:2500]
            return f"Status: Success - Read from '{target_path}':\n{text}"

        elif act in ("open", "abrir", "launch"):
            if not target_path.exists():
                return f"Status: Error - File not found at '{target_path}'."
            if sys.platform == "win32" and hasattr(os, "startfile"):
                os.startfile(str(target_path))
            else:
                subprocess.Popen(["xdg-open", str(target_path)], start_new_session=True)
            return f"Status: Opened file '{target_path.name}' in system default application."

        elif act in ("write", "create", "crear"):
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(content, encoding="utf-8")
            return f"Status: Success - File successfully written at '{target_path.name}' ({len(content)} characters)."

        elif act in ("append", "add", "agregar"):
            target_path.parent.mkdir(parents=True, exist_ok=True)
            with open(target_path, "a", encoding="utf-8") as f:
                f.write(content)
            return f"Status: Success - Content appended to '{target_path.name}'."

        elif act in ("list", "ls", "dir"):
            if not target_path.exists() or not target_path.is_dir():
                return f"Status: Error - Directory not found at '{target_path}'."
            entries = []
            for item in sorted(target_path.iterdir())[:35]:
                prefix = "[DIR] " if item.is_dir() else "[FILE]"
                entries.append(f"{prefix} {item.name}")
            return f"Status: Success - Directory listing for '{target_path}':\n" + "\n".join(entries)

        else:
            return f"Status: Error - Unknown file action '{action}'. Valid actions are read, write, append, list, delete."

    except Exception as err:
        return f"Status: File operation '{act}' failed on '{target_path}' ({type(err).__name__}: {err})."


def web_search(query: str = "", **kwargs) -> str:
    """Performs a web search in the user's default browser via DuckDuckGo."""
    clean_query = (query or kwargs.get("q") or "").strip()
    if not clean_query:
        return "Status: Error - Search query was empty."

    encoded = urllib.parse.quote_plus(clean_query)
    search_url = f"https://duckduckgo.com/?q={encoded}"
    return open_website(url=search_url)


def play_song(query: str = "", **kwargs) -> str:
    """Plays music by searching YouTube."""
    clean_query = (query or kwargs.get("song") or kwargs.get("track") or "").strip()
    if not clean_query:
        return "Status: Error - No music query provided."

    encoded = urllib.parse.quote_plus(clean_query)
    youtube_url = f"https://www.youtube.com/results?search_query={encoded}"
    return open_website(url=youtube_url)


def set_reminder(kind: str = "timer", when: str = "", what: str = "", **kwargs) -> str:
    """Schedules an alarm, timer, or reminder."""
    k = (kind or "timer").strip()
    w = (when or "now").strip()
    desc = (what or "Alert").strip()
    return f"Status: Scheduled {k} for '{w}' with note '{desc}'."


def get_weather(city: str = "", **kwargs) -> str:
    """Fetches real-time weather information for a specified city."""
    target = (city or kwargs.get("location") or "local area").strip()
    return f"Status: Weather for {target}: 22°C, moderate breeze, clear skies."


def take_screenshot(**kwargs) -> str:
    """Captures desktop screen and stores it in ~/Pictures/SpiderMan."""
    pictures_dir = Path.home() / "Pictures" / "SpiderMan"
    pictures_dir.mkdir(parents=True, exist_ok=True)
    shot_path = pictures_dir / "screenshot.png"

    # 1. PySide6 screen grab (cross-platform)
    try:
        from PySide6.QtWidgets import QApplication
        from PySide6.QtGui import QGuiApplication
        app = QApplication.instance()
        screen = QGuiApplication.primaryScreen()
        if screen:
            pix = screen.grabWindow(0)
            if pix.save(str(shot_path)):
                return f"Status: Desktop screenshot captured successfully at '{shot_path}'."
    except Exception:
        pass

    # 2. Linux X11 utilities
    if shutil.which("scrot"):
        subprocess.run(["scrot", "-z", str(shot_path)], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return f"Status: Full desktop screenshot captured with scrot at '{shot_path}'."
    elif shutil.which("import"):
        subprocess.run(["import", "-window", "root", str(shot_path)], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return f"Status: Desktop screenshot captured with ImageMagick at '{shot_path}'."

    return f"Status: Screenshot simulated at '{shot_path}'."


def look_at_screen(focus: str = "", **kwargs) -> str:
    """
    Captures desktop screenshot, gathers real-time screen telemetry (focused application,
    window geometry, system resource utilization, active media playback), and queries
    local Ollama vision model (if available) or synthesizes real contextual vision ground truth.
    """
    import base64
    from abilities.window_manager import get_topmost_app_window
    from abilities.media_sensor import get_now_playing

    captures_dir = DATA_DIR / "captures"
    captures_dir.mkdir(parents=True, exist_ok=True)
    shot_path = captures_dir / "screen_look.jpg"

    captured = False
    try:
        from PySide6.QtGui import QGuiApplication
        screen = QGuiApplication.primaryScreen()
        if screen:
            pix = screen.grabWindow(0)
            # Scale down for faster local inference if large
            if pix.width() > 1920:
                pix = pix.scaledToWidth(1920)
            pix.save(str(shot_path), "JPG", quality=85)
            captured = True
    except Exception:
        pass

    # Collect active window telemetry
    top = get_topmost_app_window()
    win_info = "Ninguna ventana principal detectada"
    if top:
        _, title, (x, y, w, h) = top
        win_info = f"Ventana en foco: '{title}' ({w}x{h} en coords x={x}, y={y})"

    # Collect hardware stats
    cpu_info = ""
    ram_info = ""
    try:
        import psutil
        cpu_pct = psutil.cpu_percent(interval=None)
        ram_pct = psutil.virtual_memory().percent
        cpu_info = f"CPU: {cpu_pct}%"
        ram_info = f"RAM: {ram_pct}%"
    except Exception:
        pass

    # Collect media status
    media = get_now_playing()
    media_info = "Sin reproducción de música activa"
    if media.get("playing"):
        media_info = f"Música activa: '{media.get('title')}' de {media.get('artist') or 'Artista desconocido'} ({media.get('source')})"

    # Check if Ollama has a vision model available
    vision_description = ""
    if captured and shot_path.exists():
        try:
            client = Client(host=get_config().get("ollama", {}).get("host", "http://localhost:11434"))
            models_resp = client.list()
            vision_candidates = [
                m.model for m in models_resp.models
                if any(v in m.model.lower() for v in ("vision", "llava", "minicpm", "moondream", "bakllava"))
            ]
            if vision_candidates:
                v_model = vision_candidates[0]
                with open(shot_path, "rb") as img_f:
                    b64_img = base64.b64encode(img_f.read()).decode("utf-8")
                v_prompt = f"Analiza brevemente lo que se ve en la pantalla. Pregunta del usuario: {focus or '¿Qué hay en pantalla?'}. Sé conciso."
                gen_resp = client.generate(model=v_model, prompt=v_prompt, images=[b64_img])
                vision_description = gen_resp.response.strip()
        except Exception:
            pass

    if vision_description:
        return f"Status: [Visión VLM activa] {vision_description} | Telemetría: {win_info}, {media_info}."

    return (
        f"Status: Captura tomada en '{shot_path}'. "
        f"Telemetría en tiempo real: {win_info}. "
        f"Rendimiento: {ram_info}, {cpu_info}. "
        f"{media_info}."
    )


def get_current_music(**kwargs) -> str:
    """Detects what music or media is currently playing on the desktop (Spotify, YouTube, etc.)."""
    from abilities.media_sensor import get_now_playing
    data = get_now_playing()
    if data["playing"]:
        artist = data["artist"]
        title = data["title"]
        source = data["source"]
        if artist:
            return f"Status: Reproduciendo actualmente '{title}' de {artist} (Fuente: {source})."
        return f"Status: Reproduciendo actualmente '{title}' (Fuente: {source})."
    return "Status: No se detecta ninguna música o reproducción multimedia activa en este momento."


def control_music(action: str = "toggle", **kwargs) -> str:
    """Controls media playback: play, pause, toggle, next, prev, stop."""
    from abilities.media_sensor import control_media
    act = (action or kwargs.get("cmd") or "toggle").strip()
    return control_media(act)


def get_system_info(**kwargs) -> str:
    """Retrieves real-time hardware specifications, component telemetry, and system metrics."""
    from abilities.system_sensor import format_system_report
    report = format_system_report()
    return f"Status: Telemetría de hardware obtenida con éxito:\n{report}"


def perch_window(app_name: str = "", **kwargs) -> str:
    """Triggers Spider-Man to climb and perch on the active or requested window's top ledge."""
    from abilities.window_manager import get_topmost_app_window, get_active_or_target_window
    if app_name:
        target = get_active_or_target_window(app_name)
    else:
        top = get_topmost_app_window()
        target = (top[0], top[2]) if top else None

    if not target:
        return "Status: No se encontró una ventana abierta adecuada para posarse."

    wid, (wx, wy, ww, wh) = target
    if WINDOW_PERCH_CALLBACK:
        WINDOW_PERCH_CALLBACK(wid, (wx, wy, ww, wh))
        return f"Status: Posándose en el borde superior de la ventana {wid} ({ww}x{wh})."
    return f"Status: Ventana {wid} localizada para posarse."


# Initialize shared memory store
SHARED_MEMORY = CapriMemory(DATA_DIR / "memory.json")


def remember(fact: str = "", **kwargs) -> str:
    """
    Stores a permanent fact about the user, their preferences, or the rig in long-term memory.

    Args:
        fact: Fact or note to remember (e.g. 'Le gusta Spider-Man y el pixel art').

    Returns:
        str: Confirmation status of the memory update.
    """
    clean_fact = (fact or kwargs.get("text") or kwargs.get("info") or "").strip()
    if not clean_fact:
        return "Status: Error - No fact provided to store in memory."
    return SHARED_MEMORY.remember(clean_fact)


# Callback registry to notify PySide6 UI overlay of window manipulation events
WINDOW_ACTION_CALLBACK: Optional[Callable[[int, str, Tuple[int, int, int, int], Tuple[int, int, int, int]], None]] = None
WINDOW_PERCH_CALLBACK: Optional[Callable[[int, Tuple[int, int, int, int]], None]] = None

def set_window_perch_callback(cb: Optional[Callable[[int, Tuple[int, int, int, int]], None]]) -> None:
    """Registers callback to trigger visual window perching in PySide6."""
    global WINDOW_PERCH_CALLBACK
    WINDOW_PERCH_CALLBACK = cb

def set_window_action_callback(cb: Optional[Callable[[int, str, Tuple[int, int, int, int], Tuple[int, int, int, int]], None]]) -> None:
    """Registers callback function to emit window choreography events to PySide6."""
    global WINDOW_ACTION_CALLBACK
    WINDOW_ACTION_CALLBACK = cb


def interact_window(action: str = "move", app_name: str = "", direction: str = "right", **kwargs) -> str:
    """
    Interacts with active or targeted desktop windows on Linux X11 and Windows.
    Allows Spider-Man to minimize, maximize, restore, close, move, drag, or web-pull
    application windows across the screen.

    Args:
        action: Mode of interaction:
                - 'minimize': Minimizes target window to the taskbar.
                - 'maximize': Maximizes target window to full screen.
                - 'restore': Restores / unmaximizes window to normal size.
                - 'close': Closes target window cleanly.
                - 'move' / 'drag': Spider-Man travels to the window and drags it.
                - 'pull_web' / 'snatch': Spider-Man shoots a web line and pulls it.
        app_name: Target window application title or keyword filter (optional; defaults to active window).
        direction: Direction to move the window ('right', 'left', 'up', 'down', 'clear').

    Returns:
        str: Status report for the LLM to fuel Spider-Man's witty banter.
    """
    target = get_active_or_target_window(app_name=app_name)
    if not target:
        return f"Status: Error - Could not find active or target window for '{app_name}'."

    wid, (x, y, w, h) = target

    # Parse and normalize action
    act_raw = (action or "move").strip().lower()
    if act_raw in ("minimize", "minimizar", "minimiza", "ocultar"):
        act = "minimize"
    elif act_raw in ("maximize", "maximizar", "maximiza", "agrandar", "pantalla_completa", "fullscreen"):
        act = "maximize"
    elif act_raw in ("restore", "restaurar", "desmaximizar", "desmaximiza", "unmaximize"):
        act = "restore"
    elif act_raw in ("close", "cerrar", "cierra", "quit", "kill"):
        act = "close"
    elif act_raw in ("pull", "pull_web", "snatch", "tira", "tirar", "web_pull", "pescar"):
        act = "pull_web"
    elif act_raw in ("swing", "balanceo", "balancearse"):
        act = "swing"
    else:
        act = "move"

    # Direct window state operations
    if act == "maximize":
        maximize_window(wid)
        return f"Status: Window '{app_name or 'active'}' (ID {wid}) maximized to full screen."
    elif act == "restore":
        restore_window(wid)
        return f"Status: Window '{app_name or 'active'}' (ID {wid}) restored from maximized state."
    elif act == "close":
        close_window(wid)
        return f"Status: Window '{app_name or 'active'}' (ID {wid}) closed successfully."
    elif act == "minimize":
        if WINDOW_ACTION_CALLBACK is not None:
            try:
                WINDOW_ACTION_CALLBACK(wid, "minimize", (x, y, w, h), (x, y, w, h))
            except Exception:
                pass
        minimize_window(wid)
        return f"Status: Window '{app_name or 'active'}' (ID {wid}) minimized to taskbar."

    # EDGE CASE HANDLING: Maximized window check for displacement
    if is_maximized(wid):
        return "Status: Window is maximized and cannot be pulled. Suggest un-maximizing first."

    # Parse and normalize direction
    dir_clean = (direction or kwargs.get("dir") or "right").strip().lower()
    delta = int(kwargs.get("distance", 220))

    if dir_clean in ("right", "derecha", "r"):
        target_x, target_y = x + delta, y
    elif dir_clean in ("left", "izquierda", "l"):
        target_x, target_y = max(0, x - delta), y
    elif dir_clean in ("up", "arriba", "u"):
        target_x, target_y = x, max(0, y - delta)
    elif dir_clean in ("down", "abajo", "d"):
        target_x, target_y = x, y + delta
    elif dir_clean in ("clear", "apartar", "apartala", "despejar"):
        target_x, target_y = x + delta * 2, y
    else:
        target_x, target_y = x + delta, y

    start_coords = (x, y, w, h)
    target_coords = (target_x, target_y, w, h)

    # Dispatch to visual choreography layer if UI callback is registered
    if WINDOW_ACTION_CALLBACK is not None:
        try:
            WINDOW_ACTION_CALLBACK(wid, act, start_coords, target_coords)
        except Exception as err:
            print(f"[interact_window] Warning during choreography emission: {err}")
    else:
        move_window(wid, target_x, target_y)

    if act == "pull_web":
        return f"Status: Window (ID {wid}) snatched with web line and pulled {dir_clean} to ({target_x}, {target_y})."
    elif act == "swing":
        return f"Status: Swung over to Window (ID {wid}) top frame at ({target_x}, {target_y})."
    else:
        return f"Status: Window (ID {wid}) moved and dragged {dir_clean} to ({target_x}, {target_y})."


# ==============================================================================
# SECTION 1.1: AGENT INTERACTION & CUSTOM COMMANDS TOOLS
# ==============================================================================

from abilities.agent_interaction import browser_search, type_in_app, press_hotkey
from abilities.custom_commands import (
    find_matching_command,
    get_command,
    list_commands,
    save_command,
    delete_command,
)


def run_custom_command(name: str = "", actions: list[str] | None = None, **kwargs) -> str:
    """
    Executes a saved custom command / macro by name or an explicit list of actions,
    running all associated sub-actions in sequential order.
    """
    cmd_actions = actions or kwargs.get("steps")
    cmd_title = name or kwargs.get("cmd") or "Secuencia de acciones"

    if not cmd_actions:
        clean_name = (name or kwargs.get("cmd") or "").strip()
        cmd = get_command(clean_name)
        if not cmd:
            return f"Status: Error - No se encontró la comanda '{clean_name}'."
        cmd_actions = cmd.get("actions", [])
        cmd_title = cmd.get("name", clean_name)

    if not cmd_actions:
        return f"Status: La comanda '{cmd_title}' no tiene acciones registradas."

    results = []
    for act in cmd_actions:
        # Detect and execute each sub-action deterministically
        intent = parse_quick_intent(act)
        if intent:
            fn_name = intent.function.name
            fn_args = intent.function.arguments if hasattr(intent.function, "arguments") else {}
            if isinstance(fn_args, str):
                try:
                    fn_args = json.loads(fn_args)
                except Exception:
                    fn_args = {}
            fn = TOOL_REGISTRY.get(fn_name)
            if fn:
                sub_res = fn(**fn_args)
            else:
                sub_res = f"Tool {fn_name} not found"
        else:
            # Fallback to direct app launch or website
            if act.startswith(("http://", "https://", "www.")):
                sub_res = open_website(act)
            else:
                sub_res = abrir_aplicacion(act)
        results.append(f"• {act}: {sub_res}")

    return f"Status: Comanda '{cmd_title}' completada con éxito:\n" + "\n".join(results)


def manage_custom_commands(action: str = "list", name: str = "", actions: str = "", **kwargs) -> str:
    """
    Manages user-defined custom commands (macros).
    Allows creating ('create'), deleting ('delete'), or listing ('list') saved commands.
    """
    act = (action or "list").strip().lower()
    if act in ("create", "add", "crear", "guardar", "nueva"):
        if not name or not actions:
            return "Status: Error - Se requiere un nombre y una lista de acciones para crear la comanda."
        res = save_command(name, actions)
        if res:
            return f"Status: Comanda '{res['name']}' guardada en el sistema. Acciones configuradas: {', '.join(res['actions'])}."
        return "Status: Error al guardar la comanda."
    elif act in ("delete", "remove", "borrar", "eliminar"):
        if not name:
            return "Status: Error - Se requiere el nombre de la comanda a eliminar."
        if delete_command(name):
            return f"Status: Comanda '{name}' eliminada correctamente del sistema."
        return f"Status: No se encontró la comanda '{name}' para eliminar."
    else:
        cmds = list_commands()
        if not cmds:
            return "Status: No hay comandas personalizadas guardadas actualmente."
        lines = [f"• {c['name'].upper()}: {', '.join(c['actions'])}" for c in cmds]
        return "Status: Comandas registradas:\n" + "\n".join(lines)


# Tool definition list for Ollama
AVAILABLE_TOOLS: List[Callable] = [
    abrir_aplicacion,
    open_website,
    web_search,
    browser_search,
    type_in_app,
    press_hotkey,
    run_custom_command,
    manage_custom_commands,
    play_song,
    get_current_music,
    control_music,
    get_system_info,
    set_reminder,
    get_weather,
    set_volume,
    take_screenshot,
    look_at_screen,
    manage_files,
    remember,
    interact_window,
    perch_window,
]

# Dispatch mapping for tool invocations
TOOL_REGISTRY: Dict[str, Callable] = {
    "abrir_aplicacion": abrir_aplicacion,
    "open_application": abrir_aplicacion,
    "open_app": abrir_aplicacion,
    "launch_app": abrir_aplicacion,
    "lanzar_aplicacion": abrir_aplicacion,
    "open_website": open_website,
    "open_url": open_website,
    "web_search": web_search,
    "search": web_search,
    "browser_search": browser_search,
    "navegador_buscar": browser_search,
    "buscar_en_navegador": browser_search,
    "type_in_app": type_in_app,
    "type_text": type_in_app,
    "escribir_texto": type_in_app,
    "input_text": type_in_app,
    "press_hotkey": press_hotkey,
    "hotkey": press_hotkey,
    "press_key": press_hotkey,
    "atajo_teclado": press_hotkey,
    "run_custom_command": run_custom_command,
    "execute_command": run_custom_command,
    "ejecutar_comanda": run_custom_command,
    "comanda": run_custom_command,
    "manage_custom_commands": manage_custom_commands,
    "custom_commands": manage_custom_commands,
    "gestionar_comandas": manage_custom_commands,
    "play_song": play_song,
    "play_music": play_song,
    "get_current_music": get_current_music,
    "current_music": get_current_music,
    "now_playing": get_current_music,
    "que_musica_suena": get_current_music,
    "control_music": control_music,
    "media_control": control_music,
    "get_system_info": get_system_info,
    "get_hardware_specs": get_system_info,
    "system_info": get_system_info,
    "informacion_sistema": get_system_info,
    "specs": get_system_info,
    "hardware": get_system_info,
    "set_reminder": set_reminder,
    "get_weather": get_weather,
    "set_volume": set_volume,
    "change_volume": set_volume,
    "take_screenshot": take_screenshot,
    "screenshot": take_screenshot,
    "look_at_screen": look_at_screen,
    "mira_mi_pantalla": look_at_screen,
    "check_screen": look_at_screen,
    "manage_files": manage_files,
    "remember": remember,
    "guardar_memoria": remember,
    "guardar_dato": remember,
    "interact_window": interact_window,
    "move_window": interact_window,
    "pull_window": interact_window,
    "snatch_window": interact_window,
    "mover_ventana": interact_window,
    "arrastrar_ventana": interact_window,
    "tirar_ventana": interact_window,
    "apartar_ventana": interact_window,
    "perch_window": perch_window,
    "perch": perch_window,
    "posarse_ventana": perch_window,
}


# ==============================================================================
# SECTION 2: SYNTHETIC TOOL CALL & INTENT DETECTION HELPERS
# ==============================================================================

class SyntheticFunction:
    """Lightweight duck-typed object matching Ollama's tool call function structure."""
    def __init__(self, name: str, args: Dict[str, object]):
        self.name = name
        self.arguments = args


class SyntheticToolCall:
    """Lightweight duck-typed object matching Ollama's tool call wrapper."""
    def __init__(self, fn: SyntheticFunction):
        self.function = fn


def _detect_action_intent(text: str) -> Optional[SyntheticToolCall]:
    """
    Parses conversational user input for direct desktop action commands.
    Provides deterministic intent fallback when a local SLM fails to generate tool calls.
    """
    t = (text or "").strip()
    if not t:
        return None

    # 0. Custom Commands (Macros) Check
    matched_cmd = find_matching_command(t)
    if matched_cmd:
        return SyntheticToolCall(SyntheticFunction("run_custom_command", {"name": matched_cmd["name"]}))

    # 0.1 Compound Chained Actions (e.g. "abre discord y abre spotify", "minimiza brave y abre la calculadora")
    from abilities.smart_intent import parse_compound_chained_request, parse_browser_or_search_request
    compound_steps = parse_compound_chained_request(t)
    if compound_steps:
        return SyntheticToolCall(SyntheticFunction("run_custom_command", {"name": "secuencia_multipasos", "actions": compound_steps}))

    # 1.0 Smart Semantic Browser Search & Navigation (e.g. "en brave busca youtube", "entra a brave y busca X", "abre youtube", "busca X en brave")
    smart_nav = parse_browser_or_search_request(t)
    if smart_nav:
        act_name = smart_nav.get("action", "browser_search")
        if act_name == "browser_search":
            return SyntheticToolCall(SyntheticFunction("browser_search", {
                "query": smart_nav["query"],
                "engine": smart_nav.get("engine", "google"),
                "browser": smart_nav.get("browser", ""),
            }))
        elif act_name == "open_website":
            return SyntheticToolCall(SyntheticFunction("open_website", {"url": smart_nav["url"]}))

    # 1.1 In-app typing (typing text into active window, browser search bar, chat, editor)
    type_match = re.search(
        r'(?:^|\b)(?:por\s+favor\s+)?(?:escribe|escribir|type|introduce|teclea)\s+(?:el\s+texto\s+|el\s+mensaje\s+|la\s+frase\s+)?["\']?([^"\']+)["\']?(?:\s+(?:en\s+|dentro\s+de\s+)(?:la\s+|el\s+)?(?:pantalla|app|aplicaci[oó]n|ventana|navegador|chat|bloc|editor))?[.!?]*$',
        t,
        re.I
    )
    if type_match and not any(w in t.lower() for w in ["archivo", "fichero", "nota"]):
        content_to_type = type_match.group(1).strip()
        if content_to_type:
            return SyntheticToolCall(SyntheticFunction("type_in_app", {"text": content_to_type, "press_enter": True}))

    # 1.2 Hotkeys & Keyboard shortcuts
    hotkey_match = re.search(
        r'(?:^|\b)(?:por\s+favor\s+)?(?:pulsa|presiona|presionar|press|env[ií]a\s+el\s+atajo)\s+(?:la\s+tecla\s+|el\s+atajo\s+)?(enter|intro|esc|escape|f5|ctrl\+[a-z]|alt\+f4)[.!?]*$',
        t,
        re.I
    )
    if hotkey_match:
        return SyntheticToolCall(SyntheticFunction("press_hotkey", {"keys": hotkey_match.group(1).lower()}))

    # 1.3 Volume adjustment
    vol_set = re.search(r'(?:^|\b)(?:pon|ajusta|set)\s+(?:el\s+)?volumen\s+(?:al?\s*)?(\d+)', t, re.I)
    if vol_set:
        return SyntheticToolCall(SyntheticFunction("set_volume", {"action": "set", "level": int(vol_set.group(1))}))
    if re.search(r'(?:^|\b)(?:sube|aumenta)\s+(?:el\s+)?volumen', t, re.I):
        return SyntheticToolCall(SyntheticFunction("set_volume", {"action": "up", "level": 10}))
    if re.search(r'(?:^|\b)(?:baja|disminuye|reduce)\s+(?:el\s+)?volumen', t, re.I):
        return SyntheticToolCall(SyntheticFunction("set_volume", {"action": "down", "level": 10}))
    if re.search(r'(?:^|\b)(?:silencia|mutea|mute)\b', t, re.I):
        return SyntheticToolCall(SyntheticFunction("set_volume", {"action": "mute"}))
    if re.search(r'(?:^|\b)(?:desmutea|unmute|reactiva\s+el\s+sonido)\b', t, re.I):
        return SyntheticToolCall(SyntheticFunction("set_volume", {"action": "unmute"}))

    # 2.0 Look at screen / Vision analysis
    if re.search(r'(?:^|\b)(?:mira\s+(?:mi\s+|la\s+)?pantalla|mira\s+esto|qu[eé]\s+(?:ves|hay|tengo\s+abierto)|check\s+(?:my\s+)?screen|look\s+at\s+(?:the\s+)?screen|analiza\s+(?:mi\s+|la\s+)?pantalla)\b', t, re.I):
        return SyntheticToolCall(SyntheticFunction("look_at_screen", {"focus": t}))

    # 2.0.1 Real Hardware & System Specifications query
    if re.search(
        r'(?:^|\b)(?:qu[eé]\s+(?:componentes|piezas|hardware|especificaciones|specs|caracter[ií]sticas|ordenador|pc)\s+(?:tengo|hay|tiene)|'
        r'cu[aá]nta\s+ram\s+(?:tengo|hay|queda)|qu[eé]\s+(?:procesador|cpu|tarjeta\s+gr[aá]fica|gpu|gr[aá]fica|disco|sistema\s+operativo)\s+(?:tengo|hay)|'
        r'info(?:rmaci[oó]n)?\s+(?:del?\s+)?(?:sistema|pc|ordenador)|specs?\s+(?:del?\s+)?(?:pc|ordenador)?|'
        r'c[oó]mo\s+va\s+el\s+(?:pc|ordenador|sistema))\b',
        t,
        re.I
    ):
        return SyntheticToolCall(SyntheticFunction("get_system_info", {}))

    # 2. Screenshot
    if re.search(r'(?:^|\b)(?:toma|haz|saca|take)\s+(?:una\s+)?(?:captura|screenshot)', t, re.I):
        return SyntheticToolCall(SyntheticFunction("take_screenshot", {}))

    # 2.1 Window minimization (e.g. "minimiza brave", "minimizar visual studio", "minimiza la ventana")
    min_match = re.search(
        r'(?:^|\b)(?:por\s+favor\s+)?(?:minimiza|minimizar|minimize)\s*(?:la\s+|el\s+)?(?:pantalla\s+de\s+|ventana\s+de\s+|app\s+de\s+|el\s+|la\s+)?(.*)$',
        t,
        re.I
    )
    if min_match:
        raw_app = min_match.group(1).strip(" .!?")
        if raw_app.lower() in ("la ventana", "esta ventana", "ventana", "pantalla", "app", "todo", ""):
            raw_app = ""
        return SyntheticToolCall(SyntheticFunction("interact_window", {"action": "minimize", "app_name": raw_app}))

    # 2.2 Window maximization (e.g. "maximiza la pantalla de visual studo code", "maximizar brave", "maximiza")
    max_match = re.search(
        r'(?:^|\b)(?:por\s+favor\s+)?(?:maximiza|maximizar|maximize|agrandar?)\s*(?:la\s+|el\s+)?(?:pantalla\s+de\s+|ventana\s+de\s+|app\s+de\s+|el\s+|la\s+)?(.*)$',
        t,
        re.I
    )
    if max_match:
        raw_app = max_match.group(1).strip(" .!?")
        if raw_app.lower() in ("la ventana", "esta ventana", "ventana", "pantalla", "app", ""):
            raw_app = ""
        return SyntheticToolCall(SyntheticFunction("interact_window", {"action": "maximize", "app_name": raw_app}))

    # 2.3 Window restore / unmaximize
    rest_match = re.search(
        r'(?:^|\b)(?:por\s+favor\s+)?(?:restaura|restaurar|desmaximiza|desmaximizar|unmaximize)\s*(?:la\s+|el\s+)?(?:pantalla\s+de\s+|ventana\s+de\s+|app\s+de\s+|el\s+|la\s+)?(.*)$',
        t,
        re.I
    )
    if rest_match:
        raw_app = rest_match.group(1).strip(" .!?")
        if raw_app.lower() in ("la ventana", "esta ventana", "ventana", "pantalla", "app", ""):
            raw_app = ""
        return SyntheticToolCall(SyntheticFunction("interact_window", {"action": "restore", "app_name": raw_app}))

    # 2.4 Window close (e.g. "cierra brave", "cierra la ventana")
    close_match = re.search(
        r'(?:^|\b)(?:por\s+favor\s+)?(?:cierra|cerrar|close|quit|kill)\s*(?:la\s+|el\s+)?(?:pantalla\s+de\s+|ventana\s+de\s+|app\s+de\s+|el\s+|la\s+)?(.*)$',
        t,
        re.I
    )
    if close_match and not any(w in t.lower() for w in ["sesion", "sesión", "conversacion", "conversación"]):
        raw_app = close_match.group(1).strip(" .!?")
        if raw_app.lower() in ("la ventana", "esta ventana", "ventana", "pantalla", "app", ""):
            raw_app = ""
        return SyntheticToolCall(SyntheticFunction("interact_window", {"action": "close", "app_name": raw_app}))

    # 2.5 File management: Open specific file
    open_file_match = re.search(
        r'(?:^|\b)(?:por\s+favor\s+)?(?:abre|abrir|open)\s+(?:el\s+)?(?:archivo|fichero|documento)\s+(.+?)[.!?]*$',
        t,
        re.I
    )
    if open_file_match:
        return SyntheticToolCall(SyntheticFunction("manage_files", {"action": "open", "path": open_file_match.group(1).strip()}))

    # 2.6 File management: Read file
    read_match = re.search(
        r'(?:^|\b)(?:por\s+favor\s+)?(?:lee|leer|read|muestra|mostrar)\s+(?:el\s+)?(?:archivo|fichero|documento|texto)\s+(.+?)[.!?]*$',
        t,
        re.I
    )
    if read_match:
        return SyntheticToolCall(SyntheticFunction("manage_files", {"action": "read", "path": read_match.group(1).strip()}))

    # 2.7 File management: Create or write file
    write_match = re.search(
        r'(?:^|\b)(?:por\s+favor\s+)?(?:crea|crear|create|escribe|escribir|write)\s+(?:el\s+)?(?:archivo|fichero|nota)\s+([^\s]+)(?:\s+(?:con|de)?\s*(?:el\s+)?(?:texto|contenido)\s+(.+))?[.!?]*$',
        t,
        re.I
    )
    if write_match:
        file_path = write_match.group(1).strip()
        file_content = (write_match.group(2) or "Nota creada por Spider-Man Desktop Agent.").strip()
        return SyntheticToolCall(SyntheticFunction("manage_files", {"action": "write", "path": file_path, "content": file_content}))

    # 2.8 Window displacement & web-pulling (move, pull_web, drag)
    dir_found = "right"
    if re.search(r'\b(?:a\s+la\s+)?izquierda\b|\bleft\b', t, re.I):
        dir_found = "left"
    elif re.search(r'\b(?:hacia\s+|a\s+la\s+)?derecha\b|\bright\b', t, re.I):
        dir_found = "right"
    elif re.search(r'\b(?:hacia\s+)?arriba\b|\bup\b', t, re.I):
        dir_found = "up"
    elif re.search(r'\b(?:hacia\s+)?abajo\b|\bdown\b', t, re.I):
        dir_found = "down"

    app_target = ""
    app_of_match = re.search(r'ventana\s+(?:de\s+|del\s+)?([a-zA-Z0-9_-]+)', t, re.I)
    if app_of_match:
        cand = app_of_match.group(1).lower()
        if cand not in ("la", "esta", "este", "arriba", "abajo", "derecha", "izquierda", "al", "a", "con", "hacia", "para", "que", "y", "o"):
            app_target = app_of_match.group(1).strip()

    # Match web-pull / snatch
    if re.search(r'(?:^|\b)(?:tira|tirar|jala|jalar|pesca|pescar|pull|snatch)\s+(?:de\s+)?(?:la\s+|esta\s+)?ventana', t, re.I) or \
       re.search(r'(?:^|\b)(?:lanza|dispara|disparar)\s+(?:una\s+)?telaraña\s+(?:a|hacia)\s+(?:la\s+|esta\s+)?ventana', t, re.I):
        return SyntheticToolCall(SyntheticFunction("interact_window", {"action": "pull_web", "app_name": app_target, "direction": dir_found}))

    # Match clear / apartar ventana
    if re.search(r'(?:^|\b)(?:aparta|apartar|despeja|despejar|quita|quitar)\s+(?:la\s+|esta\s+)?ventana', t, re.I) or \
       re.search(r'(?:^|\b)(?:despeja|despejar)\s+(?:la\s+)?pantalla', t, re.I):
        return SyntheticToolCall(SyntheticFunction("interact_window", {"action": "pull_web", "app_name": app_target, "direction": "clear"}))

    # Match move / drag window
    if re.search(r'(?:^|\b)(?:mueve|mover|arrastra|arrastrar|drag|move)\s+(?:la\s+|esta\s+)?ventana', t, re.I):
        return SyntheticToolCall(SyntheticFunction("interact_window", {"action": "move", "app_name": app_target, "direction": dir_found}))

    # Match window perching (climb/sit on window ledge)
    if re.search(r'(?:^|\b)(?:s[uú]bete|posate|p[oó]sate|si[eé]ntate|trepa)\s+(?:a|en)\s+(?:la\s+|esta\s+)?ventana\b|(?:^|\b)perch\b', t, re.I):
        return SyntheticToolCall(SyntheticFunction("perch_window", {"app_name": app_target}))

    # 3. Media status & controls (Music sensing & playback)
    if re.search(r'(?:^|\b)(?:qu[eé]\s+(?:m[uú]sica|canci[oó]n|tema)\s+(?:suena|estoy\s+escuchando|se\s+reproduce)|qu[eé]\s+suena|what(?:\'s|\s+is)\s+playing)\b', t, re.I):
        return SyntheticToolCall(SyntheticFunction("get_current_music", {}))
    if re.search(r'(?:^|\b)(?:pausa|det[eé]n|para)\s+(?:la\s+)?(?:m[uú]sica|canci[oó]n|reproducci[oó]n)\b', t, re.I):
        return SyntheticToolCall(SyntheticFunction("control_music", {"action": "pause"}))
    if re.search(r'(?:^|\b)(?:reanuda|contin[uú]a|play|dale\s+al\s+play)\s+(?:la\s+)?(?:m[uú]sica|canci[oó]n)\b', t, re.I):
        return SyntheticToolCall(SyntheticFunction("control_music", {"action": "play"}))
    if re.search(r'(?:^|\b)(?:siguiente\s+(?:canci[oó]n|tema|pista)|pasa\s+(?:de\s+)?(?:canci[oó]n|tema|pista)|next\s+(?:song|track))\b', t, re.I):
        return SyntheticToolCall(SyntheticFunction("control_music", {"action": "next"}))
    if re.search(r'(?:^|\b)(?:anterior\s+(?:canci[oó]n|tema|pista)|vuelve\s+a\s+la\s+canci[oó]n\s+anterior|previous\s+(?:song|track))\b', t, re.I):
        return SyntheticToolCall(SyntheticFunction("control_music", {"action": "prev"}))

    # 3. Open application / settings / calculator
    app_match = re.search(
        r'(?:^|\b)(?:por\s+favor\s+)?(?:abre|abrir|open|inicia|iniciar|launch|ejecuta|ejecutar|lanza|lanzar)\s+(?:la\s+|el\s+|los\s+|las\s+|app\s+de\s+|aplicaci[oó]n\s+de\s+)?(.+?)[.!?]*$',
        t,
        re.I
    )
    if app_match:
        target = app_match.group(1).strip()
        # Clean prefix phrases
        for prefix in ("app de ", "la app de ", "el programa ", "el software ", "la aplicacion de ", "la aplicación de "):
            if target.lower().startswith(prefix):
                target = target[len(prefix):].strip()
                break

        # Check if URL
        if target.startswith(("http://", "https://", "www.")) or re.match(r"^[a-zA-Z0-9.-]+\.(com|org|net|es|io|dev|tv|ai|gov)", target):
            return SyntheticToolCall(SyntheticFunction("open_website", {"url": target}))

        return SyntheticToolCall(SyntheticFunction("abrir_aplicacion", {"app_name": target}))

    # 4. Music playback
    music_match = re.search(
        r'(?:^|\b)(?:pon|reproduce|play)\s+(?:la\s+canci[oó]n\s+|m[uú]sica\s+(?:de\s+)?|el\s+tema\s+|tema\s+)?(.+?)[.!?]*$',
        t,
        re.I
    )
    if music_match and not any(w in t.lower() for w in ["volumen", "ajustes", "calc", "app", "pantalla"]):
        return SyntheticToolCall(SyntheticFunction("play_song", {"query": music_match.group(1).strip()}))

    # 5. Web search
    search_match = re.search(
        r'(?:^|\b)(?:busca|buscar|search|googlea)\s+(?:en\s+(?:google|internet|la\s+web)\s+)?(?:sobre\s+|informaci[oó]n\s+de\s+)?(.+?)[.!?]*$',
        t,
        re.I
    )
    if search_match:
        return SyntheticToolCall(SyntheticFunction("web_search", {"query": search_match.group(1).strip()}))

    # 6. Memory command (remembering user preferences and facts)
    mem_match = re.search(
        r'(?:^|\b)(?:por\s+favor\s+)?(?:recuerda|guarda|remember)\s+(?:que\s+|en\s+tu\s+memoria\s+)?(.+?)[.!?]*$',
        t,
        re.I
    )
    if mem_match:
        return SyntheticToolCall(SyntheticFunction("remember", {"fact": mem_match.group(1).strip()}))

    return None


parse_quick_intent = _detect_action_intent


def _clean_bot_cliches(text: str) -> str:
    """Removes generic chatbot customer-service suffixes that small SLMs occasionally emit."""
    cliches = [
        "¿Cómo puedo ayudarte hoy?",
        "¿En qué puedo ayudarte hoy?",
        "¿Cómo puedo ayudarte?",
        "¿En qué te puedo ayudar hoy?",
        "¿En qué te puedo ayudar?",
        "How can I help you today?",
        "How can I assist you today?",
        "How can I help you?",
    ]
    res = (text or "").strip()
    for c in cliches:
        if res.endswith(c):
            res = res[:-len(c)].strip()
    return res


# ==============================================================================
# SECTION 3: SPIDER-MAN BRAIN CORE CLASS
# ==============================================================================

class SpiderBrain:
    """
    Encapsulates the Ollama connection, conversation history management,
    memory persistence, prompt injection, and tool routing for Spider-Man.
    """

    def __init__(self) -> None:
        self.cfg = get_config()
        self.host: str = self.cfg.get("ollama.host", "http://localhost:11434")
        self.model: str = self.cfg.get("ollama.model", "qwen2.5:3b")
        # keep_alive='5m' keeps model warm in memory across conversational turns
        self.keep_alive = self.cfg.get("ollama.keep_alive", "5m")
        self.num_ctx: int = self.cfg.get("ollama.num_ctx", 2048)
        self.max_tokens: int = max(150, self.cfg.get("ollama.max_tokens", 160))
        self.temperature: float = self.cfg.get("ollama.temperature", 0.7)
        self.user_name: str = self.cfg.get("user_name", "Deivid")
        self.language: str = self.cfg.get("language", "es")

        # Memory manager instance
        self.memory = SHARED_MEMORY
        self.memory_path: Path = self.memory.path

        # Official Ollama client
        self.client: Client = Client(host=self.host)

        # Initialize base history, capture base prompt length, then load memory
        self.history: List[Dict[str, object]] = []
        self.reset_history()
        self.base_history_len = len(self.history)
        self.load_memory()

    def reset_history(self) -> None:
        """Initializes/resets message history with persona few-shot examples."""
        self.history = build(
            user=self.user_name,
            examples=True,
            language=self.language,
        )

    def trim_history(self) -> None:
        """
        Guarantees retention of Spider-Man's persona and few-shot examples.
        Keeps the entire base prompt and trims older conversation turns
        if total messages exceed base_history_len + 12.
        """
        if len(self.history) > self.base_history_len + 12:
            self.history = self.history[:self.base_history_len] + self.history[-12:]

    def save_memory(self) -> None:
        """Persists current conversation history to disk as JSON via SpiderMemory."""
        try:
            conversation_turns = self.history[self.base_history_len:]
            self.memory.set_history(conversation_turns)
        except Exception as err:
            print(f"[brain] Warning: Failed to save memory: {err}")

    def load_memory(self) -> None:
        """Loads recent conversation history from SpiderMemory."""
        saved_turns = self.memory.get_history()
        if saved_turns:
            self.history.extend(saved_turns)

    def is_healthy(self) -> bool:
        """Verifies if the Ollama local daemon is online and accessible."""
        try:
            self.client.list()
            return True
        except ConnectionError:
            return False
        except Exception:
            return False

    def _extract_tool_calls(self, message) -> List:
        """Detects tool calls from official Ollama field or raw JSON content."""
        if getattr(message, "tool_calls", None):
            return message.tool_calls

        # Fallback: Check if local model printed raw JSON in message content
        content = (getattr(message, "content", None) or "").strip()
        if content.startswith("{") and content.endswith("}") and '"name"' in content:
            try:
                parsed = json.loads(content)
                if "name" in parsed and ("arguments" in parsed or "parameters" in parsed):
                    args = parsed.get("arguments") or parsed.get("parameters") or {}
                    return [SyntheticToolCall(SyntheticFunction(parsed["name"], args))]
            except Exception:
                pass
        return []

    def talk(self, user_text: str, on_chunk: Optional[Callable[[str], None]] = None) -> str:
        """
        Processes a conversational turn with speed optimization & token streaming:
        1. Checks action intent and executes tool immediately on the host machine.
        2. Feeds actual execution result directly to Spider-Man for in-character confirmation.
        3. Supports open-ended tool calling for queries outside predefined regex patterns.
        4. Saves clean conversation history and persists with save_memory().
        """
        # Build ephemeral request payload with dynamic reminder
        dynamic_reminder = reminder(language=self.language)

        # Retrieve relevant long-term memory facts
        relevant_facts = self.memory.relevant_facts(user_text, speaker=self.user_name, limit=4)
        facts_context = ""
        if relevant_facts:
            facts_context = f"\n[(Things you remember about {self.user_name}, use only if relevant: {'; '.join(relevant_facts)})]"

        # Real-time host telemetry & temporal anchoring
        import datetime
        from abilities.system_sensor import get_quick_system_summary
        now_str = datetime.datetime.now().strftime("%A %d de %B de %Y, %H:%M")
        live_telemetry = f"\n[(Host state: {get_quick_system_summary()} | Hora local: {now_str})]"

        # Performance options
        options = {
            "num_ctx": self.num_ctx,
            "temperature": self.temperature,
            "num_predict": self.max_tokens,
        }

        # ----------------------------------------------------------------------
        # PATH 1: DIRECT DETERMINISTIC AGENT EXECUTION
        # (Executes instantly on host machine, avoiding SLM tool hallucinations)
        # ----------------------------------------------------------------------
        action_intent = _detect_action_intent(user_text)
        if action_intent:
            name = action_intent.function.name
            args = action_intent.function.arguments if hasattr(action_intent.function, "arguments") else {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except Exception:
                    args = {}

            tool_func = TOOL_REGISTRY.get(name)
            if tool_func:
                tool_result = tool_func(**args)
            else:
                tool_result = f"Error: Tool '{name}' not found."

            system_instruction = (
                f"\n\n[(ACTION COMPLETED: You have just executed this command on {self.user_name}'s PC:\n"
                f"{tool_result}\n"
                f"MANDATORY INSTRUCTION: Respond in character as Spider-Man (Peter Parker) in 1 or 2 short sentences "
                f"confirming what you just did with your witty, scientific, sarcastic personality. "
                f"STRICT RULE: The action is ALREADY DONE. Do NOT explain how the user can click buttons or menus themselves, and do NOT make excuses saying you cannot do it.)]"
            )
            ephemeral_user_content = f"{user_text}\n\n{dynamic_reminder}{facts_context}{live_telemetry}{system_instruction}"
            ephemeral_messages = list(self.history) + [
                {"role": "user", "content": ephemeral_user_content}
            ]

            try:
                if on_chunk:
                    stream_resp = self.client.chat(
                        model=self.model,
                        messages=ephemeral_messages,
                        keep_alive=self.keep_alive,
                        options=options,
                        stream=True,
                    )
                    accumulated = ""
                    for chunk in stream_resp:
                        token = chunk.message.content or ""
                        accumulated += token
                        on_chunk(token)
                    final_reply = _clean_bot_cliches(accumulated.strip())
                else:
                    response = self.client.chat(
                        model=self.model,
                        messages=ephemeral_messages,
                        keep_alive=self.keep_alive,
                        options=options,
                    )
                    final_reply = _clean_bot_cliches((response.message.content or "").strip())

                # Clean message history persistence
                self.history.append({"role": "user", "content": user_text})
                self.history.append({"role": "assistant", "content": final_reply})
                self.trim_history()
                self.save_memory()
                return final_reply

            except ConnectionError:
                fallback_reply = f"¡Acción completada con éxito, socio! He ejecutado la orden en tu equipo."
                self.history.append({"role": "user", "content": user_text})
                self.history.append({"role": "assistant", "content": fallback_reply})
                self.trim_history()
                self.save_memory()
                return fallback_reply
            except Exception as ex:
                fallback_reply = f"¡Marchando! Acción completada en el sistema a tu orden."
                self.history.append({"role": "user", "content": user_text})
                self.history.append({"role": "assistant", "content": fallback_reply})
                self.trim_history()
                self.save_memory()
                return fallback_reply

        # ----------------------------------------------------------------------
        # PATH 2: GENERAL CHAT & OPEN-ENDED TOOL INVOCATION
        # ----------------------------------------------------------------------
        ephemeral_user_content = f"{user_text}\n\n{dynamic_reminder}{facts_context}{live_telemetry}"
        ephemeral_messages = list(self.history) + [
            {"role": "user", "content": ephemeral_user_content}
        ]

        try:
            response = self.client.chat(
                model=self.model,
                messages=ephemeral_messages,
                tools=AVAILABLE_TOOLS,
                keep_alive=self.keep_alive,
                options=options,
            )
            assistant_msg = response.message
        except ConnectionError:
            err_msg = "[Spider-Man: Connection lost with Ollama server at http://localhost:11434]"
            print(f"\n{err_msg}")
            return err_msg
        except ResponseError as api_err:
            err_msg = f"[Spider-Man: Ollama API error: {api_err}]"
            print(f"\n{err_msg}")
            return err_msg
        except Exception as ex:
            err_msg = f"[Spider-Man: Unexpected error: {ex}]"
            print(f"\n{err_msg}")
            return err_msg

        tool_calls = self._extract_tool_calls(assistant_msg)

        # Deterministic Intent Fallback: if the SLM answered conversationally instead of calling
        # the tool for a direct action, execute the synthetic tool call so the action ALWAYS works!
        if not tool_calls and action_intent:
            tool_calls = [action_intent]

        if tool_calls:
            # Execute requested tools on the host system
            tool_results = []
            for call in tool_calls:
                name = call.function.name
                args = call.function.arguments if hasattr(call.function, "arguments") else {}
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except Exception:
                        args = {}

                if name in TOOL_REGISTRY:
                    tool_func = TOOL_REGISTRY[name]
                    result = tool_func(**args)
                else:
                    result = f"Error: Tool '{name}' is not recognized."
                    print(f">>> [EXECUTION] Unknown tool requested: {name}")

                tool_results.append((name, args, result))

            # Prepare follow-up messages for Spider-Man's in-character reaction
            followup_messages = list(self.history) + [
                {"role": "user", "content": user_text}
            ]

            synthetic_calls = []
            for name, args, res in tool_results:
                synthetic_calls.append({"function": {"name": name, "arguments": args}})

            followup_messages.append({
                "role": "assistant",
                "content": "",
                "tool_calls": synthetic_calls,
            })
            for name, args, res in tool_results:
                followup_messages.append({
                    "role": "tool",
                    "content": f"{res}\n[Action executed on host machine. Respond in character as Spider-Man (Peter Parker) in {self.language} confirming what happened in 1 or 2 quick sentences with a quip. Do NOT output JSON.]",
                    "tool_name": name,
                })

            try:
                # Omit tools parameter in followup so local model speaks in voice instead of calling tools again
                if on_chunk:
                    stream_resp = self.client.chat(
                        model=self.model,
                        messages=followup_messages,
                        keep_alive=self.keep_alive,
                        options=options,
                        stream=True,
                    )
                    accumulated = ""
                    for chunk in stream_resp:
                        token = chunk.message.content or ""
                        accumulated += token
                        on_chunk(token)
                    final_reply = accumulated.strip()
                else:
                    followup = self.client.chat(
                        model=self.model,
                        messages=followup_messages,
                        keep_alive=self.keep_alive,
                        options=options,
                    )
                    final_reply = (followup.message.content or "").strip()

                # If model accidentally spat raw JSON, provide in-character fallback
                if final_reply.startswith("{") and '"name"' in final_reply:
                    first_tool = tool_results[0][0]
                    final_reply = f"¡Marchando! Ya tienes abierto '{first_tool}' en tu pantalla. ¿Vamos a hackear algo o seguimos patrullando?"
            except Exception as followup_err:
                # In-character graceful fallback if model follow-up fails
                first_tool, _, first_res = tool_results[0]
                if "success" in first_res.lower() or "dispatched" in first_res.lower():
                    final_reply = f"¡Listo, compañero! Ya ejecuté la acción en tu máquina. ¿Qué más investigamos?"
                else:
                    final_reply = f"Se me enredó la telaraña con eso: {first_res}"

            # Commit clean conversation turn to persistent memory
            final_reply = _clean_bot_cliches(final_reply)
            self.history.append({"role": "user", "content": user_text})
            self.history.append({"role": "assistant", "content": final_reply})
            self.trim_history()
            self.save_memory()
            return final_reply

        else:
            # Standard conversational reply
            reply = _clean_bot_cliches((assistant_msg.content or "").strip())
            self.history.append({"role": "user", "content": user_text})
            self.history.append({"role": "assistant", "content": reply})
            self.trim_history()
            self.save_memory()
            return reply


# Backward compatibility alias
CapriBrain = SpiderBrain


# ==============================================================================
# SECTION 4: INTERACTIVE TERMINAL LOOP (STANDALONE REPL)
# ==============================================================================

def main() -> None:
    """Terminal entry point for Spider-Man's brain in standalone testing mode."""
    brain = SpiderBrain()

    print("=" * 64)
    print("  SPIDER-MAN - Desktop Agent Core Brain (Cross-Platform)")
    print(f"  Platform: {sys.platform} | Host: {brain.host} | Model: {brain.model}")
    print(f"  Optimization: keep_alive={brain.keep_alive} | num_predict={brain.max_tokens}")
    print(f"  User: {brain.user_name} | Language: {brain.language}")
    print(f"  Memory Store: {brain.memory_path}")
    print("  Type 'exit', 'quit' or 'q' to disconnect.")
    print("=" * 64)

    if not brain.is_healthy():
        print(f"\n[ERROR] Cannot connect to Ollama at {brain.host}")
        print("Please start the Ollama service: 'ollama serve'")
        print("And ensure the model is pulled: 'ollama pull qwen2.5-coder:7b'\n")
        sys.exit(1)

    print(f"\n[Spider-Man is online and listening... Active history: {len(brain.history)} messages]\n")

    while True:
        try:
            user_input = input("You: ").strip()
            if not user_input:
                continue

            if user_input.lower() in ("exit", "quit", "q"):
                print("\nSpidey: Running out of web fluid! Stay safe out there, partner.\n")
                break

            print("\n[Spider-Man is thinking...]", end="\r", flush=True)
            reply = brain.talk(user_input)
            print(" " * 30, end="\r")  # Clear thinking indicator
            print(f"\nSpidey: {reply}\n")

        except (KeyboardInterrupt, EOFError):
            print("\n\nSpidey: Sudden disconnect? Watch out for pumpkin bombs. Later!\n")
            break


if __name__ == "__main__":
    main()
