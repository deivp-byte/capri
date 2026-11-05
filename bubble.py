"""
bubble.py - Cyberpunk Speech Bubble & Chat Interface for Capri

Reconstructed from capri/desk/bubble.py and tailored for our lightweight,
clean PySide6 architecture:
- Chamfered matte panel with cyberpunk cut corners and neon accents.
- Typewriter text streaming effect (shown_chars incrementing smoothly).
- Live transmission header with signal meter and status indicators.
- User turn reference display in muted tone.
- Integrated QLineEdit for rapid desktop messaging.
- Auto-anchoring to Capri's body window across screen movements.
- Auto-dismiss reading hold timer.
"""

from __future__ import annotations

import time
from PySide6.QtCore import QEvent, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QKeyEvent, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QLineEdit, QWidget


def chamfer(r: QRectF, c: float) -> QPainterPath:
    """Creates a geometric polygon with top-left and bottom-right chamfered corners."""
    path = QPainterPath(QPointF(r.left() + c, r.top()))
    path.lineTo(r.right(), r.top())
    path.lineTo(r.right(), r.bottom() - c)
    path.lineTo(r.right() - c, r.bottom())
    path.lineTo(r.left(), r.bottom())
    path.lineTo(r.left(), r.top() + c)
    path.closeSubpath()
    return path


