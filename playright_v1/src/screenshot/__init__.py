"""
Screenshot Module - Desktop-Screenshots und Fenster-Management
"""
from .screenshot_manager import (
    ScreenshotManager,
    ScreenshotConfig,
    ScreenshotResult,
)
from .window_manager import (
    WindowManager,
    WindowConfig,
)

__all__ = [
    "ScreenshotManager",
    "ScreenshotConfig",
    "ScreenshotResult",
    "WindowManager",
    "WindowConfig",
]
