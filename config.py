"""
config.py - Lightweight Configuration Manager for Spider-Man Desktop Agent

Clean JSON-based configuration manager strictly tuned for local Ollama execution
and a PySide6 transparent desktop overlay.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Dict


# ==============================================================================
# BASE PATHS & CONSTANTS
# ==============================================================================
APP_NAME: str = "Spider-Man Desktop Agent"
BASE_DIR: Path = Path(__file__).resolve().parent
DATA_DIR: Path = BASE_DIR / "data"
CONFIG_FILE: Path = DATA_DIR / "config.json"
ASSETS_DIR: Path = BASE_DIR / "assets"


# ==============================================================================
# DEFAULT ARCHITECTURAL CONFIGURATION
# ==============================================================================
DEFAULT_CONFIG: Dict[str, Any] = {
    "user_name": "Deivid",
    "language": "es",
    
    # Strictly Ollama local settings (optimized for speed and low VRAM)
    "ollama": {
        "host": "http://localhost:11434",
        "model": "qwen2.5-coder:7b", # Leading coding SLM (<5GB VRAM, highly accurate)
        "keep_alive": "2m",          # Auto-unloads from VRAM after 2m idle, freeing GPU for OS
        "num_ctx": 2048,             # Restricts context to avoid OOM
        "temperature": 0.7,
        "max_tokens": 160,           # Fast response generation
    },
    
    # UI / PySide6 Window Configuration
    "desk": {
        "size": 180,                 # Sprite height in pixels
        "roam_seconds": [45, 95],    # Range of seconds before moving across the screen
        "fps": 30,                   # Animation frame rate
        "always_on_top": True,
        "sound_enabled": True,
        "bubble_timeout_seconds": 8, # Speech bubble lifespan
    },
    
    # Active Tools Sandbox Configuration
    "tools": {
        "sandbox_mode": False,       # Real desktop execution enabled
    }
}


def _deep_merge(base: Dict[str, Any], extra: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively merges user configuration over default values."""
    merged = copy.deepcopy(base)
    for key, value in (extra or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


class ConfigManager:
    """Ultralight JSON configuration manager with fallback to defaults."""

    def __init__(self, config_path: Path = CONFIG_FILE):
        self.config_path = config_path
        self._data: Dict[str, Any] = {}
        self.reload()

    def reload(self) -> Dict[str, Any]:
        """Loads configuration from JSON file or initializes defaults."""
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    user_data = json.load(f)
                self._data = _deep_merge(DEFAULT_CONFIG, user_data)
            except Exception as err:
                print(f"[config] Warning: Failed to read {self.config_path} ({err}). Using defaults.")
                self._data = copy.deepcopy(DEFAULT_CONFIG)
        else:
            self._data = copy.deepcopy(DEFAULT_CONFIG)
            self.save()
            
        return self._data

    def save(self) -> None:
        """Persists current configuration to disk as pretty JSON."""
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=4, ensure_ascii=False)
        except Exception as err:
            print(f"[config] Error: Could not write configuration file: {err}")

    def get(self, key: str, default: Any = None) -> Any:
        """Retrieve top-level or dot-separated configuration value (e.g. 'ollama.model')."""
        if "." in key:
            parts = key.split(".")
            curr = self._data
            for part in parts:
                if isinstance(curr, dict) and part in curr:
                    curr = curr[part]
                else:
                    return default
            return curr
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Set a configuration value and save to disk."""
        if "." in key:
            parts = key.split(".")
            curr = self._data
            for part in parts[:-1]:
                curr = curr.setdefault(part, {})
            curr[parts[-1]] = value
        else:
            self._data[key] = value
        self.save()

    @property
    def data(self) -> Dict[str, Any]:
        """Direct access to the underlying configuration dictionary."""
        return self._data


# Global configuration instance
config = ConfigManager()


def get_config() -> ConfigManager:
    """Helper to access the active configuration instance."""
    return config
