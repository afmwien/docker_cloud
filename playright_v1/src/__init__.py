"""
Source Module für das Playwright Projekt

Module:
- browser: Persistenter Browser mit Stealth
- cookie_handler: Cookie-Banner Handling
- overlay_cleaner: Overlay-Entfernung
- screenshot: Desktop & Viewport Screenshots
- page_cleaner: Hauptorchestrierung
"""

# Hauptexporte
from .page_cleaner import (
    PageCleaner,
    PageCleanerConfig,
    PageCleanerResult,
    clean_page,
)

# Browser
from .browser import (
    PersistentBrowser,
    BrowserConfig,
    apply_stealth_settings,
)

# Cookie Handler
from .cookie_handler import (
    CookieHandler,
    CookieHandlerConfig,
)

# Overlay Cleaner
from .overlay_cleaner import (
    OverlayCleaner,
    OverlayCleanerConfig,
    OverlayDetector,
)

# Screenshot
from .screenshot import (
    ScreenshotManager,
    ScreenshotConfig,
    WindowManager,
)

__all__ = [
    # Page Cleaner
    "PageCleaner",
    "PageCleanerConfig",
    "PageCleanerResult",
    "clean_page",
    # Browser
    "PersistentBrowser",
    "BrowserConfig",
    "apply_stealth_settings",
    # Cookie Handler
    "CookieHandler",
    "CookieHandlerConfig",
    # Overlay Cleaner
    "OverlayCleaner",
    "OverlayCleanerConfig",
    "OverlayDetector",
    # Screenshot
    "ScreenshotManager",
    "ScreenshotConfig",
    "WindowManager",
]
