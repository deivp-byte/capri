"""
abilities/pattern_learning.py - Adaptive Pattern & Preference Learning for Capri

Enables Capri to learn and remember:
1. Project locations & path aliases (e.g. "mi proyecto" -> "C:/Archivos/Personal_Projects/capri").
2. Developer coding preferences & conventions (e.g. "prefiere PySide6 sobre PyQt", "tipado estricto").
3. Learned command aliases & user corrections (e.g. "cuando diga X, haz Y").
4. Habitual workflow patterns and action usage frequencies.

Persists data locally in data/patterns.json.
Zero external heavy dependencies, fully deterministic and fast.
"""

from __future__ import annotations

import difflib
import json
import re
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from config import DATA_DIR, BASE_DIR

PATTERNS_FILE = DATA_DIR / "patterns.json"


class PatternLearner:
    """
    Manages persistent adaptive patterns, project aliases, and developer habits.
    Thread-safe and low-resource.
    """

    def __init__(self, storage_path: Optional[Path] = None) -> None:
        self.path = storage_path or PATTERNS_FILE
        self.lock = threading.RLock()
        self.data: Dict[str, Any] = {
            "projects": {},        # alias -> path (e.g. "capri": "C:/Archivos/Personal_Projects/capri")
            "preferences": {},     # category -> details (e.g. "coding_style": "Python 3.10+, Type hints, Clean Code")
            "learned_rules": {},   # trigger phrase -> action dict
            "code_snippets": {},   # pattern_name -> {description, code, language}
            "action_frequency": {},# action_name -> count
            "updated_at": time.time(),
        }
        self.load()
        self._seed_defaults()

    def _seed_defaults(self) -> None:
        """Seeds initial default project knowledge based on current workspace."""
        try:
            workspace_str = str(BASE_DIR.resolve())
            if "capri" not in self.data["projects"]:
                self.data["projects"]["capri"] = workspace_str
            if "proyecto_actual" not in self.data["projects"]:
                self.data["projects"]["proyecto_actual"] = workspace_str
            if "personal_projects" not in self.data["projects"] and BASE_DIR.parent.exists():
                self.data["projects"]["personal_projects"] = str(BASE_DIR.parent.resolve())
            
            # Default developer preferences
            if "language" not in self.data["preferences"]:
                self.data["preferences"]["language"] = "Python (PySide6, Ollama, async/sync APIs)"
            if "architecture" not in self.data["preferences"]:
                self.data["preferences"]["architecture"] = "Modular, deterministic fallback layer + local SLM"
        except Exception:
            pass

    def load(self) -> None:
        """Loads pattern vault from disk."""
        if self.path.exists():
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    if isinstance(loaded, dict):
                        self.data.update(loaded)
            except Exception as err:
                print(f"[pattern_learning] Warning: Failed to parse {self.path} ({err}).")

        self.data.setdefault("projects", {})
        self.data.setdefault("preferences", {})
        self.data.setdefault("learned_rules", {})
        self.data.setdefault("code_snippets", {})
        self.data.setdefault("action_frequency", {})

    def save(self) -> None:
        """Persists pattern store to disk atomically."""
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.data["updated_at"] = time.time()
            temp_path = self.path.with_suffix(".tmp")
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
            temp_path.replace(self.path)
        except Exception as err:
            print(f"[pattern_learning] Error saving patterns to {self.path}: {err}")

    # ==========================================================================
    # PROJECT ALIASES & LOCATION LEARNING
    # ==========================================================================

    def learn_project_path(self, alias: str, folder_path: str) -> str:
        """Learns a project or folder association (e.g. 'mi_api' -> 'C:/proyectos/api')."""
        clean_alias = (alias or "").strip().lower()
        p = Path(folder_path).expanduser().resolve()
        if not clean_alias:
            return "Status: Error - Se requiere un alias para el proyecto."
        if not p.exists():
            return f"Status: Advertencia - La ruta '{folder_path}' no existe actualmente en el disco."

        with self.lock:
            self.data["projects"][clean_alias] = str(p)
            self.save()
        return f"Status: Patrón aprendido: el proyecto '{clean_alias}' apunta a '{p}'."

    def resolve_project_path(self, name_or_alias: str) -> Optional[Path]:
        """Resolves a project alias or name to a concrete Path."""
        clean = (name_or_alias or "").strip().lower()
        if not clean:
            return BASE_DIR

        with self.lock:
            # 1. Exact match
            if clean in self.data["projects"]:
                candidate = Path(self.data["projects"][clean])
                if candidate.exists():
                    return candidate

            # 2. Substring match
            for alias, target in self.data["projects"].items():
                if clean in alias or alias in clean:
                    candidate = Path(target)
                    if candidate.exists():
                        return candidate

            # 3. Check personal projects parent folder
            parent_dir = BASE_DIR.parent
            if parent_dir.exists() and parent_dir.is_dir():
                candidate = parent_dir / clean
                if candidate.exists() and candidate.is_dir():
                    # Automatically learn this project!
                    self.data["projects"][clean] = str(candidate.resolve())
                    self.save()
                    return candidate.resolve()

        return None

    # ==========================================================================
    # DEVELOPER PREFERENCES & CONVENTIONS
    # ==========================================================================

    def learn_preference(self, key: str, value: str) -> str:
        """Stores a developer preference (e.g. 'test_runner': 'pytest', 'style': 'snake_case')."""
        clean_key = (key or "").strip().lower()
        clean_val = (value or "").strip()
        if not clean_key or not clean_val:
            return "Status: Error - Se requiere clave y valor para la preferencia."

        with self.lock:
            self.data["preferences"][clean_key] = clean_val
            self.save()
        return f"Status: Preferencia aprendida: [{clean_key}] = '{clean_val}'."

    def get_preference(self, key: str, default: str = "") -> str:
        """Retrieves a developer preference."""
        with self.lock:
            return self.data["preferences"].get(key.lower().strip(), default)

    # ==========================================================================
    # CUSTOM INTENT RULES & CORRECTIONS ("cuando diga X, haz Y")
    # ==========================================================================

    def learn_rule(self, trigger_phrase: str, target_action: str, target_params: Optional[Dict[str, Any]] = None) -> str:
        """
        Learns an explicit user-defined correction or shorthand command.
        Example: trigger="modo estudio", action="run_custom_command", params={"name": "estudiar"}
        """
        clean_trigger = (trigger_phrase or "").strip().lower()
        if not clean_trigger or not target_action:
            return "Status: Error - Falta la frase activadora o la acción a ejecutar."

        with self.lock:
            self.data["learned_rules"][clean_trigger] = {
                "action": target_action,
                "params": target_params or {},
                "created_at": time.time(),
            }
            self.save()
        return f"Status: Regla aprendida con éxito: cuando digas '{clean_trigger}', ejecutaré '{target_action}'."

    def match_learned_rule(self, user_text: str) -> Optional[Tuple[str, Dict[str, Any]]]:
        """Checks if user text matches any learned rule with high similarity."""
        clean = (user_text or "").strip().lower()
        if not clean:
            return None

        with self.lock:
            # 1. Exact match
            if clean in self.data["learned_rules"]:
                rule = self.data["learned_rules"][clean]
                return rule["action"], rule.get("params", {})

            # 2. Fuzzy match
            for trigger, rule in self.data["learned_rules"].items():
                ratio = difflib.SequenceMatcher(None, clean, trigger).ratio()
                if ratio > 0.88 or trigger in clean:
                    return rule["action"], rule.get("params", {})

        return None

    # ==========================================================================
    # CODE PATTERNS & SNIPPETS STORAGE
    # ==========================================================================

    def save_code_pattern(self, name: str, code: str, description: str = "", language: str = "python") -> str:
        """Saves a reusable architectural pattern, template, or code snippet."""
        clean_name = (name or "").strip().lower()
        if not clean_name or not code:
            return "Status: Error - Se requiere nombre y código para el patrón."

        with self.lock:
            self.data["code_snippets"][clean_name] = {
                "code": code.strip(),
                "description": description.strip(),
                "language": language.strip(),
                "saved_at": time.time(),
            }
            self.save()
        return f"Status: Patrón de código '{clean_name}' guardado en la memoria de desarrollo."

    def get_code_pattern(self, name: str) -> Optional[Dict[str, Any]]:
        """Retrieves a stored code pattern."""
        clean = (name or "").strip().lower()
        with self.lock:
            if clean in self.data["code_snippets"]:
                return self.data["code_snippets"][clean]
            for key, val in self.data["code_snippets"].items():
                if clean in key:
                    return val
        return None

    # ==========================================================================
    # FREQUENCY & HABIT TRACKING
    # ==========================================================================

    def record_usage(self, action_name: str) -> None:
        """Increments usage counter for frequent actions."""
        clean = (action_name or "").strip().lower()
        if not clean:
            return
        with self.lock:
            count = self.data["action_frequency"].get(clean, 0)
            self.data["action_frequency"][clean] = count + 1
            # Save every 5 usages to minimize disk writes
            if (count + 1) % 5 == 0:
                self.save()

    def get_top_habits(self, limit: int = 5) -> List[Tuple[str, int]]:
        """Returns the most frequent actions executed by the user."""
        with self.lock:
            items = list(self.data["action_frequency"].items())
            items.sort(key=lambda x: x[1], reverse=True)
            return items[:limit]

    # ==========================================================================
    # SUMMARY & INTROSPECTION
    # ==========================================================================

    def summary(self) -> str:
        """Returns a human-readable summary of everything Capri has learned."""
        with self.lock:
            projects = list(self.data["projects"].keys())
            prefs = [f"{k}: {v}" for k, v in self.data["preferences"].items()]
            rules = list(self.data["learned_rules"].keys())
            snippets = list(self.data["code_snippets"].keys())
            top_habits = self.get_top_habits(3)

            lines = ["Status: Resumen de aprendizaje de Capri:"]
            lines.append(f"- Proyectos conocidos ({len(projects)}): {', '.join(projects) if projects else 'Ninguno'}")
            lines.append(f"- Preferencias registradas ({len(prefs)}): {'; '.join(prefs) if prefs else 'Ninguna'}")
            lines.append(f"- Reglas aprendidas ({len(rules)}): {', '.join(rules) if rules else 'Ninguna'}")
            lines.append(f"- Plantillas/Patrones de código ({len(snippets)}): {', '.join(snippets) if snippets else 'Ninguna'}")
            if top_habits:
                habit_str = ", ".join([f"{act} ({cnt}x)" for act, cnt in top_habits])
                lines.append(f"- Hábitos más frecuentes: {habit_str}")

            return "\n".join(lines)