class SpiderBubble(QWidget):
    """
    Floating, transparent speech bubble overlay that displays Spider-Man's thoughts,
    streaming replies, and captures user input.
    """

    submitted = Signal(str)

    # Cyberpunk Color Palette
    BG_PANEL = QColor(16, 14, 24, 235)
    BORDER = QColor(255, 46, 112, 180)     # Neon Pink
    ACCENT_CYAN = QColor(0, 255, 204)       # Cyber Cyan
    ACCENT_PINK = QColor(255, 46, 112)
    TEXT_MAIN = QColor(245, 240, 250)
    TEXT_MUTED = QColor(140, 130, 160)
    TEXT_USER = QColor(180, 170, 210)

    def __init__(self, parent_pet: QWidget | None = None) -> None:
        super().__init__(
            None,
            Qt.FramelessWindowHint |
            Qt.Tool |
            Qt.WindowStaysOnTopHint |
            Qt.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)

        self.parent_pet = parent_pet

        # Dialogue State
        self.user_text = ""
        self.full_reply = ""
        self.shown_chars = 0.0
        self.cps = 38.0  # Characters per second for typewriter animation
        self.pause_until = 0.0
        self.hold_until = 0.0
        self.is_thinking = False
        self.closing_at = 0.0

        # Typography
        self.font_main = QFont("Segoe UI", 10)
        self.font_mono = QFont("Consolas", 8, QFont.Bold)
        self.font_user = QFont("Segoe UI", 8)

        # Dimensions
        self.panel_w = 320.0
        self.panel_h = 130.0

        # Input field
        self._setup_input()

        # Animation timer (60 FPS refresh)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(16)

    def _setup_input(self) -> None:
        """Configures the integrated message input field at the bottom of the panel."""
        self.edit = QLineEdit(self)
        self.edit.setPlaceholderText("Message Spider-Man... [Enter]")
        self.edit.setFont(QFont("Segoe UI", 9))
        self.edit.setStyleSheet("""
            QLineEdit {
                background: rgba(255, 255, 255, 12);
                color: #00ffcc;
                border: 1px solid rgba(255, 46, 112, 120);
                border-radius: 3px;
                padding: 4px 8px;
            }
            QLineEdit:focus {
                background: rgba(255, 255, 255, 20);
                border: 1px solid #00ffcc;
            }
            QLineEdit:disabled {
                background: rgba(10, 10, 15, 180);
                color: #666688;
                border: 1px solid #333344;
            }
        """)
        self.edit.returnPressed.connect(self._on_submit)
        self.edit.installEventFilter(self)

    def eventFilter(self, obj, event):
        """Intercepts Escape key from QLineEdit input field to trigger instant task cancel."""
        if obj == self.edit and event.type() == QEvent.KeyPress and event.key() == Qt.Key_Escape:
            if hasattr(self.parent_pet, "_cancel_active_tasks"):
                self.parent_pet._cancel_active_tasks()
            return True
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Escape key aborts ongoing background tasks."""
        if event.key() == Qt.Key_Escape:
            if hasattr(self.parent_pet, "_cancel_active_tasks"):
                self.parent_pet._cancel_active_tasks()
            event.accept()
            return
        super().keyPressEvent(event)

    def _on_submit(self) -> None:
        """Handles user enter key in the speech bubble's input field."""
        text = self.edit.text().strip()
        if not text:
            return
        self.edit.clear()
        self.submitted.emit(text)

    # --------------------------------------------------------------------------
    # PUBLIC API
    # --------------------------------------------------------------------------

    def say(self, reply: str, user_prompt: str = "") -> None:
        """Displays a new reply with typewriter animation."""
        self.user_text = user_prompt
        self.full_reply = reply
        self.shown_chars = 0.0
        self.pause_until = 0.0
        self.is_thinking = False
        self.closing_at = 0.0

        # Hold time based on reading duration
        reading_time = len(reply) / self.cps
        self.hold_until = time.monotonic() + reading_time + 4.5

        self.edit.setEnabled(True)
        self.edit.setPlaceholderText("Message Spider-Man... [Enter]")

        self._recalculate_size()
        self.reposition()
        self.show()
        self.raise_()

    def think(self, user_prompt: str = "") -> None:
        """Sets the bubble to thinking state with animated pulse indicator."""
        self.user_text = user_prompt
        self.full_reply = ""
        self.shown_chars = 0.0
        self.is_thinking = True
        self.closing_at = 0.0
        self.hold_until = time.monotonic() + 45.0  # Allow ample inference time

        self.edit.setEnabled(False)
        self.edit.setPlaceholderText("Spidey is thinking...")

        self._recalculate_size()
        self.reposition()
        self.show()
        self.raise_()

    def dismiss(self) -> None:
        """Closes the bubble."""
        self.hide()

    # --------------------------------------------------------------------------
    # LAYOUT & REPOSITIONING
    # --------------------------------------------------------------------------

    def _recalculate_size(self) -> None:
        """Dynamically computes bubble height to fit wrapped text."""
        fm_main = QFontMetricsF(self.font_main)
        fm_user = QFontMetricsF(self.font_user)

        pad = 14.0
        header_h = 24.0
        input_h = 32.0

        content_h = 0.0
        inner_w = self.panel_w - (pad * 2)

        if self.user_text:
            user_lines = self._wrap_lines(f"> You: {self.user_text}", fm_user, inner_w)
            content_h += len(user_lines) * fm_user.lineSpacing() + 6.0

        body_text = self.full_reply if self.full_reply else ("Processing in neural net..." if self.is_thinking else "")
        if body_text:
            body_lines = self._wrap_lines(body_text, fm_main, inner_w)
            content_h += len(body_lines) * fm_main.lineSpacing() + 8.0

        total_h = pad + header_h + content_h + input_h + pad
        self.panel_h = max(110.0, total_h)

        self.setFixedSize(round(self.panel_w), round(self.panel_h))

        # Position input at bottom
        self.edit.setGeometry(
            round(pad),
            round(self.panel_h - pad - input_h),
            round(inner_w),
            round(input_h)
        )
        self.update()

    def reposition(self) -> None:
        """Anchors the bubble right above or beside the parent pet window."""
        if not self.parent_pet:
            return

        pet_geom = self.parent_pet.geometry()
        x = pet_geom.center().x() - (self.panel_w / 2)
        y = pet_geom.top() - self.panel_h - 12

        # Screen boundary protection
        if y < 30:  # If near screen ceiling, place below the pet
            y = pet_geom.bottom() + 12

        self.move(round(x), round(y))

    def _wrap_lines(self, text: str, fm: QFontMetricsF, max_w: float) -> list[str]:
        """Utility to wrap text lines respecting max width."""
        lines, cur = [], ""
        for word in text.split():
            test_line = (cur + " " + word).strip()
            if fm.horizontalAdvance(test_line) <= max_w or not cur:
                cur = test_line
            else:
                lines.append(cur)
                cur = word
        if cur:
            lines.append(cur)
        return lines

    # --------------------------------------------------------------------------
    # TIMER & TICK (TYPEWRITER ANIMATION)
    # --------------------------------------------------------------------------

    def _tick(self) -> None:
        """60 FPS loop advancing typewriter animation and auto-dismiss timer."""
        if not self.isVisible():
            return

        now = time.monotonic()

        # Advance typewriter animation
        if self.full_reply and self.shown_chars < len(self.full_reply):
            if now >= self.pause_until:
                before = int(self.shown_chars)
                self.shown_chars = min(len(self.full_reply), self.shown_chars + (self.cps * 0.016))
                after = int(self.shown_chars)

                # Add tiny natural pause at punctuation
                if after > before and after < len(self.full_reply):
                    char = self.full_reply[after - 1]
                    if char in ",;":
                        self.pause_until = now + 0.12
                    elif char in ".!?":
                        self.pause_until = now + 0.28
            self.update()

        # Auto-dismiss once reading hold time expires
        if not self.is_thinking and not self.edit.hasFocus() and now > self.hold_until:
            if self.shown_chars >= len(self.full_reply):
                self.dismiss()

    # --------------------------------------------------------------------------
    # PAINT EVENT (CYBERPUNK VISUAL RENDERING)
    # --------------------------------------------------------------------------

    def paintEvent(self, _) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        rect = QRectF(1, 1, self.panel_w - 2, self.panel_h - 2)

        # 1. Background Panel with cut corners
        panel_path = chamfer(rect, 14.0)
        p.fillPath(panel_path, self.BG_PANEL)

        # 2. Cyberpunk border with pink glow
        p.setPen(QPen(self.BORDER, 1.5))
        p.drawPath(panel_path)

        # 3. Header Bar: Status dot and signal meter
        pad = 14.0
        header_y = pad + 10.0

        # Blinking / glowing status dot
        dot_color = self.ACCENT_CYAN if not self.is_thinking else self.ACCENT_PINK
        p.setPen(Qt.NoPen)
        p.setBrush(dot_color)
        p.drawEllipse(QPointF(pad + 4, header_y - 3), 3.5, 3.5)

        # Header Title
        p.setPen(self.ACCENT_CYAN)
        p.setFont(self.font_mono)
        status_text = "SPIDER-MAN // PATROL ONLINE" if not self.is_thinking else "SPIDER-MAN // NEURAL COMPUTE"
        p.drawText(round(pad + 16), round(header_y + 2), status_text)

        # Signal bars on the right
        sig_x = self.panel_w - pad - 24
        for i in range(4):
            bar_h = 4 + (i * 3)
            p.fillRect(QRectF(sig_x + (i * 5), header_y - bar_h + 3, 3, bar_h), self.ACCENT_CYAN)

        # Separator line
        p.setPen(QPen(QColor(255, 255, 255, 30), 1))
        p.drawLine(QPointF(pad, header_y + 8), QPointF(self.panel_w - pad, header_y + 8))

        # 4. User Reference Line
        curr_y = header_y + 20.0
        fm_user = QFontMetricsF(self.font_user)

        if self.user_text:
            p.setFont(self.font_user)
            p.setPen(self.TEXT_USER)
            user_lines = self._wrap_lines(f"> You: {self.user_text}", fm_user, self.panel_w - (pad * 2))
            for line in user_lines:
                p.drawText(round(pad), round(curr_y + fm_user.ascent()), line)
                curr_y += fm_user.lineSpacing()
            curr_y += 4.0

        # 5. Capri's Reply (Typewriter stream)
        fm_main = QFontMetricsF(self.font_main)
        p.setFont(self.font_main)
        p.setPen(self.TEXT_MAIN)

        if self.is_thinking:
            # Pulsing dots
            dots = "." * (int(time.monotonic() * 3) % 4)
            p.setPen(self.TEXT_MUTED)
            p.drawText(round(pad), round(curr_y + fm_main.ascent()), f"Processing{dots}")
        elif self.full_reply:
            visible_text = self.full_reply[:int(self.shown_chars)]
            reply_lines = self._wrap_lines(visible_text, fm_main, self.panel_w - (pad * 2))
            for line in reply_lines:
                p.drawText(round(pad), round(curr_y + fm_main.ascent()), line)
                curr_y += fm_main.lineSpacing()

        p.end()


# Backward compatibility alias
CapriBubble = SpiderBubble
