"""
Universal Application & Browser Discovery Engine for Windows and Linux.
Resolves applications beyond system PATH using Windows Registry App Paths,
local AppData, Program Files, and desktop environments.
"""
from __future__ import annotations

import os
import sys
import shutil
import glob
from pathlib import Path
from typing import Optional, List, Tuple


# Known web platforms that should open as direct URLs instead of looking for local binaries
KNOWN_WEB_SERVICES = {
    "youtube": "https://www.youtube.com",
    "spotify_web": "https://open.spotify.com",
    "github": "https://github.com",
    "reddit": "https://www.reddit.com",
    "twitch": "https://www.twitch.tv",
    "twitter": "https://x.com",
    "x": "https://x.com",
    "chatgpt": "https://chat.openai.com",
    "gmail": "https://mail.google.com",
    "whatsapp": "https://web.whatsapp.com",
    "netflix": "https://www.netflix.com",
    "wikipedia": "https://es.wikipedia.org",
    "google": "https://www.google.com",
    "duckduckgo": "https://duckduckgo.com",
}


def get_windows_registry_app_path(exe_name: str) -> Optional[str]:
    """Queries Windows Registry App Paths for registered application binaries."""
    if sys.platform != "win32":
        return None
    try:
        import winreg
        for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            key_path = f"SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\App Paths\\{exe_name}"
            try:
                with winreg.OpenKey(root, key_path) as k:
                    val, _ = winreg.QueryValueEx(k, "")
                    if val and os.path.exists(val):
                        return val
            except Exception:
                pass
    except Exception:
        pass
    return None


def find_browser_executable(browser_name: str = "brave") -> Optional[str]:
    """
    Locates the executable path for a specific browser (Brave, Chrome, Edge, Firefox).
    Returns absolute path or None.
    """
    b_name = (browser_name or "").strip().lower()
    if not b_name:
        return None

    if sys.platform == "win32":
        # 1. Check registry App Paths
        exe_variants = {
            "brave": ["brave.exe"],
            "chrome": ["chrome.exe"],
            "edge": ["msedge.exe"],
            "firefox": ["firefox.exe"],
            "opera": ["opera.exe"],
        }.get(b_name, [f"{b_name}.exe"])

        for exe in exe_variants:
            reg_path = get_windows_registry_app_path(exe)
            if reg_path:
                return reg_path

        # 2. Check standard Windows installation directories
        search_dirs = [
            os.environ.get("ProgramFiles", r"C:\Program Files"),
            os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
            os.environ.get("LOCALAPPDATA", r"C:\Users\Default\AppData\Local"),
        ]

        known_locations = {
            "brave": [
                r"BraveSoftware\Brave-Browser\Application\brave.exe",
            ],
            "chrome": [
                r"Google\Chrome\Application\chrome.exe",
            ],
            "edge": [
                r"Microsoft\Edge\Application\msedge.exe",
            ],
            "firefox": [
                r"Mozilla Firefox\firefox.exe",
            ],
        }

        for rel in known_locations.get(b_name, []):
            for base in search_dirs:
                full_path = os.path.join(base, rel)
                if os.path.exists(full_path):
                    return full_path

        # 3. PATH fallback
        for exe in exe_variants:
            found = shutil.which(exe)
            if found:
                return found

    elif sys.platform.startswith("linux"):
        linux_cmds = {
            "brave": ["brave-browser", "brave"],
            "chrome": ["google-chrome", "chromium", "chromium-browser"],
            "edge": ["microsoft-edge"],
            "firefox": ["firefox"],
        }.get(b_name, [b_name])

        for cmd in linux_cmds:
            found = shutil.which(cmd)
            if found:
                return found

    return None


def resolve_application_command(app_name: str) -> Optional[Tuple[List[str], str]]:
    """
    Resolves application launch command and friendly title.
    Returns ([command_args], display_name) or None.
    """
    clean = (app_name or "").strip()
    if not clean:
        return None

    low = clean.lower()

    # 1. Windows specialized resolvers
    if sys.platform == "win32":
        # Brave
        if "brave" in low:
            p = find_browser_executable("brave")
            if p:
                return [p], "Brave Browser"

        # Discord
        if "discord" in low:
            local = os.environ.get("LOCALAPPDATA", "")
            if local:
                update_exe = os.path.join(local, "Discord", "Update.exe")
                if os.path.exists(update_exe):
                    return [update_exe, "--processStart", "Discord.exe"], "Discord"
                app_dirs = glob.glob(os.path.join(local, "Discord", "app-*", "Discord.exe"))
                if app_dirs and os.path.exists(app_dirs[-1]):
                    return [app_dirs[-1]], "Discord"
            # Protocol fallback
            return ["cmd.exe", "/c", "start", "", "discord:"], "Discord"

        # Spotify
        if "spotify" in low:
            # Check WindowsApps or AppData
            local = os.environ.get("LOCALAPPDATA", "")
            winapp_spot = os.path.join(local, "Microsoft", "WindowsApps", "Spotify.exe")
            if os.path.exists(winapp_spot):
                return [winapp_spot], "Spotify"
            roaming = os.environ.get("APPDATA", "")
            spot_exe = os.path.join(roaming, "Spotify", "Spotify.exe")
            if os.path.exists(spot_exe):
                return [spot_exe], "Spotify"
            # Protocol fallback (instant native Windows Spotify launch)
            return ["cmd.exe", "/c", "start", "", "spotify:"], "Spotify"

        # Visual Studio Code
        if any(k in low for k in ("visual studio code", "vs code", "vscode", "code")):
            reg_code = get_windows_registry_app_path("code.exe")
            if reg_code:
                return [reg_code], "Visual Studio Code"
            local = os.environ.get("LOCALAPPDATA", "")
            code_exe = os.path.join(local, "Programs", "Microsoft VS Code", "Code.exe")
            if os.path.exists(code_exe):
                return [code_exe], "Visual Studio Code"

        # Chrome
        if "chrome" in low:
            p = find_browser_executable("chrome")
            if p:
                return [p], "Google Chrome"

        # Edge
        if "edge" in low:
            p = find_browser_executable("edge")
            if p:
                return [p], "Microsoft Edge"

        # Try Windows Registry App Paths for any requested executable
        reg_check = get_windows_registry_app_path(f"{clean}.exe" if not clean.endswith(".exe") else clean)
        if reg_check:
            return [reg_check], clean.capitalize()

    # Generic PATH lookup
    found_bin = shutil.which(clean) or shutil.which(f"{clean}.exe")
    if found_bin:
        return [found_bin], clean.capitalize()

    return None
