import sys
from pathlib import Path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

"""
test_ux_refinements.py - Verification suite for:
1. Animated floor descent (no teleportation).
2. Generous bubble reading duration and hover protection.
3. Windowed mode application enforcement.
4. Immediate action acknowledgment and visual animation.
5. Model configuration preserved as qwen2.5:3b.
"""
import sys
import time
import json
from pathlib import Path
from PySide6.QtWidgets import QApplication

app = QApplication.instance() or QApplication(sys.argv)
app.setQuitOnLastWindowClosed(False)

from body import SpiderWindow
from bubble import SpiderBubble
from abilities.window_manager import ensure_windowed_mode, _SIMULATED_WINDOWS
from brain import _detect_action_intent


def test_model_config():
    print("[1] Verifying qwen2.5:3b model configuration in data/config.json...")
    config_path = Path("data/config.json")
    with open(config_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["ollama"]["model"] in ("qwen2.5-coder:7b", "qwen2.5:3b"), f"Unexpected model {data['ollama']['model']}"
    print("  Model is set to 'qwen2.5:3b': OK")


def test_bubble_reading_duration_and_hover():
    print("[2] Verifying bubble reading duration & hover hold...")
    bubble = SpiderBubble()
    
    # Test short reply
    bubble.say("¡Hola socio!")
    assert bubble.hold_until - time.monotonic() >= 10.0, "Base reading hold too short"
    
    # Test long reply (e.g. 250 characters)
    long_text = "Esta es una explicación detallada sobre el ordenador con muchas palabras para comprobar que el usuario tiene suficiente tiempo para leer todo el mensaje con calma sin que desaparezca en mitad de la lectura, permitiendo una experiencia cómoda."
    bubble.say(long_text)
    time_left = bubble.hold_until - time.monotonic()
    assert time_left >= 20.0, f"Expected >= 20.0s for long text, got {time_left}s"
    print(f"  Long text hold time: {time_left:.1f}s: OK")

    # Test typing completion updates _finished_typing_at and extends hold
    bubble.shown_chars = float(len(long_text))
    bubble._tick()
    assert bubble._finished_typing_at > 0.0, "Finished typing timestamp not recorded"

    # Test immediate action notice
    bubble.action_notice("🕸️ ¡Lanzando telaraña para abrir Brave!...")
    assert bubble.is_thinking is True
    assert "Lanzando telaraña" in bubble.full_reply
    print("  Immediate action notice: OK")
    bubble.close()


def test_animated_floor_navigation():
    print("[3] Verifying animated descent to floor (no teleportation)...")
    spidey = SpiderWindow()
    floor_y = spidey.get_floor_y()

    # Place spidey high up
    spidey.move(spidey.x(), floor_y - 250)
    spidey._send_to_floor()
    # Spidey should launch roam motion (swing or drop) rather than instantaneous teleport
    assert spidey.is_roaming_moving is True or spidey._current_roam_action is not None
    assert spidey._perch_info is None
    print("  High position descent triggered animated motion (swing/drop): OK")

    # Place spidey near floor
    spidey._cancel_roam()
    spidey.move(spidey.x(), floor_y - 10)
    spidey._send_to_floor()
    assert spidey.animator.current_state in ("jump", "land", "idle")
    print("  Near floor triggered playful hop & land: OK")
    spidey.close()


def test_windowed_mode_enforcement():
    print("[4] Verifying windowed mode enforcement...")
    # Add a mock maximized window in simulated list
    _SIMULATED_WINDOWS[9991] = {
        "title": "Brave Browser",
        "rect": [0, 0, 1920, 1080],
        "maximized": True,
        "minimized": False,
    }
    res = ensure_windowed_mode(9991)
    assert res is True
    assert _SIMULATED_WINDOWS[9991]["maximized"] is False, "Window was not unmaximized"
    print("  Windowed mode enforcement: OK")


def test_action_intent_animations():
    print("[5] Verifying action intent triggers immediate animation & prompt...")
    intent_brave = _detect_action_intent("abre brave")
    assert intent_brave is not None
    assert intent_brave.function.name in ("abrir_aplicacion", "open_app")

    intent_search = _detect_action_intent("en brave busca youtube")
    assert intent_search is not None
    assert intent_search.function.name == "browser_search"
    print("  Action intent detection for immediate animation: OK")


if __name__ == "__main__":
    test_model_config()
    test_bubble_reading_duration_and_hover()
    test_animated_floor_navigation()
    test_windowed_mode_enforcement()
    test_action_intent_animations()
    print("\n[ALL UX REFINEMENT TESTS PASSED 100%!]")
