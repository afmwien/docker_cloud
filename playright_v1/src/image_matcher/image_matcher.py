"""
Image Matcher - Orchestriert alle Matching-Methoden

Kombiniert:
1. Hash Matching (schneller Vorfilter)
2. Feature Matching (robust gegen Skalierung)
3. Template Matching (findet Position im Screenshot)

Verwendung:
    from src.image_matcher import ImageMatcher

    matcher = ImageMatcher(page)

    # Bild auf Seite finden
    result = matcher.find_on_page("reference.jpg")

    if result.found:
        print(f"Gefunden bei {result.position}")
        print(f"Confidence: {result.confidence:.1%}")
"""

import logging
from pathlib import Path
from typing import Optional, List, Tuple
from dataclasses import dataclass, field
from playwright.sync_api import Page
from PIL import Image

from .image_extractor import ImageExtractor, ExtractedImage
from .hash_matcher import HashMatcher, HashMatchResult
from .template_matcher import TemplateMatcher, TemplateMatchResult, BoundingBox
from .feature_matcher import FeatureMatcher, FeatureMatchResult


@dataclass
class ImageMatchConfig:
    """Konfiguration für den Image Matcher."""
    # Verzeichnisse
    temp_dir: Path = field(default_factory=lambda: Path("temp/image_matching"))

    # Hash Matching
    hash_threshold: int = 20  # Hamming-Distanz
    hash_min_similarity: float = 0.7

    # Feature Matching
    feature_min_matches: int = 10
    feature_min_confidence: float = 0.5

    # Template Matching
    template_threshold: float = 0.7
    template_multi_scale: bool = True

    # Bild-Extraktion
    min_image_width: int = 50
    min_image_height: int = 50


@dataclass
class ImageMatchResult:
    """Ergebnis der Bildsuche."""
    found: bool
    confidence: float = 0.0
    method: str = ""  # Welche Methode war erfolgreich

    # Position im Screenshot
    position: Optional[BoundingBox] = None

    # Welches Bild wurde gematcht
    matched_image: Optional[ExtractedImage] = None
    matched_path: Optional[Path] = None

    # Detail-Ergebnisse
    hash_result: Optional[HashMatchResult] = None
    feature_result: Optional[FeatureMatchResult] = None
    template_result: Optional[TemplateMatchResult] = None

    # Alle Kandidaten die geprüft wurden
    candidates_checked: int = 0


