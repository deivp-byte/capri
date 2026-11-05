"""
abilities/media_sensor.py - Real-Time Media Sensing & Hardware Playback Control

Cross-platform media detection and transport control for Capri / Spider-Man Desktop.
Supports:
1. Windows:
   - Window title inspection for Spotify, YouTube (Chrome, Brave, Edge, Firefox),
     SoundCloud, VLC, and Windows Media Player.
   - Global hardware media key simulation via Win32 keybd_event (VK_MEDIA_PLAY_PAUSE,
     VK_MEDIA_NEXT_TRACK, VK_MEDIA_PREV_TRACK, VK_MEDIA_STOP) requiring zero external DLLs.
2. Linux:
   - MPRIS D-Bus interface integration via playerctl (metadata & playback control).
"""

from __future__ import annotations

import ctypes
import os
import re
import shutil
import subprocess
import sys
from typing import Any, Dict, Optional


# ==============================================================================
# WIN32 VIRTUAL KEY CODES FOR GLOBAL MEDIA TRANSPORT
# ==============================================================================
VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_STOP = 0xB2
VK_MEDIA_PLAY_PAUSE = 0xB3
KEYEVENTF_KEYUP = 0x0002


def _send_win32_media_key(vk_code: int) -> bool:
    """Dispatches a global Win32 media key event."""
    try:
        user32 = ctypes.windll.user32
        user32.keybd_event(vk_code, 0, 0, 0)
        user32.keybd_event(vk_code, 0, KEYEVENTF_KEYUP, 0)
        return True
    except Exception:
        return False


def _get_input_desktop_handle():
    """Ensures access to the interactive desktop station on Windows."""
    try:
        user32 = ctypes.windll.user32
        input_desk = user32.OpenInputDesktop(0, False, 0x01FF)
        if input_desk:
            user32.SetThreadDesktop(input_desk)
        return input_desk
    except Exception:
        return None


def get_now_playing() -> Dict[str, Any]:
    """
    Detects what media or music is currently playing on the user's PC.

    Returns:
        dict: {
            "playing": bool,
            "title": str,
            "artist": str,
            "source": str,
            "raw_title": str
        }
    """
    result = {
        "playing": False,
        "title": "",
        "artist": "",
        "source": "",
        "raw_title": "",
    }

    # --------------------------------------------------------------------------
    # 1. WINDOWS MEDIA SENSING VIA NATIVE WINDOW ENUMERATION
    # --------------------------------------------------------------------------
    if sys.platform == "win32":
        try:
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            _get_input_desktop_handle()

            found_media: list[dict] = []

            def _enum_media_cb(hwnd, _):
                if not user32.IsWindowVisible(hwnd):
                    return True
                length = user32.GetWindowTextLengthW(hwnd)
                if length == 0:
                    return True

                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                title = buf.value.strip()

                cls_buf = ctypes.create_unicode_buffer(256)
                user32.GetClassNameW(hwnd, cls_buf, 256)
                cls_name = cls_buf.value

                title_lower = title.lower()

                # A. Spotify Desktop App
                # When playing: title is "Artist - Song Title"
                # When paused/idle: title is "Spotify Free", "Spotify Premium", or "Spotify"
                if "spotify" in cls_name.lower() or "spotify" in title_lower:
                    if title and not re.match(r"^spotify(?:\s+(?:free|premium))?$", title, re.IGNORECASE):
                        if " - " in title:
                            parts = title.split(" - ", 1)
                            found_media.append({
                                "playing": True,
                                "artist": parts[0].strip(),
                                "title": parts[1].strip(),
                                "source": "Spotify",
                                "raw_title": title,
                                "priority": 10,
                            })
                        else:
                            found_media.append({
                                "playing": True,
                                "artist": "",
                                "title": title,
                                "source": "Spotify",
                                "raw_title": title,
                                "priority": 8,
                            })

                # B. YouTube / Music in Browsers (Chrome, Brave, Edge, Firefox)
                elif " - youtube" in title_lower or "youtube music" in title_lower:
                    clean = title
                    # Remove browser suffixes
                    for b_suffix in (" - google chrome", " - brave", " - personal: brave", " - microsoft edge", " - mozilla firefox"):
                        if clean.lower().endswith(b_suffix):
                            clean = clean[:-len(b_suffix)].strip()
                    # Remove YouTube suffix
                    clean = re.sub(r"\s*-\s*youtube(?:\s+music)?\s*$", "", clean, flags=re.IGNORECASE).strip()
                    if clean:
                        artist = ""
                        track = clean
                        if " - " in clean:
                            parts = clean.split(" - ", 1)
                            artist = parts[0].strip()
                            track = parts[1].strip()
                        found_media.append({
                            "playing": True,
                            "artist": artist,
                            "title": track,
                            "source": "YouTube",
                            "raw_title": title,
                            "priority": 7,
                        })

                # C. SoundCloud / Other Web Players
                elif "soundcloud" in title_lower:
                    clean = re.sub(r"\s*\|\s*soundcloud.*$", "", title, flags=re.IGNORECASE).strip()
                    found_media.append({
                        "playing": True,
                        "artist": "",
                        "title": clean or "SoundCloud Stream",
                        "source": "SoundCloud",
                        "raw_title": title,
                        "priority": 6,
                    })

                # D. VLC Media Player
                elif "vlc media player" in title_lower:
                    clean = re.sub(r"\s*-\s*vlc media player$", "", title, flags=re.IGNORECASE).strip()
                    found_media.append({
                        "playing": True,
                        "artist": "",
                        "title": clean or "VLC Media",
                        "source": "VLC",
                        "raw_title": title,
                        "priority": 5,
                    })

                return True

            WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
            user32.EnumWindows(WNDENUMPROC(_enum_media_cb), 0)

            if found_media:
                # Return highest priority media match
                found_media.sort(key=lambda m: m["priority"], reverse=True)
                top = found_media[0]
                result["playing"] = True
                result["title"] = top["title"]
                result["artist"] = top["artist"]
                result["source"] = top["source"]
                result["raw_title"] = top["raw_title"]
                return result
        except Exception:
            pass

    # --------------------------------------------------------------------------
    # 2. LINUX MPRIS D-BUS SENSING VIA PLAYERCTL
    # --------------------------------------------------------------------------
    elif shutil.which("playerctl"):
        try:
            status_proc = subprocess.run(
                ["playerctl", "status"],
                capture_output=True,
                text=True,
                check=False,
                timeout=1.5,
            )
            status = status_proc.stdout.strip().lower()
            if status in ("playing", "paused"):
                result["playing"] = (status == "playing")

                title_proc = subprocess.run(
                    ["playerctl", "metadata", "title"],
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=1.5,
                )
                artist_proc = subprocess.run(
                    ["playerctl", "metadata", "artist"],
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=1.5,
                )
                player_proc = subprocess.run(
                    ["playerctl", "metadata", "mpris:trackid"],
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=1.5,
                )

                result["title"] = title_proc.stdout.strip()
                result["artist"] = artist_proc.stdout.strip()
                result["source"] = "MPRIS"
                result["raw_title"] = f"{result['artist']} - {result['title']}".strip(" - ")
                return result
        except Exception:
            pass

    return result


