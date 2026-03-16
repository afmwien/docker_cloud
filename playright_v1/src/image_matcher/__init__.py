"""
Image Matcher Module - Findet Referenzbilder auf Webseiten

Komponenten:
- ImageLocator: 2-Phasen Lokalisierung + optimaler Screenshot mit Zoom
- ImageExtractor: Extrahiert alle Bilder von einer Webseite
- HashMatcher: Schneller Vorfilter mittels Perceptual Hashing
- FeatureMatcher: SIFT/ORB Feature-basiertes Matching
- TemplateMatcher: OpenCV Template Matching
- ImageMatcher: Orchestriert alle Methoden

Verwendung:
    from src.image_matcher import ImageLocator

    locator = ImageLocator(page)
    result = locator.find_and_screenshot(
        reference_image=Path("reference.jpg"),
        output_path=Path("screenshot.png")
    )

    if result.success:
        print(f"Gefunden bei Y={result.location.y}")
"""

from .image_locator import (
    ImageLocator,
    ImageLocation,
    LocatorResult,
)
from .image_matcher import (
    ImageMatcher,
    ImageMatchConfig,
    ImageMatchResult,
    find_image_on_page,
)
from .image_extractor import (
    ImageExtractor,
    ExtractedImage,
    ExtractionResult,
)
from .hash_matcher import (
    HashMatcher,
    HashMatchResult,
    quick_compare,
)
from .template_matcher import (
    TemplateMatcher,
    TemplateMatchResult,
    BoundingBox,
)
from .feature_matcher import (
    FeatureMatcher,
    FeatureMatchResult,
)

__all__ = [
    # Image Locator (2-Phasen)
    "ImageLocator",
    "ImageLocation",
    "LocatorResult",
    # Haupt-Orchestrierung
    "ImageMatcher",
    "ImageMatchConfig",
    "ImageMatchResult",
    "find_image_on_page",
    # Extractor
    "ImageExtractor",
    "ExtractedImage",
    "ExtractionResult",
    # Hash Matcher
    "HashMatcher",
    "HashMatchResult",
    "quick_compare",
    # Template Matcher
    "TemplateMatcher",
    "TemplateMatchResult",
    "BoundingBox",
    # Feature Matcher
    "FeatureMatcher",
    "FeatureMatchResult",
]
