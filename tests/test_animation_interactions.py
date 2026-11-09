import sys
from pathlib import Path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

"""
test_animation_interactions.py - Verification suite for 30-animation pack integration & interactive hooks.
"""
import sys
import time
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QPointF

app = QApplication.instance() or QApplication(sys.argv)
app.setQuitOnLastWindowClosed(False)

from body import SpiderWindow, SpriteAnimator
from bubble import SpiderBubble


def test_manifest_and_animations_loaded():
    print("[1] Verifying all 30 base animations and synthesized variants in SpriteAnimator...")
    sprites_dir = Path("assets/sprites/spiderman")
    animator = SpriteAnimator(sprites_dir)

    expected_30 = [
        "idle", "walk", "run", "jump", "fall", "land",
        "climb", "wall_idle", "ceiling_crawl", "web_shoot", "web_hang", "web_swing",
        "listen", "think", "work", "talk", "success", "error",
        "wave", "sit", "sleep", "wake", "drag", "peek",
        "brake", "read", "search", "point", "surprise", "released"
    ]

    for name in expected_30:
        assert name in animator.animations, f"Missing base animation '{name}'!"
        frames = animator.animations[name]["frames"]
        assert len(frames) > 0, f"Animation '{name}' has 0 frames!"

    # Verify synthesized software variant 'climb_down'
    assert "climb_down" in animator.animations, "Missing synthesized 'climb_down' variant!"
    assert len(animator.animations["climb_down"]["frames"]) == len(animator.animations["climb"]["frames"])
    print(f"  All {len(expected_30)} base animations + climb_down loaded with valid pixmaps: OK")


def test_weborigin_metadata_and_hand_position():
    print("[2] Verifying vector webOrigin extraction and get_hand_pos precision...")
    spidey = SpiderWindow()
    spidey.animator.set_state("web_shoot")
    spidey.animator.current_frame = 2  # frame 02 defines webOrigin {'x': 87, 'y': 78}

    origin = spidey.animator.current_web_origin()
    assert origin is not None, "Failed to extract webOrigin from frame metadata"
    assert isinstance(origin, QPointF)
    # 87 * (140/128) ~= 95.15, 10 + 78 * (140/128) ~= 95.31
    assert 90 <= origin.x() <= 100, f"Unexpected webOrigin X: {origin.x()}"
    assert 90 <= origin.y() <= 100, f"Unexpected webOrigin Y: {origin.y()}"

    # Hand position matches exact webOrigin
    hand_pos = spidey.get_hand_pos()
    assert abs(hand_pos.x() - int(origin.x())) <= 1
    assert abs(hand_pos.y() - int(origin.y())) <= 1
    print("  Vector webOrigin pixel-level extraction: OK")
    spidey.close()


def test_listen_animation_on_typing():
    print("[3] Verifying 'listen' animation triggered while typing in speech bubble...")
    spidey = SpiderWindow()
    spidey.animator.set_state("idle")

    # Simulate user typing in QLineEdit
    spidey.bubble.edit.setText("Hola Spidey")
    spidey.bubble._on_text_edited("Hola Spidey")
    assert spidey.animator.current_state == "listen", f"Expected 'listen', got {spidey.animator.current_state}"

    # Typing timeout returns to idle
    spidey._on_typing_idle()
    assert spidey.animator.current_state == "idle", f"Expected 'idle', got {spidey.animator.current_state}"
    print("  Attentive listening animation upon typing: OK")
    spidey.close()


def test_drag_and_drop_retention():
    print("[4] Verifying drag-and-drop position retention (stays where user drops him)...")
    spidey = SpiderWindow()
    floor_y = spidey.get_floor_y()

    # Position high in mid-air and simulate release after dragging
    target_mid_y = floor_y - 200
    spidey.move(spidey.x(), target_mid_y)
    spidey._drag_start_pos = QPointF(100, 100).toPoint()
    
    # Create fake release event after moving
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtCore import QEvent, Qt, QPoint
    fake_release = QMouseEvent(QEvent.MouseButtonRelease, QPoint(100, 100), QPointF(200, 200), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
    spidey.mouseReleaseEvent(fake_release)

    # Must stay at target_mid_y, NOT fall to floor_y!
    assert spidey.y() == target_mid_y, f"Expected Spidey to stay at y={target_mid_y}, but got y={spidey.y()}"
    assert spidey.animator.current_state in ("released", "idle")
    print("  Drag and drop stays where user drops him: OK")
    spidey.close()


def test_interactive_spidey_click():
    print("[5] Verifying interactive click handling (wake / reactive gestures)...")
    spidey = SpiderWindow()

    # 1. Sleeping spidey wakes up on click
    spidey.animator.set_state("sleep")
    spidey._handle_spidey_click()
    assert spidey.animator.current_state == "wake", f"Expected 'wake', got {spidey.animator.current_state}"

    # 2. Idle spidey plays expressive gesture
    spidey.animator.set_state("idle")
    spidey._handle_spidey_click()
    assert spidey.animator.current_state in ("wave", "surprise", "peek", "point", "read", "search")
    print("  Interactive click wakeup and gesture cycle: OK")
    spidey.close()


def test_ceiling_crawl_and_wall_climb_motion():
    print("[6] Verifying ceiling crawl and wall climb sequence initialization...")
    spidey = SpiderWindow()

    # Ceiling crawl test
    spidey._start_auto_ceiling_crawl()
    assert spidey.is_roaming_moving is True
    assert spidey._current_roam_action["type"] == "ceiling_crawl_sequence"
    assert spidey.animator.current_state in ("web_shoot", "ceiling_crawl")

    # Wall climb test
    spidey._start_auto_climb()
    assert spidey.is_roaming_moving is True
    assert spidey._current_roam_action["type"] == "climb_sequence"
    assert spidey.animator.current_state in ("climb", "wall_idle")
    print("  Ceiling crawl and wall climb motion: OK")
    spidey.close()


def test_semantic_animation_triggers():
    print("[7] Verifying semantic conversational animation triggers...")
    spidey = SpiderWindow()
    # Mock brain.talk to avoid invoking live network inference during unit test
    spidey.brain.talk = lambda *args, **kwargs: "¡Acción ejecutada, vecino!"

    # Search intent
    spidey._handle_user_submit("en brave busca wikipedia")
    assert spidey.animator.current_state in ("search", "work")

    # Science / read query
    spidey._handle_user_submit("explica la ecuación de Bernoulli")
    assert spidey.animator.current_state in ("read", "think")

    # Greeting
    spidey._handle_user_submit("hola amigo")
    assert spidey.animator.current_state in ("wave", "think")

    # Surprise
    spidey._handle_user_submit("¡Cuidado con el duende verde!")
    assert spidey.animator.current_state in ("surprise", "think")

    # Praise / Success
    spidey._on_brain_reply("¡De nada!", "muchas gracias genial trabajo")
    assert spidey.animator.current_state == "success"

    # Clean up worker thread cleanly before exiting
    if spidey._current_worker and spidey._current_worker.isRunning():
        spidey._current_worker.terminate()
        spidey._current_worker.wait(300)

    print("  Conversational and tool semantic animation triggers: OK")
    spidey.close()


if __name__ == "__main__":
    test_manifest_and_animations_loaded()
    test_weborigin_metadata_and_hand_position()
    test_listen_animation_on_typing()
    test_drag_and_drop_retention()
    test_interactive_spidey_click()
    test_ceiling_crawl_and_wall_climb_motion()
    test_semantic_animation_triggers()
    print("\n[ALL 7 ANIMATION INTERACTION TESTS PASSED 100%!]")
