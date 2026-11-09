"""
body.py - Visual Body, Desktop Window, Vector Web Choreography & Sprite Renderer for Spider-Man

Implements:
1. Window Flags: Frameless, translucent, always-on-top desktop overlay.
2. Free Window Dragging: Move Spidey smoothly across the desktop; speech bubble follows seamlessly.
3. 30-Animation State Engine: High-fidelity pixel-art animations loaded directly from
   animations.json manifest (idle, walk, run, drag, released, land, think, talk, work, wave, web_shoot, web_swing, web_hang).
4. Dynamic Vector Web Rendering: High-performance QPainterPath vector webs using QPen(QColor(240, 240, 255, 230), 2)
   with elastic tension curves and screen-wide click-through overlay.
5. Window Choreography Engine:
   - Case A: Pendular swinging to active window top frame.
   - Case B: Distance web-shooting ("pull_web" / "snatch") and smooth real-time window pulling.
   - Case C: Physical window dragging synchronized frame-by-frame with desktop pet movement.
6. Speech Bubble Integration: Connected to SpiderBubble for typewriter transmissions.
7. Asynchronous Brain Integration: Multi-threaded background inference preventing UI freezes.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
import random
import sys
import time

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, QThread, QTimer, Signal
from PySide6.QtGui import (
    QAction,
    QColor,
    QFont,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPen,
    QPixmap,
    QTransform,
)
from PySide6.QtWidgets import QApplication, QMenu, QWidget

from abilities.window_manager import (
    get_active_or_target_window,
    move_window,
    minimize_window,
)
from abilities.media_sensor import get_now_playing
from brain import SpiderBrain, CapriBrain, set_window_action_callback, set_window_perch_callback
from bubble import SpiderBubble, CapriBubble
from config import get_config


# ==============================================================================
# SECTION 1: ASYNCHRONOUS BRAIN WORKER THREAD
# ==============================================================================

class BrainWorker(QThread):
    """
    Background worker thread to handle Ollama inference without blocking the
    PySide6 UI thread (preventing OS 'Not Responding' hangs).
    """
    reply_ready = Signal(str, str)  # (reply_text, original_user_text)
    chunk_received = Signal(str)     # Streaming token chunks
    error_occurred = Signal(str)

    def __init__(self, brain: SpiderBrain, user_text: str):
        super().__init__()
        self.brain = brain
        self.user_text = user_text

    def run(self) -> None:
        try:
            # Pass chunk streaming callback for real-time response delivery
            reply = self.brain.talk(
                self.user_text,
                on_chunk=lambda token: self.chunk_received.emit(token)
            )
            self.reply_ready.emit(reply, self.user_text)
        except Exception as err:
            self.error_occurred.emit(str(err))


# ==============================================================================
# SECTION 2: 30-ANIMATION SPRITE CONTROLLER (ANIMATIONS.JSON MANIFEST)
# ==============================================================================

class SpriteAnimator:
    """
    High-fidelity state engine controlling all 30 pixel-art Spider-Man animations.
    Loads metadata (FPS, loop, transitions, pivots, webOrigin) directly from animations.json manifest.
    Synthesizes software variants (e.g. 'climb_down') and handles directional mirroring.
    """

    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir
        self.animations: dict[str, dict] = {}
        self.current_state = "idle"
        self.current_frame = 0
        self.last_frame_time = time.monotonic()
        self.load_all()

    def load_all(self) -> None:
        """Loads all animations and frames declared in animations.json."""
        manifest_path = self.base_dir / "animations.json"
        if not manifest_path.exists():
            return

        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as err:
            print(f"[spiderman] Warning: Failed to read animations.json: {err}")
            return

        manifest_anims = data.get("animations", {})

        for name, meta in manifest_anims.items():
            frames_dir = self.base_dir / "frames" / name
            pixmaps: list[QPixmap] = []

            if frames_dir.exists():
                for p in sorted(frames_dir.glob("*.png")):
                    pix = QPixmap(str(p))
                    if not pix.isNull():
                        pixmaps.append(pix)

            if pixmaps:
                self.animations[name] = {
                    "fps": max(1, meta.get("fps", 10)),
                    "loop": meta.get("loop", True),
                    "next": meta.get("next"),
                    "frames": pixmaps,
                    "frame_data": meta.get("frames", []),
                }

        # Synthesize software animation variants as defined in sprite documentation
        if "climb" in self.animations:
            climb = self.animations["climb"]
            self.animations["climb_down"] = {
                "fps": climb["fps"],
                "loop": True,
                "next": None,
                "frames": list(reversed(climb["frames"])),
                "frame_data": list(reversed(climb.get("frame_data", []))),
            }

    def set_state(self, state: str) -> None:
        """Switches to a new animation state if recognized, with aliases and directional suffixes."""
        target_state = state
        if target_state.endswith("_left") or target_state.endswith("_right"):
            base = target_state.rsplit("_", 1)[0]
            if base in self.animations:
                target_state = base

        if target_state not in self.animations:
            aliases = {
                "swing": "web_swing",
                "shoot": "web_shoot",
                "hang": "web_hang",
                "pull_effort": "work",
                "effort": "work",
                "push": "work",
                "crouch": "sit",
                "rest": "sit",
                "nap": "sleep",
                "alert": "surprise",
                "tingle": "surprise",
                "shock": "surprise",
                "cheer": "success",
                "praise": "success",
                "descend": "climb_down",
                "web_descend": "web_hang",
                "crawl": "ceiling_crawl",
            }
            target_state = aliases.get(target_state, target_state)

        if target_state in self.animations and target_state != self.current_state:
            self.current_state = target_state
            self.current_frame = 0
            self.last_frame_time = time.monotonic()

    def tick(self) -> bool:
        """
        Advances the animation frame according to the state's FPS and loop logic.
        Handles state transitions (e.g., 'released' -> 'fall' -> 'land' -> 'idle').
        Returns True if a repaint is needed.
        """
        now = time.monotonic()
        anim = self.animations.get(self.current_state)
        if not anim:
            return False

        fps = anim["fps"]
        frame_interval = 1.0 / fps

        if now - self.last_frame_time >= frame_interval:
            frames = anim["frames"]
            if self.current_frame + 1 < len(frames):
                self.current_frame += 1
                self.last_frame_time = now
                return True
            else:
                # End of animation sequence reached
                if anim["loop"]:
                    self.current_frame = 0
                    self.last_frame_time = now
                    return True
                else:
                    # Non-looping animation transition
                    next_state = anim.get("next")
                    if next_state and next_state in self.animations:
                        self.set_state(next_state)
                        return True
                    return False
        return False

    def current_pixmap(self) -> QPixmap | None:
        """Returns the current active frame QPixmap."""
        anim = self.animations.get(self.current_state)
        if anim and anim["frames"]:
            return anim["frames"][self.current_frame % len(anim["frames"])]
        return None

    def current_web_origin(self) -> QPointF | None:
        """Returns pixel-accurate vector web origin from manifest frame metadata."""
        anim = self.animations.get(self.current_state)
        if not anim:
            return None
        frame_data = anim.get("frame_data", [])
        if not frame_data:
            return None
        idx = self.current_frame % len(frame_data)
        fdata = frame_data[idx]
        origin = fdata.get("webOrigin")
        if not origin:
            return None
        scale = 140.0 / 128.0
        wx = origin["x"] * scale
        wy = 10.0 + (origin["y"] * scale)
        return QPointF(wx, wy)

    def current_pivot(self) -> QPointF | None:
        """Returns contact pivot from manifest frame metadata."""
        anim = self.animations.get(self.current_state)
        if not anim:
            return None
        frame_data = anim.get("frame_data", [])
        if not frame_data:
            return None
        idx = self.current_frame % len(frame_data)
        fdata = frame_data[idx]
        piv = fdata.get("pivot")
        if not piv:
            return None
        scale = 140.0 / 128.0
        wx = piv["x"] * scale
        wy = 10.0 + (piv["y"] * scale)
        return QPointF(wx, wy)


# ==============================================================================
# SECTION 3: DYNAMIC VECTOR WEB RENDERING UTILITY
# ==============================================================================

def draw_dynamic_web(
    painter: QPainter,
    start_pt: QPointF,
    end_pt: QPointF,
    sag: float = 0.0,
) -> None:
    """
    Renders high-visibility, organic vector web lines in real time using QPainterPath
    and QPen(QColor(240, 240, 255, 230), 2) with elastic sag and high-visibility glow.
    """
    if start_pt.isNull() or end_pt.isNull():
        return

    painter.save()
    painter.setRenderHint(QPainter.Antialiasing, True)

    path = QPainterPath()
    path.moveTo(start_pt)

    if abs(sag) > 0.5:
        # Elastic tension / gravitational curve
        mid_x = (start_pt.x() + end_pt.x()) / 2.0
        mid_y = (start_pt.y() + end_pt.y()) / 2.0 + sag
        path.quadTo(QPointF(mid_x, mid_y), end_pt)
    else:
        path.lineTo(end_pt)

    # Core luminous web strand (as specified in architectural requirements)
    core_pen = QPen(QColor(240, 240, 255, 230), 2, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    painter.setPen(core_pen)
    painter.drawPath(path)

    # Soft outer glow for crisp visibility across dark and light desktop backgrounds
    glow_pen = QPen(QColor(255, 255, 255, 95), 4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    painter.setPen(glow_pen)
    painter.drawPath(path)

    painter.restore()


# ==============================================================================
# SECTION 4: FULL-SCREEN CLICK-THROUGH WEB CANVAS OVERLAY
# ==============================================================================

class WebCanvasOverlay(QWidget):
    """
    Full-screen transparent click-through canvas overlay to render
    dynamic vector webs extending beyond Spider-Man's bounding box
    directly across the desktop without any window boundary clipping.
    """

    def __init__(self, spidey: SpiderWindow) -> None:
        super().__init__()
        self.spidey = spidey
        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool |
            Qt.WindowTransparentForInput
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._sync_screen_geometry()

    def _sync_screen_geometry(self) -> None:
        """Adapts canvas geometry to full primary screen bounds."""
        screen = QApplication.primaryScreen()
        if screen:
            self.setGeometry(screen.geometry())

    def paintEvent(self, event: QPaintEvent) -> None:
        """Draws screen-spanning web string connecting Spidey with target window/ceiling."""
        if (
            self.spidey.web_active
            and self.spidey.web_start_point is not None
            and self.spidey.web_end_point is not None
        ):
            painter = QPainter(self)
            draw_dynamic_web(
                painter,
                self.spidey.web_start_point,
                self.spidey.web_end_point,
                self.spidey.web_sag
            )
            painter.end()


# ==============================================================================
# SECTION 5: SPIDER-MAN DESKTOP PET WINDOW
# ==============================================================================

class SpiderWindow(QWidget):
    """
    Transparent, draggable desktop overlay window representing Spider-Man.
    Coordinates interactive window choreography and dynamic web shooting.
    """

    SPRITE_WIDTH = 140
    SPRITE_HEIGHT = 160

    # Thread-safe signal to trigger visual window choreography from background worker
    choreography_requested = Signal(int, str, object, object)  # (wid, action, start_coords, target_coords)

    def __init__(self) -> None:
        super().__init__()

        # Critical: Prevent Qt from auto-quitting when secondary dialogs or menus close
        _app = QApplication.instance()
        if _app:
            _app.setQuitOnLastWindowClosed(False)

        # Initialize Brain & Memory
        self.brain = SpiderBrain()
        self.cfg = getattr(self.brain, "cfg", None) or get_config()

        # Window drag tracking state
        self._drag_pos: QPoint | None = None
        self._current_worker: BrainWorker | None = None
        self._commands_dialog = None

        # Setup 30-animation sprite engine
        sprites_dir = Path(__file__).resolve().parent / "assets" / "sprites" / "spiderman"
        self.animator = SpriteAnimator(sprites_dir)

        # Dynamic vector web state
        self.web_active: bool = False
        self.web_start_point: QPointF | None = None
        self.web_end_point: QPointF | None = None
        self.web_sag: float = 0.0

        # Fullscreen transparent web overlay
        self.web_overlay = WebCanvasOverlay(self)

        # Window Choreography 60 FPS Engine
        self._choreo_timer = QTimer(self)
        self._choreo_timer.timeout.connect(self._on_choreo_tick)
        self._choreo_state: dict | None = None

        # Setup PySide6 visual flags and attributes
        self._setup_window_flags()
        self.setFixedSize(self.SPRITE_WIDTH, self.SPRITE_HEIGHT)

        # Setup Speech Bubble
        self.bubble = SpiderBubble(self)
        self.bubble.submitted.connect(self._handle_user_submit)
        self.bubble.user_typing.connect(self._on_user_typing)
        self.bubble.typing_finished.connect(self._on_speech_finished)

        # Typing silence timer: returns from 'listen' to 'idle' when typing pauses
        self._typing_idle_timer = QTimer(self)
        self._typing_idle_timer.setSingleShot(True)
        self._typing_idle_timer.timeout.connect(self._on_typing_idle)

        # Configured FPS animation loop (e.g. 30 FPS = ~33ms, saving CPU cycles when idle)
        target_fps = self.cfg.get("desk", {}).get("fps", 30)
        self.anim_interval_ms = max(20, int(1000 / target_fps))
        self.anim_timer = QTimer(self)
        self.anim_timer.timeout.connect(self._on_anim_tick)
        self.anim_timer.start(self.anim_interval_ms)

        # Autonomous Roaming & Desktop Life Engine (Calm Pacing)
        self.roaming_enabled: bool = True
        self.facing_left: bool = False
        self.last_user_touch: float = time.monotonic()
        self.next_roam_time: float = time.monotonic() + random.uniform(35.0, 75.0)
        self.is_roaming_moving: bool = False
        self._current_roam_action: dict | None = None
        self._perch_info: dict | None = None

        # Spontaneous Live Chatter & Ambient Thought Engine
        self.last_spontaneous_speech: float = time.monotonic()
        self.next_spontaneous_speech: float = time.monotonic() + random.uniform(90.0, 180.0)
        self._chatter_timer = QTimer(self)
        self._chatter_timer.timeout.connect(self._evaluate_spontaneous_chatter)
        self._chatter_timer.start(5000)

        # Roaming evaluation & motion timers
        self._roam_eval_timer = QTimer(self)
        self._roam_eval_timer.timeout.connect(self._evaluate_autonomous_roam)
        self._roam_eval_timer.start(1000)

        self._roam_motion_timer = QTimer(self)
        self._roam_motion_timer.timeout.connect(self._on_roam_motion_tick)

        # Initial placement on screen floor (above taskbar)
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            init_x = max(0, geo.right() - self.SPRITE_WIDTH - 60)
            init_y = max(0, geo.bottom() - self.SPRITE_HEIGHT + 8)
            self.move(init_x, init_y)

        # Initial positioning of speech bubble
        self.bubble.reposition()

        # Wire window choreography and perching signals from brain.py to GUI thread
        self.choreography_requested.connect(self._start_choreography)
        set_window_action_callback(
            lambda wid, act, sc, tc: self.choreography_requested.emit(wid, act, sc, tc)
        )
        set_window_perch_callback(
            lambda wid, coords: self.perch_on_window(wid, coords)
        )

    def _setup_window_flags(self) -> None:
        """Applies window flags and attributes for a transparent, borderless overlay."""
        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setMouseTracking(True)

    def _on_anim_tick(self) -> None:
        """60 FPS animation loop: frame advancing, real-time window tracking & physics."""
        # High-frequency synchronous window follow (60 FPS, zero stutter)
        if (
            self._perch_info is not None
            and not self.is_roaming_moving
            and not self._choreo_timer.isActive()
            and self._drag_pos is None
        ):
            self._update_perch_follow()

        if self.animator.tick():
            self.update()

    # --------------------------------------------------------------------------
    # SCREEN & DESKTOP GEOMETRY HELPERS
    # --------------------------------------------------------------------------

    def get_screen_bounds(self) -> tuple[int, int, int, int]:
        """Returns (x, y, width, height) of primary screen usable desktop geometry."""
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            return geo.x(), geo.y(), geo.width(), geo.height()
        return 0, 0, 1920, 1080

    def get_floor_y(self) -> int:
        """Returns the floor Y coordinate (resting directly above taskbar)."""
        x, y, w, h = self.get_screen_bounds()
        return y + h - self.SPRITE_HEIGHT + 8

    def get_hand_pos(self) -> QPoint:
        """Returns Spidey's hand position relative to SpiderWindow based on current animation state and facing direction."""
        # 1. Use pixel-accurate frame webOrigin from manifest when available
        origin = self.animator.current_web_origin()
        if origin is not None:
            ox = origin.x()
            if self.facing_left:
                ox = self.SPRITE_WIDTH - ox
            return QPoint(int(ox), int(origin.y()))

        # 2. State-specific hand positioning fallback
        state = self.animator.current_state
        if state in ("web_shoot", "shoot"):
            hand = QPoint(int(self.SPRITE_WIDTH * 0.72), int(self.SPRITE_HEIGHT * 0.50))
        elif state in ("web_hang", "web_swing", "swing"):
            hand = QPoint(int(self.SPRITE_WIDTH * 0.50), int(self.SPRITE_HEIGHT * 0.12))
        elif state in ("drag", "work"):
            hand = QPoint(int(self.SPRITE_WIDTH * 0.55), int(self.SPRITE_HEIGHT * 0.40))
        elif state in ("point",):
            hand = QPoint(int(self.SPRITE_WIDTH * 0.75), int(self.SPRITE_HEIGHT * 0.38))
        else:
            hand = QPoint(int(self.SPRITE_WIDTH * 0.50), int(self.SPRITE_HEIGHT * 0.45))

        if self.facing_left:
            return QPoint(self.SPRITE_WIDTH - hand.x(), hand.y())
        return hand

    def get_hand_global_pos(self) -> QPointF:
        """Returns Spidey's hand position in global desktop screen coordinates."""
        local_hand = self.get_hand_pos()
        return QPointF(self.mapToGlobal(local_hand))

    # --------------------------------------------------------------------------
    # CHOREOGRAPHY ENGINE: SWING, WEB-PULL & DRAG
    # --------------------------------------------------------------------------

    def _start_choreography(self, wid: int, action: str, start_coords: tuple, target_coords: tuple) -> None:
        """
        Kicks off high-performance 60 FPS animation sequence for the requested window action.
        """
        # Cancel any active autonomous roaming immediately
        self._cancel_roam()
        self._perch_info = None

        if self._choreo_timer.isActive():
            self._choreo_timer.stop()

        wx, wy, ww, wh = start_coords
        tx, ty, _, _ = target_coords

        self._choreo_state = {
            "wid": wid,
            "action": action,
            "start_coords": start_coords,
            "target_coords": target_coords,
            "frame": 0,
            "total_frames": 45,
            "spidey_start": self.pos(),
        }

        if action == "swing":
            # Caso A: Desplazamiento por balanceo ("swing")
            # 1. Spidey shoots web upward to screen top
            target_spidey_x = wx + ww // 2 - self.width() // 2
            ceiling_x = (self.x() + target_spidey_x) // 2
            self.facing_left = (target_spidey_x < self.x())

            self.web_active = True
            self.web_end_point = QPointF(ceiling_x, 0)
            self.web_start_point = self.get_hand_global_pos()
            self.web_sag = 0.0

            # 2. Change to swing sprite
            self.animator.set_state("web_swing" if "web_swing" in self.animator.animations else "swing")
            self.web_overlay.show()
            self.web_overlay.update()

        elif action == "pull_web":
            # Caso B: Tiroteo y agarre a distancia ("web-pull")
            # 1. Stay in current position, switch to shooting animation
            self.animator.set_state("web_shoot")
            # 2. Shoot web line that hits window title bar
            self.web_active = True
            self.web_start_point = self.get_hand_global_pos()
            self.web_end_point = QPointF(wx + ww // 2, wy + 15)
            self.web_sag = 0.0
            self.web_overlay.show()
            self.web_overlay.update()

        elif action in ("move", "drag"):
            # Caso C: Arrastre físico en ventana ("drag")
            # 1. Position on top window frame with contact edge alignment
            target_spidey_x = wx + ww // 2 - self.width() // 2
            target_spidey_y = wy + 2 if wy <= 115 else wy - 130
            self.move(target_spidey_x, target_spidey_y)
            self.bubble.reposition()
            # 2. Change to push/effort sprite
            self.animator.set_state("work" if "work" in self.animator.animations else "drag")

        elif action == "minimize":
            self.animator.set_state("web_shoot")
            self.web_active = True
            self.web_start_point = self.get_hand_global_pos()
            self.web_end_point = QPointF(wx + ww // 2, wy + 15)
            self.web_sag = 0.0
            self.web_overlay.show()
            self.web_overlay.update()

        elif action in ("maximize", "restore"):
            self.animator.set_state("success" if "success" in self.animator.animations else "wave")

        self._choreo_timer.start(16)

    def _on_choreo_tick(self) -> None:
        """60 FPS choreography tick updating positions, web strings, and window coordinates."""
        if not self._choreo_state:
            self._choreo_timer.stop()
            return

        c = self._choreo_state
        c["frame"] += 1
        frame = c["frame"]
        total = c["total_frames"]
        action = c["action"]
        wid = c["wid"]
        wx, wy, ww, wh = c["start_coords"]
        tx, ty, _, _ = c["target_coords"]

        progress = min(1.0, frame / float(total))

        if action == "swing":
            # Caso A: Pendular swing path
            spidey_start = c["spidey_start"]
            target_spidey_x = wx + ww // 2 - self.width() // 2
            target_spidey_y = wy + 2 if wy <= 115 else wy - 130

            # Arc trajectory
            curr_x = spidey_start.x() + (target_spidey_x - spidey_start.x()) * progress
            arc_sag = 80.0 * math.sin(progress * math.pi)
            curr_y = spidey_start.y() + (target_spidey_y - spidey_start.y()) * progress + arc_sag

            self.move(int(curr_x), int(curr_y))
            self.bubble.reposition()
            self.web_start_point = self.get_hand_global_pos()
            self.web_sag = 12.0 * math.sin(progress * math.pi * 2)
            self.web_overlay.update()

            if progress >= 1.0:
                # 4. Deactivate web upon reaching window frame
                self._finish_choreography("land")

        elif action == "pull_web":
            # Caso B: Web-pull at distance
            # After shooting frame (frame == 6 ~100 ms), switch to pull effort/tension animation
            if frame == 6:
                self.animator.set_state("work" if "work" in self.animator.animations else "drag")

            # Ease-out window motion
            eased = math.sin(progress * math.pi / 2.0)
            curr_wx = int(wx + (tx - wx) * eased)
            curr_wy = int(wy + (ty - wy) * eased)

            # Update window position
            move_window(wid, curr_wx, curr_wy)

            # Keep web attached to title bar frame-by-frame
            self.web_start_point = self.get_hand_global_pos()
            self.web_end_point = QPointF(curr_wx + ww // 2, curr_wy + 15)
            self.web_sag = 18.0 * math.sin(progress * math.pi * 3)
            self.web_overlay.update()

            if progress >= 1.0:
                # 5. Web fades out and Spidey returns to idle
                self._finish_choreography("idle")

        elif action in ("move", "drag"):
            # Caso C: Arrastre físico en ventana ("drag")
            curr_wx = int(wx + (tx - wx) * progress)
            curr_wy = int(wy + (ty - wy) * progress)

            move_window(wid, curr_wx, curr_wy)
            target_spidey_y = curr_wy + 2 if curr_wy <= 115 else curr_wy - 130
            self.move(curr_wx + ww // 2 - self.width() // 2, target_spidey_y)
            self.bubble.reposition()

            if progress >= 1.0:
                self._finish_choreography("idle")

        elif action == "minimize":
            eased = progress * progress
            curr_wx = int(wx + 300 * eased)
            move_window(wid, curr_wx, wy)
            self.web_start_point = self.get_hand_global_pos()
            self.web_end_point = QPointF(curr_wx + ww // 2, wy + 15)
            self.web_overlay.update()

            if progress >= 1.0:
                minimize_window(wid)
                self._finish_choreography("success")

    def _finish_choreography(self, final_state: str = "idle") -> None:
        """Cleans up web line and resets character state."""
        self._choreo_timer.stop()
        self._choreo_state = None
        self.web_active = False
        self.web_start_point = None
        self.web_end_point = None
        self.web_sag = 0.0
        self.web_overlay.hide()
        self.animator.set_state(final_state if final_state in self.animator.animations else "idle")
        self.update()

    # --------------------------------------------------------------------------
    # MOUSE EVENTS: WINDOW DRAGGING & ANIMATION STATE HOOKS
    # --------------------------------------------------------------------------

    def enterEvent(self, event) -> None:
        """When mouse cursor hovers over Spidey, he peeks curiously if idle."""
        super().enterEvent(event)
        if (
            not self.is_roaming_moving
            and not self._choreo_timer.isActive()
            and self._drag_pos is None
            and not self.bubble.isVisible()
        ):
            if self.animator.current_state == "idle":
                self.animator.set_state("peek")
                QTimer.singleShot(2200, lambda: self.animator.set_state("idle") if self.animator.current_state == "peek" else None)

    def leaveEvent(self, event) -> None:
        """Restores idle state when mouse cursor leaves widget."""
        super().leaveEvent(event)
        if self.animator.current_state == "peek":
            self.animator.set_state("idle")

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Captures mouse click position, cancels autonomous roam, and triggers drag animation."""
        self._cancel_roam()
        self._perch_info = None

        if event.button() == Qt.LeftButton:
            # Stop any active choreo sequence if user grabs Spidey
            if self._choreo_timer.isActive():
                self._finish_choreography("drag")

            self._drag_start_pos = event.globalPosition().toPoint()
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self.animator.set_state("drag")
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """Moves window smoothly across the screen; bubble follows along."""
        if event.buttons() == Qt.LeftButton and self._drag_pos is not None:
            new_pos = event.globalPosition().toPoint() - self._drag_pos
            self.move(new_pos)
            self.bubble.reposition()
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """Handles click vs drag release: keeps Spidey in place wherever the user dropped him."""
        if event.button() == Qt.LeftButton:
            drag_start = getattr(self, "_drag_start_pos", None)
            curr_pos = event.globalPosition().toPoint()
            self._drag_pos = None

            dist_moved = 0.0
            if drag_start is not None:
                dist_moved = math.hypot(curr_pos.x() - drag_start.x(), curr_pos.y() - drag_start.y())

            if dist_moved < 6.0:
                # Interactive single click on Spider-Man!
                self._handle_spidey_click()
            else:
                # User dragged Spidey to a specific spot:
                # KEEP SPIDEY IN PLACE WHEREVER HE IS DROPPED!
                screen_x, screen_y, screen_w, screen_h = self.get_screen_bounds()
                floor_y = self.get_floor_y()

                drop_x = max(screen_x + 5, min(screen_x + screen_w - self.SPRITE_WIDTH - 5, self.x()))
                drop_y = max(screen_y + 5, min(floor_y, self.y()))
                self.move(drop_x, drop_y)
                self.bubble.reposition()

                # Contextual pose according to drop location:
                # 1. Close to ceiling (drop_y <= screen_y + 45): latch onto ceiling!
                if drop_y <= screen_y + 45:
                    self.animator.set_state("ceiling_crawl" if random.random() < 0.5 else "web_hang")

                # 2. Close to left or right wall edge: cling to wall in wall_idle!
                elif drop_x <= screen_x + 25:
                    self.facing_left = True
                    self.animator.set_state("wall_idle")
                elif drop_x >= screen_x + screen_w - self.SPRITE_WIDTH - 25:
                    self.facing_left = False
                    self.animator.set_state("wall_idle")

                # 3. Close to floor (drop_y >= floor_y - 20): snap to floor with land squash
                elif drop_y >= floor_y - 20:
                    self.move(drop_x, floor_y)
                    self.animator.set_state("land")
                    QTimer.singleShot(320, lambda: self.animator.set_state("idle") if self.animator.current_state == "land" else None)

                # 4. Anywhere else across desktop space: stay right where dropped!
                else:
                    self.animator.set_state("released")
                    QTimer.singleShot(220, lambda: self.animator.set_state("idle") if self.animator.current_state == "released" else None)

            self.update()
            self.last_user_touch = time.monotonic()
            self.next_roam_time = time.monotonic() + random.uniform(45.0, 90.0)
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        """Double clicking triggers friendly wave and opens speech bubble."""
        self._cancel_roam()
        if "wave" in self.animator.animations:
            self.animator.set_state("wave")
        else:
            self.animator.set_state("web_shoot")
        self.bubble.say("¡Listo para la acción! Lanza tus preguntas científicas o comandos de patrulla.", "")
        event.accept()

    def _handle_spidey_click(self) -> None:
        """Interactive click: wakes up from rest or plays expressive reactive gestures."""
        self._cancel_roam()
        curr = self.animator.current_state

        if curr in ("sleep", "sit"):
            self.animator.set_state("wake")
            QTimer.singleShot(420, lambda: self.animator.set_state("wave"))
            self.bubble.say("¡Uff! Despierto y al 100%. ¿Qué patrullamos hoy en el escritorio?", "")
        else:
            gestures = ["wave", "surprise", "peek", "point", "read", "search"]
            chosen = random.choice([g for g in gestures if g in self.animator.animations])
            self.animator.set_state(chosen)

            quips = {
                "wave": "¡Hola, vecino! Spider-Man al aparato listo para patrullar.",
                "surprise": "¡Mi sentido arácnido vibró! ¿Has hecho clic por una emergencia?",
                "peek": "¡Ojo avizor! Vigilando cada rincón de tus ventanas.",
                "point": "¡Ese icono de ahí parece sospechoso! ¿Lo investigamos?",
                "read": "Revisando mis notas científicas del laboratorio... ¡Dime qué necesitas!",
                "search": "Escaneando el horizonte con mis binoculares arácnidos... ¡Todo despejado!",
            }
            self.bubble.say(quips.get(chosen, "¡Listo para la acción!"), "")

            anim_meta = self.animator.animations.get(chosen, {})
            if anim_meta.get("loop", False):
                QTimer.singleShot(2600, lambda: self.animator.set_state("idle") if self.animator.current_state == chosen else None)

    def _start_gravity_drop(self) -> None:
        """
        Executes signature mid-air release & gravity drop sequence:
        1. 'released' reaction frame in mid-air (~200ms)
        2. 'fall' animation with accelerating downward physics
        3. 'land' impact squash on floor (~350ms)
        4. Smooth return to 'idle'
        """
        self._cancel_roam()
        self.animator.set_state("released" if "released" in self.animator.animations else "fall")

        def _begin_fall():
            if self._drag_pos is not None:
                return  # User grabbed Spidey again
            self.animator.set_state("fall")
            floor_y = self.get_floor_y()
            self.is_roaming_moving = True
            self._current_roam_action = {
                "type": "physics_drop",
                "x": self.x(),
                "vy": 2.5,
                "gravity": 1.5,
                "target_y": floor_y,
            }
            self._roam_motion_timer.start(16)

        QTimer.singleShot(200, _begin_fall)

    def _on_user_typing(self) -> None:
        """When user types into the chat input, Spider-Man listens attentively."""
        if self._choreo_timer.isActive() or self._drag_pos is not None or self.is_roaming_moving:
            return

        # Face towards the speech bubble
        if self.bubble.isVisible():
            self.facing_left = (self.bubble.geometry().center().x() < self.geometry().center().x())

        # Wake up if asleep or resting
        if self.animator.current_state in ("sleep", "sit"):
            self.animator.set_state("wake")
            QTimer.singleShot(420, lambda: self.animator.set_state("listen"))
        elif self.animator.current_state not in ("talk", "work", "web_shoot"):
            self.animator.set_state("listen")

        self._typing_idle_timer.start(3200)

    def _on_typing_idle(self) -> None:
        """If user pauses typing without sending, return to idle."""
        if self.animator.current_state == "listen":
            self.animator.set_state("idle")

    def _on_speech_finished(self) -> None:
        """When typewriter finishes streaming reply text, return smoothly to idle."""
        if self.animator.current_state == "talk":
            QTimer.singleShot(1200, lambda: self.animator.set_state("idle") if self.animator.current_state == "talk" else None)

    def on_bubble_dismissed(self) -> None:
        """When bubble closes, ensure character returns to idle or sits comfortably."""
        if self.animator.current_state in ("talk", "listen", "think"):
            self.animator.set_state("idle")

    def contextMenuEvent(self, event) -> None:
        """Right-click context menu: clean, compact, and organized."""
        menu = QMenu(self)
        menu_style = """
            QMenu {
                background-color: #12101a;
                color: #f5f0fa;
                border: 1px solid #ff2e70;
                padding: 4px;
                font-family: 'Segoe UI';
                font-size: 12px;
            }
            QMenu::item {
                padding: 6px 22px;
                border-radius: 3px;
            }
            QMenu::item:selected {
                background-color: #ff2e70;
                color: #ffffff;
            }
            QMenu::separator {
                height: 1px;
                background-color: rgba(255, 46, 112, 60);
                margin: 4px 8px;
            }
        """
        menu.setStyleSheet(menu_style)

        # 1. Chat interaction
        chat_act = menu.addAction("💬 Hablar con Spider-Man")
        chat_act.triggered.connect(lambda: self.bubble.say("¡Hey! ¿Qué pasa por ese cerebro de genio hoy?", ""))

        menu.addSeparator()

        # 2. Key desktop pet controls
        roam_act = menu.addAction("🕷️ Patrulla autónoma")
        roam_act.setCheckable(True)
        roam_act.setChecked(self.roaming_enabled)
        roam_act.toggled.connect(self._toggle_roaming)

        perch_act = menu.addAction("🧗 Posarse en ventana activa")
        perch_act.triggered.connect(lambda: self.perch_on_window())

        swing_act = menu.addAction("🕸️ Lanzar telaraña y balancearse")
        swing_act.triggered.connect(lambda: self._start_auto_swing())

        floor_act = menu.addAction("⬇️ Bajar a la barra de tareas")
        floor_act.triggered.connect(self._send_to_floor)

        menu.addSeparator()

        # 3. Compact Submenu: Gestos y acrobacias manuales
        poses_menu = menu.addMenu("🎭 Gestos y acrobacias")
        poses_menu.setStyleSheet(menu_style)

        wave_act = poses_menu.addAction("👋 Saludar")
        wave_act.triggered.connect(lambda: self._start_auto_gesture("wave"))

        crawl_act = poses_menu.addAction("🕸️ Avanzar por el techo")
        crawl_act.triggered.connect(self._start_auto_ceiling_crawl)

        climb_act = poses_menu.addAction("🧗 Escalar pared")
        climb_act.triggered.connect(self._start_auto_climb)

        search_act = poses_menu.addAction("🔍 Buscar con binoculares")
        search_act.triggered.connect(lambda: self._start_auto_gesture("search"))

        read_act = poses_menu.addAction("📖 Leer notas científicas")
        read_act.triggered.connect(lambda: self._start_auto_gesture("read"))

        win_act = poses_menu.addAction("⚡ Celebrar victoria")
        win_act.triggered.connect(lambda: self._start_auto_gesture("success"))

        poses_menu.addSeparator()

        rest_act = poses_menu.addAction("☕ Sentarse a descansar")
        rest_act.triggered.connect(lambda: self._start_auto_rest(is_nap=False))

        nap_act = poses_menu.addAction("💤 Echarse una siesta")
        nap_act.triggered.connect(lambda: self._start_auto_rest(is_nap=True))

        menu.addSeparator()

        # 4. Utilities & Exit
        cmd_act = menu.addAction("⚡ Comandas personalizadas...")
        cmd_act.triggered.connect(self._open_commands_dialog)

        quit_act = menu.addAction("❌ Salir")
        quit_act.triggered.connect(self.close)

        menu.exec(event.globalPos())

    def _toggle_roaming(self, enabled: bool) -> None:
        """Toggles the autonomous roaming engine."""
        self.roaming_enabled = enabled
        if not enabled:
            self._cancel_roam()
            self.animator.set_state("idle")

    def _send_to_floor(self) -> None:
        """Smoothly moves Spidey down to rest above the taskbar using dynamic animations without teleportation."""
        self._cancel_roam()
        self._perch_info = None
        floor_y = self.get_floor_y()
        dist_y = floor_y - self.y()

        if abs(dist_y) < 25:
            # Already at floor level: playful hop & land
            self.animator.set_state("jump")
            QTimer.singleShot(220, lambda: self.animator.set_state("land"))
            QTimer.singleShot(750, lambda: self.animator.set_state("idle") if self.animator.current_state == "land" else None)
            return

        if dist_y > 110:
            # High perch / elevated window: dynamic web-swing down to taskbar
            screen_x, screen_y, screen_w, screen_h = self.get_screen_bounds()
            lateral_offset = 80 if self.x() < screen_x + screen_w / 2 else -80
            target_x = max(screen_x + 30, min(screen_x + screen_w - self.SPRITE_WIDTH - 30, self.x() + lateral_offset))
            self._start_auto_swing(custom_target=(target_x, floor_y), final_state="land")
        else:
            # Moderate height: leap down with gravity drop and land
            self.animator.set_state("jump")
            QTimer.singleShot(120, self._start_auto_descend_to_floor)

    def _open_commands_dialog(self) -> None:
        """Opens the custom commands / macros management dialog in a non-blocking floating window."""
        from dialogs.commands_dialog import SpiderCommandsDialog
        if self._commands_dialog is None:
            self._commands_dialog = SpiderCommandsDialog(parent=None)
            self._commands_dialog.command_executed.connect(self._handle_user_submit)
        else:
            self._commands_dialog._refresh_list()
        self._commands_dialog.show()
        self._commands_dialog.raise_()
        self._commands_dialog.activateWindow()

    # --------------------------------------------------------------------------
    # AUTONOMOUS LIFE & ROAMING ENGINE
    # --------------------------------------------------------------------------

    def _cancel_roam(self) -> None:
        """Instantly halts active autonomous motion and resets web lines."""
        if self._roam_motion_timer.isActive():
            self._roam_motion_timer.stop()
        self.is_roaming_moving = False
        self._current_roam_action = None
        if self.web_active and not self._choreo_timer.isActive():
            self.web_active = False
            self.web_start_point = None
            self.web_end_point = None
            self.web_sag = 0.0
            self.web_overlay.hide()
        self.last_user_touch = time.monotonic()
        self.next_roam_time = time.monotonic() + random.uniform(40.0, 80.0)

    def _evaluate_spontaneous_chatter(self) -> None:
        """Periodically triggers organic in-character thoughts, science facts, and PC observations."""
        now = time.monotonic()
        if now < self.next_spontaneous_speech:
            return

        # Do not interrupt active interactions
        if (
            self.bubble.isVisible()
            or self._current_worker is not None
            or self._drag_pos is not None
            or self._choreo_timer.isActive()
        ):
            self.next_spontaneous_speech = now + random.uniform(30.0, 60.0)
            return

        from abilities.care_advisor import get_proactive_advice
        from abilities.spontaneous_talk import get_spontaneous_chatter
        line = get_proactive_advice() or get_spontaneous_chatter()
        if line:
            self.animator.set_state("talk" if "talk" in self.animator.animations else "idle")
            self.bubble.say(line, "")
            self.last_spontaneous_speech = now
            # Next chatter scheduled between 3.5 and 6.5 minutes
            self.next_spontaneous_speech = now + random.uniform(210.0, 390.0)

    def _evaluate_autonomous_roam(self) -> None:
        """
        Main heartbeat of Spider-Man's autonomous life.
        Paced calmly so he rests, perches, or observes without frantic side-to-side pacing.
        Note: Perched window tracking is executed at 60 FPS in _on_anim_tick().
        """
        now = time.monotonic()

        # Check guard conditions: do not roam when user is interacting or busy
        if (
            not self.roaming_enabled
            or self._choreo_timer.isActive()
            or self._drag_pos is not None
            or self.bubble.isVisible()
            or self.is_roaming_moving
        ):
            return

        if now < self.next_roam_time:
            return

        # If perched and perch duration elapsed, hop down
        if self._perch_info is not None:
            self._start_auto_descend_to_floor()
            return

        # Natural, peaceful behavior distribution: sits, perches, gestures, hangs, climbs or crawls
        roll = random.random()

        if roll < 0.28:
            # Sit down or take a restful nap (calm idle state)
            self._start_auto_rest(is_nap=(roll < 0.12))
        elif roll < 0.52:
            # Perch on an open window frame
            if not self._start_auto_perch():
                self._start_auto_gesture()
        elif roll < 0.68:
            # Play a short friendly gesture (read, search, wave, peek, point, surprise)
            self._start_auto_gesture()
        elif roll < 0.78:
            # Web hang upside down
            self._start_auto_hang()
        elif roll < 0.88:
            # Ceiling crawl or wall climb
            if roll < 0.83:
                self._start_auto_ceiling_crawl()
            else:
                self._start_auto_climb()
        else:
            # Walk or run across the floor with dynamic skid braking
            self._start_auto_walk()

    def _update_perch_follow(self) -> None:
        """
        High-frequency synchronous window tracking engine (60 FPS, 0 ms latency).
        Smoothly follows window dragging without teleportation and plays reactive
        riding/effort animations when the window is dragged across the screen.
        """
        if not self._perch_info:
            return

        now = time.monotonic()
        if now >= self._perch_info.get("perch_until", 0):
            self._start_auto_descend_to_floor()
            return

        wid = self._perch_info["wid"]
        bounds = None

        if sys.platform == "win32":
            try:
                import ctypes
                user32 = ctypes.windll.user32
                if not user32.IsWindow(wid) or user32.IsIconic(wid) or not user32.IsWindowVisible(wid):
                    self._start_auto_descend_to_floor()
                    return
                from abilities.window_manager import _get_window_bounds_win32
                bounds = _get_window_bounds_win32(wid)
            except Exception:
                bounds = None
        else:
            from abilities.window_manager import get_active_or_target_window
            target = get_active_or_target_window("")
            if target and target[0] == wid:
                bounds = target[1]

        if not bounds:
            self._start_auto_descend_to_floor()
            return

        wx, wy, ww, wh = bounds

        # If window collapsed or closed to zero geometry
        if ww < 150 or wh < 100:
            self._start_auto_descend_to_floor()
            return

        target_x = wx + self._perch_info["rel_x"]
        target_y = wy + self._perch_info["rel_y"]

        curr_x = self.x()
        curr_y = self.y()
        dx = target_x - curr_x
        dy = target_y - curr_y
        dist = math.hypot(dx, dy)

        if dist >= 1.0:
            # Immediate zero-lag physical displacement
            self.move(int(target_x), int(target_y))
            self.bubble.reposition()

            # Dynamic reactive animation when user drags the window with velocity
            if dist >= 2.8:
                self._perch_info["last_drag_time"] = now
                if dx < -1.5:
                    self.facing_left = True
                elif dx > 1.5:
                    self.facing_left = False

                # Switch to active clinging/effort animation while riding window
                clinging = "work" if "work" in self.animator.animations else ("drag" if "drag" in self.animator.animations else "climb")
                if self.animator.current_state != clinging and self.animator.current_state not in ("talk", "think"):
                    self.animator.set_state(clinging)
        else:
            # Window is stationary: after slight deceleration buffer, return to relaxed sitting posture
            last_drag = self._perch_info.get("last_drag_time", 0.0)
            if now - last_drag > 0.16:
                settled = self._perch_info.get("settled_state", "sit")
                if self.animator.current_state not in (settled, "sleep", "talk", "think"):
                    self.animator.set_state(settled)

    def _start_auto_walk(self) -> None:
        """Walks or runs along the desktop floor/taskbar, or swings across if elevated."""
        screen_x, screen_y, screen_w, screen_h = self.get_screen_bounds()
        floor_y = self.get_floor_y()
        current_x = self.x()

        # If Spidey is positioned in mid-air (not on the floor), swing or crawl across instead of dropping
        if abs(self.y() - floor_y) > 40 and self._perch_info is None:
            if self.y() <= screen_y + 60:
                self._start_auto_ceiling_crawl()
            else:
                target_x = random.randint(screen_x + 60, screen_x + screen_w - self.SPRITE_WIDTH - 60)
                self._start_auto_swing(custom_target=(target_x, self.y()), final_state="idle")
            return

        min_x = screen_x + 20
        max_x = screen_x + screen_w - self.SPRITE_WIDTH - 20
        target_x = random.randint(min_x, max_x)

        dist = target_x - current_x
        if abs(dist) < 50:
            self.next_roam_time = time.monotonic() + random.uniform(35.0, 70.0)
            return

        is_running = abs(dist) > 300
        speed = 5.0 if is_running else 3.0
        self.facing_left = (dist < 0)

        anim_state = "run" if is_running else "walk"
        self.animator.set_state(anim_state)
        self.is_roaming_moving = True

        self._current_roam_action = {
            "type": "walk",
            "start_x": current_x,
            "target_x": target_x,
            "y": floor_y,
            "speed": speed if dist > 0 else -speed,
        }
        self._roam_motion_timer.start(16)

    def _start_auto_swing(
        self,
        custom_target: tuple[int, int] | None = None,
        final_state: str | None = None,
    ) -> None:
        """Launches dynamic web swing across the desktop with pendular arc."""
        screen_x, screen_y, screen_w, screen_h = self.get_screen_bounds()
        floor_y = self.get_floor_y()
        start_pt = self.pos()

        if custom_target:
            target_x, target_y = custom_target
        else:
            if start_pt.x() < screen_x + screen_w / 2:
                target_x = random.randint(int(screen_x + screen_w * 0.55), int(screen_x + screen_w - self.SPRITE_WIDTH - 40))
            else:
                target_x = random.randint(int(screen_x + 40), int(screen_x + screen_w * 0.45))

            # If Spidey is positioned off the floor, swing between desktop altitudes
            if abs(start_pt.y() - floor_y) > 50 and self._perch_info is None:
                target_y = random.randint(screen_y + 100, max(screen_y + 110, floor_y - 60))
            else:
                target_y = floor_y

        dist = target_x - start_pt.x()
        self.facing_left = (dist < 0)

        anchor_x = (start_pt.x() + target_x) / 2.0
        anchor_y = float(screen_y)

        self.web_active = True
        self.web_end_point = QPointF(anchor_x, anchor_y)
        self.web_start_point = self.get_hand_global_pos()
        self.web_sag = 0.0
        self.web_overlay.show()
        self.web_overlay.update()

        self.animator.set_state("web_swing")
        self.is_roaming_moving = True

        total_frames = max(35, min(65, int(abs(dist) / 10)))

        if final_state is None:
            final_state = "land" if target_y >= floor_y - 20 else "idle"

        self._current_roam_action = {
            "type": "swing",
            "start_x": start_pt.x(),
            "start_y": start_pt.y(),
            "target_x": target_x,
            "target_y": target_y,
            "frame": 0,
            "total_frames": total_frames,
            "final_state": final_state,
        }
        self._roam_motion_timer.start(16)

    def _start_auto_hang(self) -> None:
        """Shoots a web straight up to ceiling and hangs upside down on patrol."""
        screen_x, screen_y, screen_w, screen_h = self.get_screen_bounds()
        start_pt = self.pos()

        anchor_x = float(start_pt.x() + self.SPRITE_WIDTH // 2)
        anchor_y = float(screen_y)

        self.web_active = True
        self.web_end_point = QPointF(anchor_x, anchor_y)
        self.web_start_point = self.get_hand_global_pos()
        self.web_sag = 0.0
        self.web_overlay.show()
        self.web_overlay.update()

        target_y = random.randint(screen_y + 100, screen_y + 240)
        self.animator.set_state("web_shoot")
        self.is_roaming_moving = True

        self._current_roam_action = {
            "type": "hang",
            "phase": "pull_up",
            "start_x": start_pt.x(),
            "start_y": start_pt.y(),
            "target_y": target_y,
            "anchor_x": anchor_x,
            "frame": 0,
            "pull_frames": 25,
            "hang_until": time.monotonic() + random.uniform(5.0, 9.0),
        }
        self._roam_motion_timer.start(16)

    def perch_on_window(self, wid: int = 0, coords: Optional[tuple] = None) -> bool:
        """
        Actively targets a specific or topmost desktop window and performs a
        realistic swing/leap to sit on its upper ledge with pixel-accurate contact alignment.
        """
        try:
            self._cancel_roam()
            self._perch_info = None

            if not coords or not wid:
                from abilities.window_manager import get_topmost_app_window
                exclude = {int(self.winId()), int(self.bubble.winId()), int(self.web_overlay.winId())}
                top = get_topmost_app_window(exclude_hwnds=exclude)
                if not top:
                    return False
                wid, title, (wx, wy, ww, wh) = top
            else:
                wx, wy, ww, wh = coords

            if ww < 220 or wh < 180 or wy < -80:
                return False

            screen_x, screen_y, screen_w, screen_h = self.get_screen_bounds()

            # Contact alignment:
            # Sprite 128x128 is centered at (0, 10) inside the 140x160 widget.
            # Feet contact line is at Y = 131 in widget coordinates.
            # Top-edge perch: perch_y = wy - 130 places Spidey's feet squarely on top of the window frame.
            # For windows touching or snapped to screen ceiling, sit inside top bar safely.
            if wy <= screen_y + 115:
                perch_y = max(screen_y + 2, wy + 2)
                settled_state = "sit"
            else:
                perch_y = wy - 130
                settled_state = "sit"

            # Avoid caption control buttons (Minimize, Maximize, Close occupy rightmost ~160px)
            left_margin = wx + 50
            right_margin = max(left_margin, wx + ww - self.SPRITE_WIDTH - 150)
            if right_margin > left_margin:
                perch_x = random.randint(left_margin, right_margin)
            else:
                perch_x = wx + max(10, (ww - self.SPRITE_WIDTH) // 2)

            self._perch_info = {
                "wid": wid,
                "rel_x": perch_x - wx,
                "rel_y": perch_y - wy,
                "perch_until": time.monotonic() + random.uniform(30.0, 60.0),
                "last_drag_time": 0.0,
                "settled_state": settled_state,
            }
            self._start_auto_swing(custom_target=(perch_x, perch_y), final_state=settled_state)
            return True
        except Exception as err:
            print(f"[perch] Error: {err}")
            return False

    def _start_auto_perch(self) -> bool:
        """Autonomous roaming hook: finds topmost window and perches."""
        return self.perch_on_window()

    def _start_auto_descend_to_floor(self) -> None:
        """Jumps down from perched window or elevated ledge to the screen floor."""
        self._perch_info = None
        floor_y = self.get_floor_y()
        if abs(self.y() - floor_y) < 20:
            return

        self.animator.set_state("fall")
        self.is_roaming_moving = True
        self._current_roam_action = {
            "type": "drop_to_floor",
            "start_x": self.x(),
            "start_y": self.y(),
            "target_y": floor_y,
            "frame": 0,
            "total_frames": 22,
        }
        self._roam_motion_timer.start(16)

    def _start_auto_rest(self, is_nap: bool = False) -> None:
        """Sits down or takes a nap when bored or resting."""
        state = "sleep" if is_nap else "sit"
        self.animator.set_state(state)
        rest_duration = random.uniform(50.0, 110.0) if is_nap else random.uniform(30.0, 70.0)
        self.next_roam_time = time.monotonic() + rest_duration + random.uniform(15.0, 30.0)
        QTimer.singleShot(int(rest_duration * 1000), self._wake_up_from_rest)

    def _wake_up_from_rest(self) -> None:
        """Wakes Spidey up from sitting or sleep back to idle."""
        if self.animator.current_state in ("sleep", "sit") and not self._drag_pos and not self.bubble.isVisible():
            self.animator.set_state("wake")

    def _start_auto_ceiling_crawl(self) -> None:
        """Shoots a web to ceiling, zips up, crawls horizontally along desktop ceiling, and drops down."""
        self._cancel_roam()
        screen_x, screen_y, screen_w, screen_h = self.get_screen_bounds()
        start_pt = self.pos()

        anchor_x = float(start_pt.x() + self.SPRITE_WIDTH // 2)
        anchor_y = float(screen_y)

        self.web_active = True
        self.web_end_point = QPointF(anchor_x, anchor_y)
        self.web_start_point = self.get_hand_global_pos()
        self.web_sag = 0.0
        self.web_overlay.show()
        self.web_overlay.update()

        target_crawl_y = screen_y + 2
        self.animator.set_state("web_shoot")
        self.is_roaming_moving = True

        crawl_dir = -1 if start_pt.x() > screen_x + screen_w // 2 else 1
        crawl_dist = random.randint(180, 320) * crawl_dir
        target_crawl_x = max(screen_x + 30, min(screen_x + screen_w - self.SPRITE_WIDTH - 30, start_pt.x() + crawl_dist))

        self.facing_left = (crawl_dist < 0)

        self._current_roam_action = {
            "type": "ceiling_crawl_sequence",
            "phase": "pull_up",
            "start_x": start_pt.x(),
            "start_y": start_pt.y(),
            "target_crawl_y": target_crawl_y,
            "target_crawl_x": target_crawl_x,
            "crawl_speed": 3.0 if crawl_dist > 0 else -3.0,
            "frame": 0,
            "pull_frames": 22,
        }
        self._roam_motion_timer.start(16)

    def _start_auto_climb(self) -> None:
        """Scales the side border of the screen, clings in wall_idle, and climbs down."""
        self._cancel_roam()
        screen_x, screen_y, screen_w, screen_h = self.get_screen_bounds()
        floor_y = self.get_floor_y()

        is_left = self.x() < screen_x + screen_w // 2
        edge_x = screen_x + 8 if is_left else screen_x + screen_w - self.SPRITE_WIDTH - 8
        self.facing_left = is_left

        climb_target_y = max(screen_y + 120, floor_y - 320)
        self.move(edge_x, floor_y)
        self.animator.set_state("climb")
        self.is_roaming_moving = True

        self._current_roam_action = {
            "type": "climb_sequence",
            "phase": "climbing_up",
            "edge_x": edge_x,
            "start_y": floor_y,
            "target_y": climb_target_y,
            "speed_y": -3.0,
            "climb_until": 0.0,
        }
        self._roam_motion_timer.start(16)

    def _start_auto_gesture(self, specific_gesture: str | None = None) -> None:
        """Plays friendly gestures like waving, peeking, pointing, reading or scouting."""
        gestures = ["wave", "peek", "point", "surprise", "read", "search", "success"]
        available = [g for g in gestures if g in self.animator.animations]
        chosen = specific_gesture if (specific_gesture and specific_gesture in self.animator.animations) else (random.choice(available) if available else "wave")
        self.animator.set_state(chosen)
        anim_meta = self.animator.animations.get(chosen, {})
        if anim_meta.get("loop", False):
            gesture_dur = random.uniform(2.5, 4.0)
            QTimer.singleShot(
                int(gesture_dur * 1000),
                lambda: self.animator.set_state("idle") if self.animator.current_state == chosen else None
            )
        self.next_roam_time = time.monotonic() + random.uniform(40.0, 80.0)

    def _finish_roam_motion(self, final_state: str = "idle") -> None:
        """Concludes active roam motion and transitions animation state."""
        self._roam_motion_timer.stop()
        self.is_roaming_moving = False
        self._current_roam_action = None
        self.animator.set_state(final_state)
        self.update()

    def _on_roam_motion_tick(self) -> None:
        """60 FPS tick handling coordinate interpolation during autonomous motion."""
        if not self._current_roam_action or not self.is_roaming_moving:
            self._roam_motion_timer.stop()
            self.is_roaming_moving = False
            return

        c = self._current_roam_action
        action_type = c["type"]

        if action_type == "walk":
            curr_x = self.x() + c["speed"]
            target_x = c["target_x"]
            reached = (c["speed"] > 0 and curr_x >= target_x) or (c["speed"] < 0 and curr_x <= target_x)
            if reached:
                self.move(int(target_x), int(c["y"]))
                self.animator.set_state("brake")
                self._roam_motion_timer.stop()
                self.is_roaming_moving = False
                self._current_roam_action = None
                QTimer.singleShot(400, lambda: self.animator.set_state("idle") if self.animator.current_state == "brake" else None)
                self.next_roam_time = time.monotonic() + random.uniform(45.0, 90.0)
            else:
                self.move(int(curr_x), int(c["y"]))

        elif action_type == "physics_drop":
            c["vy"] += c["gravity"]
            new_y = self.y() + c["vy"]
            if new_y >= c["target_y"]:
                self.move(int(c["x"]), int(c["target_y"]))
                self._finish_roam_motion("land")
                QTimer.singleShot(350, lambda: self.animator.set_state("idle") if self.animator.current_state == "land" else None)
                self.next_roam_time = time.monotonic() + random.uniform(40.0, 80.0)
            else:
                self.move(int(c["x"]), int(new_y))

        elif action_type == "ceiling_crawl_sequence":
            phase = c["phase"]
            if phase == "pull_up":
                c["frame"] += 1
                prog = min(1.0, c["frame"] / c["pull_frames"])
                curr_y = c["start_y"] + (c["target_crawl_y"] - c["start_y"]) * math.sin(prog * math.pi / 2.0)
                self.move(int(c["start_x"]), int(curr_y))
                self.web_start_point = self.get_hand_global_pos()
                self.web_overlay.update()
                if prog >= 1.0:
                    c["phase"] = "crawling"
                    self.web_active = False
                    self.web_overlay.hide()
                    self.animator.set_state("ceiling_crawl")

            elif phase == "crawling":
                curr_x = self.x() + c["crawl_speed"]
                target_x = c["target_crawl_x"]
                reached = (c["crawl_speed"] > 0 and curr_x >= target_x) or (c["crawl_speed"] < 0 and curr_x <= target_x)
                if reached:
                    self.move(int(target_x), int(c["target_crawl_y"]))
                    c["phase"] = "drop_down"
                    self.animator.set_state("fall")
                    c["drop_start_y"] = self.y()
                    c["drop_target_y"] = self.get_floor_y()
                    c["drop_frame"] = 0
                    c["drop_total"] = 24
                else:
                    self.move(int(curr_x), int(c["target_crawl_y"]))

            elif phase == "drop_down":
                c["drop_frame"] += 1
                prog = min(1.0, c["drop_frame"] / c["drop_total"])
                curr_y = c["drop_start_y"] + (c["drop_target_y"] - c["drop_start_y"]) * (prog * prog)
                self.move(int(self.x()), int(curr_y))
                if prog >= 1.0:
                    self._finish_roam_motion("land")
                    QTimer.singleShot(350, lambda: self.animator.set_state("idle") if self.animator.current_state == "land" else None)
                    self.next_roam_time = time.monotonic() + random.uniform(45.0, 90.0)

        elif action_type == "climb_sequence":
            phase = c["phase"]
            if phase == "climbing_up":
                curr_y = self.y() + c["speed_y"]
                if curr_y <= c["target_y"]:
                    self.move(int(c["edge_x"]), int(c["target_y"]))
                    c["phase"] = "wall_clinging"
                    self.animator.set_state("wall_idle")
                    c["climb_until"] = time.monotonic() + random.uniform(3.0, 5.0)
                else:
                    self.move(int(c["edge_x"]), int(curr_y))

            elif phase == "wall_clinging":
                if time.monotonic() >= c["climb_until"]:
                    c["phase"] = "climbing_down"
                    self.animator.set_state("climb_down" if "climb_down" in self.animator.animations else "climb")

            elif phase == "climbing_down":
                curr_y = self.y() - c["speed_y"]
                floor_y = self.get_floor_y()
                if curr_y >= floor_y:
                    self.move(int(c["edge_x"]), int(floor_y))
                    self._finish_roam_motion("land")
                    QTimer.singleShot(350, lambda: self.animator.set_state("idle") if self.animator.current_state == "land" else None)
                    self.next_roam_time = time.monotonic() + random.uniform(45.0, 90.0)
                else:
                    self.move(int(c["edge_x"]), int(curr_y))

        elif action_type == "swing":
            c["frame"] += 1
            prog = min(1.0, c["frame"] / c["total_frames"])

            curr_x = c["start_x"] + (c["target_x"] - c["start_x"]) * prog
            arc_sag = 95.0 * math.sin(prog * math.pi)
            curr_y = c["start_y"] + (c["target_y"] - c["start_y"]) * prog + arc_sag

            self.move(int(curr_x), int(curr_y))
            self.web_start_point = self.get_hand_global_pos()
            self.web_sag = 12.0 * math.sin(prog * math.pi * 2)
            self.web_overlay.update()

            if prog >= 1.0:
                self.web_active = False
                self.web_overlay.hide()
                self._finish_roam_motion(c.get("final_state", "idle"))
                self.next_roam_time = time.monotonic() + random.uniform(50.0, 95.0)

        elif action_type == "hang":
            phase = c["phase"]
            if phase == "pull_up":
                c["frame"] += 1
                prog = min(1.0, c["frame"] / c["pull_frames"])
                curr_y = c["start_y"] + (c["target_y"] - c["start_y"]) * math.sin(prog * math.pi / 2.0)
                self.move(int(c["start_x"]), int(curr_y))
                self.web_start_point = self.get_hand_global_pos()
                self.web_overlay.update()
                if prog >= 1.0:
                    c["phase"] = "hanging"
                    self.animator.set_state("web_hang")

            elif phase == "hanging":
                sway = 4.0 * math.sin(time.monotonic() * 2.0)
                self.move(int(c["start_x"] + sway), int(c["target_y"]))
                self.web_start_point = self.get_hand_global_pos()
                self.web_overlay.update()
                if time.monotonic() >= c["hang_until"]:
                    c["phase"] = "dropping"
                    self.web_active = False
                    self.web_overlay.hide()
                    self.animator.set_state("fall")
                    c["drop_start_y"] = self.y()
                    c["drop_target_y"] = self.get_floor_y()
                    c["drop_frame"] = 0
                    c["drop_total"] = 22

            elif phase == "dropping":
                c["drop_frame"] += 1
                prog = min(1.0, c["drop_frame"] / c["drop_total"])
                curr_y = c["drop_start_y"] + (c["drop_target_y"] - c["drop_start_y"]) * (prog * prog)
                self.move(int(c["start_x"]), int(curr_y))
                if prog >= 1.0:
                    self._finish_roam_motion("land")
                    self.next_roam_time = time.monotonic() + random.uniform(45.0, 90.0)

        elif action_type == "drop_to_floor":
            c["frame"] += 1
            prog = min(1.0, c["frame"] / c["total_frames"])
            curr_y = c["start_y"] + (c["target_y"] - c["start_y"]) * (prog * prog)
            self.move(int(c["start_x"]), int(curr_y))
            if prog >= 1.0:
                self._finish_roam_motion("land")
                self.next_roam_time = time.monotonic() + random.uniform(45.0, 90.0)

    # --------------------------------------------------------------------------
    # PAINT EVENT: SPRITE & LOCAL WEB RENDERING
    # --------------------------------------------------------------------------

    def paintEvent(self, event: QPaintEvent) -> None:
        """
        Renders the current sprite frame with crisp pixel-art scaling
        and draws local elastic web line using QPainterPath and QPen(QColor(240, 240, 255, 230), 2).
        Applies horizontal flipping when moving or facing left.
        """
        painter = QPainter(self)

        # 1. Local web rendering within pet widget boundaries
        if (
            self.web_active
            and self.web_start_point is not None
            and self.web_end_point is not None
        ):
            local_start = QPointF(self.mapFromGlobal(self.web_start_point.toPoint()))
            local_end = QPointF(self.mapFromGlobal(self.web_end_point.toPoint()))
            draw_dynamic_web(painter, local_start, local_end, self.web_sag)

        # 2. Pixel-art sprite rendering
        pix = self.animator.current_pixmap()
        if pix and not pix.isNull():
            # Nearest-neighbor scaling keeps pixel art sharp
            painter.setRenderHint(QPainter.Antialiasing, False)

            # Center pixmap preserving aspect ratio
            scaled = pix.scaled(
                self.SPRITE_WIDTH,
                self.SPRITE_HEIGHT,
                Qt.KeepAspectRatio,
                Qt.FastTransformation
            )

            # Directional horizontal flipping
            if self.facing_left:
                scaled = scaled.transformed(QTransform().scale(-1, 1))

            offset_x = (self.SPRITE_WIDTH - scaled.width()) / 2
            offset_y = (self.SPRITE_HEIGHT - scaled.height()) / 2
            painter.drawPixmap(round(offset_x), round(offset_y), scaled)

        else:
            # Fallback placeholder if sprites are missing
            painter.setRenderHint(QPainter.Antialiasing, True)
            sprite_rect = QRectF(5, 5, self.SPRITE_WIDTH - 10, self.SPRITE_HEIGHT - 10)
            painter.setBrush(QColor(220, 20, 60, 160))
            painter.setPen(QPen(QColor(0, 255, 204), 2))
            painter.drawRoundedRect(sprite_rect, 12, 12)

            painter.setPen(QColor(255, 255, 255))
            painter.setFont(QFont("Segoe UI", 9, QFont.Bold))
            painter.drawText(sprite_rect, Qt.AlignCenter, "[ Spider-Man ]\n(Click to chat)")

        painter.end()

    def moveEvent(self, event) -> None:
        """Synchronizes speech bubble coordinates during movement."""
        super().moveEvent(event)
        self.bubble.reposition()

    def closeEvent(self, event) -> None:
        """Ensures memory is cleanly saved, overlays closed, model unloaded and timers stopped."""
        self.anim_timer.stop()
        if hasattr(self, "_chatter_timer"):
            self._chatter_timer.stop()
        self._choreo_timer.stop()
        self._roam_eval_timer.stop()
        self._roam_motion_timer.stop()
        if hasattr(self, "_typing_idle_timer"):
            self._typing_idle_timer.stop()
        if self._current_worker and self._current_worker.isRunning():
            self._current_worker.terminate()
            self._current_worker.wait(200)
        if self._commands_dialog:
            self._commands_dialog.close()
        self.web_overlay.close()
        self.bubble.close()
        self.brain.save_memory()
        self.brain.unload_model()
        event.accept()

    def _cancel_active_tasks(self) -> None:
        """Instant Asides halt: aborts ongoing background worker, choreo, and roaming."""
        aborted = False
        if self._current_worker and self._current_worker.isRunning():
            self._current_worker.terminate()
            self._current_worker = None
            aborted = True

        if self._choreo_timer.isActive():
            self._finish_choreography("idle")
            aborted = True

        if self.is_roaming_moving:
            self._cancel_roam()
            aborted = True

        self.animator.set_state("brake" if "brake" in self.animator.animations else "idle")
        if aborted:
            self.bubble.say("¡Frenada en seco! Misión abortada a tu orden.", "")

    def keyPressEvent(self, event) -> None:
        """Global key event interceptor: Esc key aborts current tasks / inference."""
        if event.key() == Qt.Key_Escape:
            self._cancel_active_tasks()
            event.accept()
            return
        super().keyPressEvent(event)

    # --------------------------------------------------------------------------
    # CHAT SUBMISSION & BRAIN INTERACTION
    # --------------------------------------------------------------------------

    def _handle_user_submit(self, user_text: str) -> None:
        """Submits user text to SpiderBrain asynchronously with Aside interruption support."""
        user_text = user_text.strip()
        if not user_text:
            return

        # ASIDES INTERCEPTOR: Handle interruption / progress queries while brain is actively working
        if self._current_worker and self._current_worker.isRunning():
            clean_low = user_text.lower().strip(" .!?¿¡")
            if clean_low in ("para", "stop", "cancela", "cancelar", "detente", "deténte", "cállate", "basta", "quiet"):
                self._current_worker.terminate()
                self._current_worker = None
                self.animator.set_state("idle")
                self.bubble.say("¡Cancelado de inmediato! A tus órdenes, socio.", "")
                return
            if clean_low in ("cómo vas", "¿cómo vas?", "que haces", "qué haces", "¿qué haces?", "progreso", "status"):
                self.bubble.say("Sigo calculando las coordenadas y procesando la tarea, ¡dame un segundo!", "")
                return

        # Cancel any active autonomous roaming immediately
        self._cancel_roam()
        self._perch_info = None

        # Check for exit / termination keywords
        if user_text.lower() in ("exit", "quit", "q"):
            print(f"\nYou: {user_text}")
            print("\nSpidey: Running out of web fluid! Stay safe out there, partner.\n")
            self.brain.save_memory()
            self.web_overlay.close()
            self.bubble.close()
            QApplication.quit()
            return

        print(f"\nYou: {user_text}")

        # Check if user prompt is a native system action or tool invocation
        from brain import _detect_action_intent
        action_intent = _detect_action_intent(user_text)
        if action_intent:
            fn_name = action_intent.function.name
            args = action_intent.function.arguments if hasattr(action_intent.function, "arguments") else {}
            if isinstance(args, str):
                try:
                    import json
                    args = json.loads(args)
                except Exception:
                    args = {}

            # Expressive animations & immediate visual feedback
            if fn_name in ("abrir_aplicacion", "open_app", "launch_app"):
                app_target = (args.get("app_name") or args.get("app") or "la aplicación").capitalize()
                self.animator.set_state("web_shoot")
                QTimer.singleShot(480, lambda: self.animator.set_state("work") if self.animator.current_state in ("web_shoot", "web_hang") else None)
                self.bubble.action_notice(f"🕸️ ¡Lanzando telaraña para abrir {app_target} en ventana!...", user_prompt=user_text)

            elif fn_name in ("browser_search", "web_search"):
                q_target = args.get("query") or args.get("q") or "la red"
                b_target = (args.get("browser") or "el navegador").capitalize()
                self.animator.set_state("search")
                QTimer.singleShot(900, lambda: self.animator.set_state("work") if self.animator.current_state == "search" else None)
                self.bubble.action_notice(f"🔍 ¡Entrando a {b_target} para buscar '{q_target}'!...", user_prompt=user_text)

            elif fn_name in ("open_website",):
                q_target = args.get("query") or args.get("q") or "la web"
                b_target = (args.get("browser") or "el navegador").capitalize()
                self.animator.set_state("web_shoot")
                QTimer.singleShot(480, lambda: self.animator.set_state("work") if self.animator.current_state in ("web_shoot", "web_hang") else None)
                self.bubble.action_notice(f"🕸️ ¡Entrando a {b_target} en ventana!...", user_prompt=user_text)

            elif fn_name in ("open_folder", "abrir_carpeta"):
                f_target = (args.get("target") or "el Explorador").capitalize()
                self.animator.set_state("web_shoot")
                QTimer.singleShot(480, lambda: self.animator.set_state("work") if self.animator.current_state in ("web_shoot", "web_hang") else None)
                self.bubble.action_notice(f"📂 ¡Abriendo la carpeta {f_target} en el Explorador!...", user_prompt=user_text)

            elif fn_name in ("list_folder", "listar_carpeta"):
                f_target = (args.get("target") or "la carpeta").capitalize()
                self.animator.set_state("read")
                self.bubble.action_notice(f"🔍 ¡Inspeccionando los archivos de {f_target}!...", user_prompt=user_text)

            elif fn_name in ("find_files", "buscar_archivos"):
                q_file = args.get("query") or "archivo"
                self.animator.set_state("search")
                QTimer.singleShot(900, lambda: self.animator.set_state("work") if self.animator.current_state == "search" else None)
                self.bubble.action_notice(f"🕸️ ¡Rastreando '{q_file}' en tus carpetas y discos!...", user_prompt=user_text)

            elif fn_name in ("care_advice", "consejo", "sentido_aracnido"):
                self.animator.set_state("point")
                self.bubble.action_notice("🕷️ ¡Calibrando sentido arácnido y revisando el estado del equipo!...", user_prompt=user_text)

            elif fn_name in ("manage_files", "read_file", "summarize"):
                self.animator.set_state("read")
                self.bubble.action_notice("📖 ¡Inspeccionando y leyendo archivos del sistema!...", user_prompt=user_text)

            elif fn_name in ("look_at_screen", "take_screenshot"):
                self.animator.set_state("peek")
                self.bubble.action_notice("👀 ¡Echando un vistazo arácnido a tu pantalla!...", user_prompt=user_text)

            elif fn_name in ("run_custom_command", "execute_custom_command"):
                cmd_name = args.get("name") or "comanda"
                self.animator.set_state("work")
                self.bubble.action_notice(f"⚡ ¡Ejecutando comanda '{cmd_name}' a toda mecha!...", user_prompt=user_text)

            elif fn_name in ("perch_window", "perch"):
                self.animator.set_state("jump")
                self.bubble.action_notice("🕷️ ¡Subiendo a posarme en la ventana!...", user_prompt=user_text)

            elif fn_name in ("set_volume", "adjust_volume"):
                self.animator.set_state("point")
                self.bubble.action_notice("🔊 ¡Ajustando los decibelios del sistema!...", user_prompt=user_text)

            else:
                self.animator.set_state("work")
                self.bubble.action_notice("🕸️ ¡Marchando orden en el sistema!...", user_prompt=user_text)
        else:
            # General conversation: expressively react with Spidey personality animations
            lowered = user_text.lower().strip()
            if any(w in lowered for w in ("hola", "buenas", "hey", "saludos", "buenos días", "buenas tardes")):
                self.animator.set_state("wave")
                QTimer.singleShot(650, lambda: self.animator.set_state("think") if self.animator.current_state == "wave" else None)
            elif any(w in lowered for w in ("!", "wow", "increible", "increíble", "socorro", "cuidado", "alerta", "ojo", "sentido arácnido", "spidey sense")):
                self.animator.set_state("surprise")
                QTimer.singleShot(600, lambda: self.animator.set_state("think") if self.animator.current_state == "surprise" else None)
            elif any(w in lowered for w in ("busca", "encuentra", "dónde", "donde", "investiga", "averigua", "google")):
                self.animator.set_state("search")
                QTimer.singleShot(900, lambda: self.animator.set_state("think") if self.animator.current_state == "search" else None)
            elif any(w in lowered for w in ("ecuación", "ecuacion", "fórmula", "formula", "física", "fisica", "química", "quimica", "apuntes", "lee", "leer", "libro", "peter parker", "estudio")):
                self.animator.set_state("read")
                QTimer.singleShot(900, lambda: self.animator.set_state("think") if self.animator.current_state == "read" else None)
            elif any(w in lowered for w in ("a dormir", "buenas noches", "descansa", "siesta", "dormir")):
                self.animator.set_state("sleep")
            elif any(w in lowered for w in ("despierta", "arriba", "despiértate", "vamos")):
                self.animator.set_state("wake")
                QTimer.singleShot(450, lambda: self.animator.set_state("wave"))
            elif any(w in lowered for w in ("gracias", "genial", "crack", "buen trabajo", "excelente", "bien hecho", "perfecto")):
                self.animator.set_state("success")
                QTimer.singleShot(750, lambda: self.animator.set_state("think") if self.animator.current_state == "success" else None)
            else:
                self.animator.set_state("think")

            self.bubble.think(user_prompt=user_text)

        # Safely terminate any prior worker before launching new inference
        if self._current_worker and self._current_worker.isRunning():
            self._current_worker.terminate()
            self._current_worker.wait(100)

        # Launch inference in background thread
        self._current_worker = BrainWorker(self.brain, user_text)
        self._current_worker.reply_ready.connect(self._on_brain_reply)
        self._current_worker.error_occurred.connect(self._on_brain_error)
        self._current_worker.start()

    def _on_brain_reply(self, reply: str, user_text: str) -> None:
        """Receives completed reply from worker thread and streams via SpiderBubble."""
        print(f"Spidey: {reply}\n")
        lowered = user_text.lower()
        from brain import _detect_action_intent
        action_intent = _detect_action_intent(user_text)
        is_praise = any(w in lowered for w in ("gracias", "genial", "crack", "bien hecho", "perfecto", "buena", "excelente"))
        if (action_intent or is_praise) and "error" not in reply.lower():
            self.animator.set_state("success")
            QTimer.singleShot(700, lambda: self.animator.set_state("talk") if self.animator.current_state == "success" else None)
        else:
            self.animator.set_state("talk")
        self.bubble.say(reply, user_prompt=user_text)

    def _on_brain_error(self, err_msg: str) -> None:
        """Handles unexpected errors during inference."""
        print(f"[Error] Inference failed: {err_msg}\n")
        self.animator.set_state("error")
        self.bubble.say(f"¡Se me soltó una telaraña! Error: {err_msg}", "")


# Backward compatibility alias
CapriWindow = SpiderWindow


# ==============================================================================
# SECTION 6: ENTRY POINT
# ==============================================================================

if __name__ == "__main__":
    app = QApplication(sys.argv)
    # Ensure secondary dialog closures do not terminate the desktop pet
    app.setQuitOnLastWindowClosed(False)
    window = SpiderWindow()
    window.show()
    # Show initial greeting in speech bubble
    window.bubble.say("¡Tu amigo y vecino Spider-Man patrullando tu escritorio! Escribe aquí para empezar.", "")
    sys.exit(app.exec())
