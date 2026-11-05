"""
Custom Commands (Macros) Persistence & Execution Engine.
Stores named multi-step commands in data/commands.json and provides matching,
management, and execution interfaces for Spider-Man / Capri.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
COMMANDS_FILE = DATA_DIR / "commands.json"


def _normalize_name(name: str) -> str:
    """Normalizes command name for robust case-insensitive lookup."""
    return re.sub(r"\s+", " ", (name or "").strip().lower())


def _parse_actions_string(actions_input: str | list[str]) -> list[str]:
    """
    Parses actions from a string or list.
    Supports comma separation, newline separation, or conversational 'y' / 'and'.
    Example: "abre discord y abre spotify" -> ["abre discord", "abre spotify"]
    """
    if isinstance(actions_input, list):
        return [a.strip() for a in actions_input if a.strip()]

    raw = (actions_input or "").strip()
    if not raw:
        return []

    # If newlines or commas are present, split by them
    if "\n" in raw:
        items = raw.split("\n")
    elif ";" in raw:
        items = raw.split(";")
    elif "," in raw:
        items = raw.split(",")
    elif " y " in raw.lower():
        items = re.split(r"\s+y\s+", raw, flags=re.I)
    elif " and " in raw.lower():
        items = re.split(r"\s+and\s+", raw, flags=re.I)
    else:
        items = [raw]

    clean_items = []
    for item in items:
        c = item.strip(" .!?")
        if c:
            clean_items.append(c)
    return clean_items


def get_default_commands() -> dict[str, dict]:
    """Returns factory default commands if commands.json does not exist."""
    return {
        "modo juego": {
            "name": "modo juego",
            "description": "Prepara el setup para jugar abriendo Discord y Spotify.",
            "actions": ["abre discord", "abre spotify"],
            "created_at": time.time(),
        },
        "modo trabajo": {
            "name": "modo trabajo",
            "description": "Abre el navegador web y Visual Studio Code para programar.",
            "actions": ["abre el navegador", "abre visual studio code"],
            "created_at": time.time(),
        },
        "modo relax": {
            "name": "modo relax",
            "description": "Ajusta el volumen suavemente y busca música tranquila.",
            "actions": ["pon el volumen al 30", "pon lofi hip hop en youtube"],
            "created_at": time.time(),
        },
    }


def load_commands() -> dict[str, dict]:
    """Loads all saved custom commands from data/commands.json."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not COMMANDS_FILE.exists():
        defaults = get_default_commands()
        save_all_commands(defaults)
        return defaults

    try:
        with open(COMMANDS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                for k, v in list(data.items()):
                    if isinstance(v, dict):
                        acts = v.get("actions", [])
                        if isinstance(acts, str):
                            v["actions"] = _parse_actions_string(acts)
                        elif isinstance(acts, list):
                            v["actions"] = [str(a).strip() for a in acts if str(a).strip()]
                return data
    except Exception as err:
        print(f"[custom_commands] Error loading {COMMANDS_FILE}: {err}")

    return {}


def save_all_commands(commands: dict[str, dict]) -> bool:
    """Writes the full commands dictionary to disk."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with open(COMMANDS_FILE, "w", encoding="utf-8") as f:
            json.dump(commands, f, indent=2, ensure_ascii=False)
        return True
    except Exception as err:
        print(f"[custom_commands] Error saving {COMMANDS_FILE}: {err}")
        return False


def save_command(name: str, actions: list[str] | str, description: str = "") -> dict | None:
    """
    Creates or updates a persistent custom command.

    Args:
        name: Command identifier (e.g. "modo juego").
        actions: List of actions or action string (e.g. "abre discord y abre spotify").
        description: Optional helpful note.

    Returns:
        dict: The created command record or None on failure.
    """
    clean_name = _normalize_name(name)
    if not clean_name:
        return None

    action_list = _parse_actions_string(actions)
    if not action_list:
        return None

    commands = load_commands()
    cmd_data = {
        "name": clean_name,
        "description": description.strip() or f"Ejecuta: {', '.join(action_list)}",
        "actions": action_list,
        "created_at": time.time(),
    }
    commands[clean_name] = cmd_data
    if save_all_commands(commands):
        return cmd_data
    return None


def delete_command(name: str) -> bool:
    """Removes a custom command permanently from disk."""
    clean_name = _normalize_name(name)
    commands = load_commands()
    if clean_name in commands:
        del commands[clean_name]
        return save_all_commands(commands)
    return False


def get_command(name: str) -> dict | None:
    """Retrieves a single command by name."""
    clean_name = _normalize_name(name)
    commands = load_commands()
    return commands.get(clean_name)


def list_commands() -> list[dict]:
    """Returns a list of all commands sorted by name."""
    commands = load_commands()
    return sorted(commands.values(), key=lambda c: c["name"])


def find_matching_command(user_text: str) -> dict | None:
    """
    Checks if conversational input directly invokes any registered custom command.
    Matches variations like:
      - "modo juego"
      - "activa el modo juego"
      - "activar modo juego"
      - "pon el modo juego"
      - "ejecuta la comanda modo juego"
      - "comanda modo juego"
    """
    clean = _normalize_name(user_text)
    if not clean:
        return None

    commands = load_commands()
    if not commands:
        return None

    # 1. Exact match
    if clean in commands:
        return commands[clean]

    # 2. Stripped prefix matching
    prefixes = [
        "ejecuta la comanda ",
        "ejecutar la comanda ",
        "ejecuta la macro ",
        "ejecuta ",
        "ejecutar ",
        "activa la comanda ",
        "activar la comanda ",
        "activa el ",
        "activar el ",
        "activa la ",
        "activar la ",
        "activa ",
        "activar ",
        "pon el ",
        "pon la ",
        "pon ",
        "inicia la comanda ",
        "inicia el ",
        "iniciar el ",
        "inicia ",
        "iniciar ",
        "comanda ",
        "macro ",
    ]

    for prefix in prefixes:
        if clean.startswith(prefix):
            candidate = clean[len(prefix):].strip(" .!?")
            if candidate in commands:
                return commands[candidate]

    # 3. Check if any command name is fully contained in user text
    for cmd_name, cmd_data in commands.items():
        # Word boundary pattern match
        pattern = r"\b" + re.escape(cmd_name) + r"\b"
        if re.search(pattern, clean, re.I):
            return cmd_data

    return None
