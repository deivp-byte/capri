"""
abilities package - Hardware, desktop, window and system automation capabilities for Spider-Man.
"""
from abilities.window_manager import (
    get_active_or_target_window,
    move_window,
    minimize_window,
    maximize_window,
    restore_window,
    close_window,
    is_maximized,
)

__all__ = [
    "get_active_or_target_window",
    "move_window",
    "minimize_window",
    "maximize_window",
    "restore_window",
    "close_window",
    "is_maximized",
]
