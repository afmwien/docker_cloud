"""
Overlay Cleaner Module - Erkennt und entfernt alle Störelemente
"""
from .overlay_cleaner import (
    OverlayCleaner,
    OverlayCleanerConfig,
    OverlayCleanerResult,
    CleanAction,
    CleanResult,
)
from .overlay_detector import (
    OverlayDetector,
    DetectedOverlay,
)
from .overlay_patterns import (
    OverlayPatterns,
    OverlayType,
)

__all__ = [
    "OverlayCleaner",
    "OverlayCleanerConfig",
    "OverlayCleanerResult",
    "CleanAction",
    "CleanResult",
    "OverlayDetector",
    "DetectedOverlay",
    "OverlayPatterns",
    "OverlayType",
]
