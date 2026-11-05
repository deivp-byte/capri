"""
memory.py - Lightweight Long-Term Memory & Fact Recall for Capri

Adapted from original Capri architecture (abilities/memory.py) but strictly
optimized for low-resource environments (4GB VRAM / Local SLMs):
- Zero external vector databases (no Qdrant / heavy embeddings).
- JSON Shard storage (data/memory.json) with facts and conversation history.
- Stem-based keyword overlap recall (_stems) for high-speed relevance matching.
- Automatic fact deduplication and update using SequenceMatcher.
- Ephemeral context injection: only relevant facts are passed to the 2048-token context.
"""

from __future__ import annotations

import difflib
import json
from pathlib import Path
import re
import threading
import time
from typing import List, Set

from config import DATA_DIR


# Common stop words in Spanish and English to filter out during relevance matching
_STOP_WORDS: Set[str] = {
    # English
    "the", "and", "or", "but", "to", "of", "in", "on", "for", "with", "is", "are",
    "was", "were", "be", "it", "this", "that", "you", "your", "my", "me", "what",
    "how", "why", "when", "who", "do", "does", "did", "can", "could", "would",
    "should", "just", "like", "really", "very", "not", "yes", "please",
    # Spanish
    "el", "la", "los", "las", "un", "una", "unos", "unas", "de", "del", "en", "con",
    "por", "para", "es", "son", "era", "ser", "estar", "este", "esta", "esto",
    "mi", "tu", "su", "mis", "tus", "sus", "que", "qué", "como", "cómo", "por qué",
    "cuando", "cuándo", "quien", "quién", "hacer", "hace", "puedes", "podrías",
    "solo", "muy", "no", "si", "sí", "favor", "algo", "nada"
}

_ASKS_ABOUT_USER = re.compile(
    r"\b(?:mi|mis|yo|conmigo|recuerdas|te acuerdas|sabes de m[ií]|qui[eé]n soy|c[oó]mo me llamo|my|me|i|remember|about me)\b",
    re.IGNORECASE
)

_QUESTION = re.compile(
    r"\?|^\s*(?:qu[eé]|qui[eé]n|d[oó]nde|cu[aá]ndo|c[oó]mo|cu[aá]l|what|who|where|when|how|which)\b",
    re.IGNORECASE
)


def _words(text: str) -> Set[str]:
    """Extracts normalized words of length >= 3, removing punctuation and stop words."""
    cleaned = re.sub(r"['’]s\b|[^\w\s]", " ", (text or "").lower())
    return {w for w in cleaned.split() if len(w) >= 3 and w not in _STOP_WORDS}


def _stems(text: str) -> Set[str]:
    """Words cut to their first 4 letters for fuzzy morphological matching."""
    return {w[:4] for w in _words(text)}


class SpiderMemory:
    """
    Manages persistent user facts, preferences, and dialogue history
    within a lightweight JSON file for Spider-Man desktop agent.
    """

    def __init__(self, memory_file: Path | None = None) -> None:
        self.path = memory_file or (DATA_DIR / "memory.json")
        self.lock = threading.Lock()
        self.data = {
            "facts": [],
            "history": []
        }
        self.load()

    def load(self) -> None:
        """Loads data from disk if file exists."""
        if self.path.exists():
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    if isinstance(loaded, dict):
                        self.data = loaded
                    elif isinstance(loaded, list):
                        # Migration from legacy list format
                        self.data = {"facts": [], "history": loaded}
            except Exception as err:
                print(f"[memory] Warning: Failed to parse memory file ({err}). Initializing fresh store.")
                self.data = {"facts": [], "history": []}

        self.data.setdefault("facts", [])
        self.data.setdefault("history", [])

    def save(self) -> None:
        """Saves current state to JSON file."""
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
        except Exception as err:
            print(f"[memory] Error saving memory to {self.path}: {err}")

    # --------------------------------------------------------------------------
    # FACTS MANAGEMENT
    # --------------------------------------------------------------------------

    def remember(self, fact_text: str, subject: str = "user") -> str:
        """
        Stores or updates a long-term fact about the user or rig.
        Uses SequenceMatcher to update existing facts if similarity > 0.82.
        """
        clean = (fact_text or "").strip()
        if not clean:
            return "Status: Error - Empty fact provided."

        with self.lock:
            # Check for existing similar fact to update
            for item in self.data["facts"]:
                ratio = difflib.SequenceMatcher(None, item["text"].lower(), clean.lower()).ratio()
                if ratio > 0.82:
                    old_text = item["text"]
                    item["text"] = clean
                    item["t"] = time.time()
                    self.save()
                    return f"Status: Updated existing memory from '{old_text}' to '{clean}'."

            # Append new fact
            self.data["facts"].append({
                "text": clean,
                "subject": subject,
                "t": time.time(),
            })
            self.save()
            return f"Status: Fact permanently stored in memory: '{clean}'."

    def relevant_facts(self, query: str, speaker: str = "user", limit: int = 5) -> List[str]:
        """
        Retrieves facts relevant to the current conversation turn.
        Uses word stem overlap scoring to keep prompt size minimal.
        """
        facts = [f["text"] for f in self.data.get("facts", [])]
        if not facts:
            return []

        query_stems = _stems(query) - {speaker.lower()[:4]}
        scored = []

        for f in facts:
            overlap = len(query_stems & _stems(f))
            if overlap > 0:
                scored.append((overlap, f))

        scored.sort(key=lambda x: x[0], reverse=True)
        results = [f for _, f in scored[:limit]]

        # If user directly asks what Capri remembers about them, return latest facts
        if _ASKS_ABOUT_USER.search(query) and (results or _QUESTION.search(query)):
            for f in reversed(facts):
                if f not in results:
                    results.append(f)
                if len(results) >= limit:
                    break

        return results[:limit]

    # --------------------------------------------------------------------------
    # CHAT HISTORY MANAGEMENT
    # --------------------------------------------------------------------------

    def get_history(self) -> List[dict]:
        """Returns the conversation history list."""
        with self.lock:
            return list(self.data.get("history", []))

    def set_history(self, history: List[dict]) -> None:
        """Replaces the conversation history list and saves."""
        with self.lock:
            self.data["history"] = list(history)
            self.save()

    def add_turn(self, user_msg: str, assistant_msg: str, max_turns: int = 12) -> None:
        """Appends a dialogue turn and keeps history within bounds."""
        with self.lock:
            self.data["history"].append({"role": "user", "content": user_msg})
            self.data["history"].append({"role": "assistant", "content": assistant_msg})
            if len(self.data["history"]) > max_turns * 2:
                self.data["history"] = self.data["history"][-max_turns * 2:]
            self.save()


# Backward compatibility alias
CapriMemory = SpiderMemory