def control_media(action: str = "toggle") -> str:
    """
    Controls desktop media playback (play/pause, next track, prev track, stop).

    Args:
        action: 'play_pause', 'toggle', 'play', 'pause', 'next', 'prev', 'previous', 'stop'.

    Returns:
        str: Descriptive status of the action taken.
    """
    act = action.strip().lower()

    if sys.platform == "win32":
        if act in ("toggle", "play_pause", "play", "pause"):
            ok = _send_win32_media_key(VK_MEDIA_PLAY_PAUSE)
            return "Status: Alternada reproducción/pausa multimedia en Windows." if ok else "Status: Error al enviar comando multimedia."
        elif act in ("next", "next_track", "siguiente"):
            ok = _send_win32_media_key(VK_MEDIA_NEXT_TRACK)
            return "Status: Saltando a la siguiente pista de música." if ok else "Status: Error al pasar de pista."
        elif act in ("prev", "previous", "anterior"):
            ok = _send_win32_media_key(VK_MEDIA_PREV_TRACK)
            return "Status: Volviendo a la pista anterior de música." if ok else "Status: Error al retroceder pista."
        elif act in ("stop", "detener", "parar"):
            ok = _send_win32_media_key(VK_MEDIA_STOP)
            return "Status: Reproducción multimedia detenida." if ok else "Status: Error al detener multimedia."
        else:
            return f"Status: Acción multimedia '{action}' no reconocida (usa play_pause, next, prev o stop)."

    # Linux playerctl fallback
    if shutil.which("playerctl"):
        cmd = ["playerctl"]
        if act in ("toggle", "play_pause"):
            cmd.append("play-pause")
        elif act == "play":
            cmd.append("play")
        elif act == "pause":
            cmd.append("pause")
        elif act in ("next", "siguiente"):
            cmd.append("next")
        elif act in ("prev", "previous", "anterior"):
            cmd.append("previous")
        elif act in ("stop", "detener"):
            cmd.append("stop")
        else:
            return f"Status: Acción multimedia '{action}' desconocida."

        try:
            subprocess.run(cmd, check=False, timeout=2.0)
            return f"Status: Comando multimedia '{act}' enviado vía playerctl."
        except Exception as err:
            return f"Status: Error ejecutando playerctl ({err})."

    return "Status: Control multimedia no disponible en este entorno."