# Global singleton instance
_learner_instance: Optional[PatternLearner] = None


def get_pattern_learner() -> PatternLearner:
    """Returns the singleton PatternLearner instance."""
    global _learner_instance
    if _learner_instance is None:
        _learner_instance = PatternLearner()
    return _learner_instance


# Tool wrappers for brain.py TOOL_REGISTRY
def learn_pattern(kind: str = "project", name: str = "", value: str = "", description: str = "", **kwargs) -> str:
    """Learns a pattern, preference, or project alias."""
    learner = get_pattern_learner()
    clean_kind = (kind or kwargs.get("type") or "project").strip().lower()
    clean_name = (name or kwargs.get("key") or kwargs.get("alias") or "").strip()
    clean_val = (value or kwargs.get("val") or kwargs.get("path") or "").strip()

    if clean_kind in ("project", "proyecto", "carpeta", "path"):
        return learner.learn_project_path(clean_name, clean_val)
    elif clean_kind in ("preference", "preferencia", "estilo", "style"):
        return learner.learn_preference(clean_name, clean_val)
    elif clean_kind in ("rule", "regla", "comando", "atajo"):
        return learner.learn_rule(clean_name, clean_val)
    elif clean_kind in ("code", "codigo", "código", "snippet"):
        return learner.save_code_pattern(clean_name, clean_val, description)
    else:
        return learner.learn_preference(clean_name or clean_kind, clean_val)


def list_learned_patterns(**kwargs) -> str:
    """Lists all learned patterns, aliases, and preferences."""
    return get_pattern_learner().summary()