class ImageMatcher:
    """
    Findet ein Referenzbild auf einer Webseite.

    Strategie:
    1. Alle Bilder von der Seite extrahieren und herunterladen
    2. Hash-Vergleich als schneller Vorfilter
    3. Feature-Matching für Top-Kandidaten
    4. Template-Matching im Screenshot für genaue Position

    Verwendung:
        matcher = ImageMatcher(page)

        # In Seiten-Bildern suchen
        result = matcher.find_on_page(Path("reference.jpg"))

        # Im Screenshot suchen
        result = matcher.find_in_screenshot(
            Path("reference.jpg"),
            Path("screenshot.png")
        )
    """

    def __init__(
        self,
        page: Optional[Page] = None,
        config: Optional[ImageMatchConfig] = None,
        logger: Optional[logging.Logger] = None
    ):
        self.page = page
        self.config = config or ImageMatchConfig()
        self.logger = logger or logging.getLogger("ImageMatcher")

        # Submodule
        self._hash_matcher = HashMatcher(
            threshold=self.config.hash_threshold,
            logger=self.logger,
        )
        self._feature_matcher = FeatureMatcher(
            min_match_count=self.config.feature_min_matches,
            logger=self.logger,
        )
        self._template_matcher = TemplateMatcher(
            threshold=self.config.template_threshold,
            logger=self.logger,
        )

        # Temp-Verzeichnis
        self.config.temp_dir.mkdir(parents=True, exist_ok=True)

    def find_on_page(
        self,
        reference_path: Path,
        screenshot_path: Optional[Path] = None,
    ) -> ImageMatchResult:
        """
        Sucht das Referenzbild auf der aktuellen Seite.

        Args:
            reference_path: Pfad zum Referenzbild
            screenshot_path: Optional - Screenshot für Template-Matching

        Returns:
            ImageMatchResult
        """
        if self.page is None:
            return ImageMatchResult(found=False)

        result = ImageMatchResult(found=False)

        try:
            self.logger.info(f"Suche Bild: {reference_path.name}")

            # Phase 1: Bilder extrahieren
            self.logger.info("Phase 1: Extrahiere Bilder von der Seite...")

            extractor = ImageExtractor(
                self.page,
                download_dir=self.config.temp_dir / "extracted",
                min_width=self.config.min_image_width,
                min_height=self.config.min_image_height,
                logger=self.logger,
            )

            extraction = extractor.extract_all(download=True)

            if not extraction.success:
                self.logger.error("Bild-Extraktion fehlgeschlagen")
                return result

            self.logger.info(f"Extrahiert: {extraction.downloaded} Bilder")
            result.candidates_checked = extraction.downloaded

            # Phase 2: Hash-Matching als Vorfilter
            self.logger.info("Phase 2: Hash-Matching...")

            candidate_paths = [
                img.local_path for img in extraction.images
                if img.local_path and img.local_path.exists()
            ]

            hash_candidates = self._filter_by_hash(reference_path, candidate_paths)

            self.logger.info(f"Hash-Filter: {len(hash_candidates)} Kandidaten")

            # Phase 3: Feature-Matching
            if hash_candidates:
                self.logger.info("Phase 3: Feature-Matching...")

                best_feature = self._feature_matcher.find_best_match(
                    reference_path,
                    [c[0] for c in hash_candidates],
                    min_confidence=self.config.feature_min_confidence,
                )

                if best_feature:
                    matched_path, feature_result = best_feature

                    # Finde das zugehörige ExtractedImage
                    matched_image = None
                    for img in extraction.images:
                        if img.local_path == matched_path:
                            matched_image = img
                            break

                    result.found = True
                    result.confidence = feature_result.confidence
                    result.method = "feature"
                    result.matched_path = matched_path
                    result.matched_image = matched_image
                    result.feature_result = feature_result

                    # Position aus dem Bild-Element
                    if matched_image and matched_image.element_position:
                        pos = matched_image.element_position
                        result.position = BoundingBox(
                            x=int(pos["x"]),
                            y=int(pos["y"]),
                            width=int(pos["width"]),
                            height=int(pos["height"]),
                        )

                    self.logger.info(
                        f"✓ Feature-Match gefunden! "
                        f"Confidence: {feature_result.confidence:.1%}, "
                        f"Matches: {feature_result.good_matches}"
                    )

            # Phase 4: Template-Matching im Screenshot (wenn vorhanden)
            if screenshot_path and screenshot_path.exists():
                self.logger.info("Phase 4: Template-Matching im Screenshot...")

                template_result = self._find_in_screenshot(
                    reference_path,
                    screenshot_path,
                )

                if template_result.found:
                    # Wenn besser als Feature-Match oder keiner gefunden
                    if not result.found or template_result.confidence > result.confidence:
                        result.found = True
                        result.confidence = template_result.confidence
                        result.method = "template"
                        result.position = template_result.bounding_box
                        result.template_result = template_result

                        self.logger.info(
                            f"✓ Template-Match gefunden! "
                            f"Position: ({template_result.bounding_box.x}, {template_result.bounding_box.y}), "
                            f"Confidence: {template_result.confidence:.1%}"
                        )

            return result

        except Exception as e:
            self.logger.error(f"Bildsuche fehlgeschlagen: {e}")
            result.found = False
            return result

    def find_in_screenshot(
        self,
        reference_path: Path,
        screenshot_path: Path,
    ) -> ImageMatchResult:
        """
        Sucht das Referenzbild direkt im Screenshot.

        Verwendet Multi-Scale Template Matching.
        """
        result = ImageMatchResult(found=False)

        try:
            template_result = self._find_in_screenshot(reference_path, screenshot_path)

            if template_result.found:
                result.found = True
                result.confidence = template_result.confidence
                result.method = "template"
                result.position = template_result.bounding_box
                result.template_result = template_result

            return result

        except Exception as e:
            self.logger.error(f"Screenshot-Suche fehlgeschlagen: {e}")
            return result

    def _filter_by_hash(
        self,
        reference_path: Path,
        candidate_paths: List[Path],
    ) -> List[Tuple[Path, HashMatchResult]]:
        """Filtert Kandidaten mittels Hash-Vergleich."""
        matches = self._hash_matcher.find_all_matches(
            reference_path,
            candidate_paths,
            min_similarity=self.config.hash_min_similarity,
        )
        return matches

    def _find_in_screenshot(
        self,
        reference_path: Path,
        screenshot_path: Path,
    ) -> TemplateMatchResult:
        """Template-Matching im Screenshot."""
        if self.config.template_multi_scale:
            return self._template_matcher.find_multi_scale(
                reference_path,
                screenshot_path,
                threshold=self.config.template_threshold,
            )
        else:
            return self._template_matcher.find(
                reference_path,
                screenshot_path,
                threshold=self.config.template_threshold,
            )

    def highlight_on_screenshot(
        self,
        result: ImageMatchResult,
        screenshot_path: Path,
        output_path: Path,
    ) -> bool:
        """
        Markiert das gefundene Bild auf dem Screenshot.
        """
        if not result.found or not result.position:
            return False

        if result.template_result:
            return self._template_matcher.highlight_match(
                result.template_result,
                screenshot_path,
                output_path,
            )

        return False


# Convenience-Funktion
def find_image_on_page(
    page: Page,
    reference_path: Path,
    screenshot_path: Optional[Path] = None,
) -> ImageMatchResult:
    """
    Einfache Funktion zum Finden eines Bildes auf einer Seite.
    """
    matcher = ImageMatcher(page)
    return matcher.find_on_page(reference_path, screenshot_path)
