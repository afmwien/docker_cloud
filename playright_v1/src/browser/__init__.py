"""
Browser Module - Stealth und Browser-Management
"""
from .stealth import (
    apply_stealth_settings,
    get_stealth_context_options,
)
from .persistent_browser import (
    PersistentBrowser,
    BrowserConfig,
    create_persistent_browser,
)

__all__ = [
    "apply_stealth_settings",
    "get_stealth_context_options",
    "PersistentBrowser",
    "BrowserConfig",
    "create_persistent_browser",
]
