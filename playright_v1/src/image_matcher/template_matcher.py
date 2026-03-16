"""
Template Matcher - OpenCV Template Matching

Findet ein Referenzbild innerhalb eines größeren Bildes (z.B. Screenshot).
Unterstützt verschiedene Matching-Methoden und Multi-Scale Matching.
"""

import logging
from pathlib import Path
from typing import Optional, List, Tuple
from dataclasses import dataclass
import cv2
import numpy as np
from PIL import Image


@dataclass
class BoundingBox:
    """Position eines gefundenen Elements."""
    x: int
    y: int
    width: int
    height: int

    @property
    def center(self) -> Tuple[int, int]:
        return (self.x + self.width // 2, self.y + self.height // 2)

    @property
    def area(self) -> int:
        return self.width * self.height


@dataclass
class TemplateMatchResult:
    """Ergebnis des Template Matchings."""
    found: bool
    confidence: float  # 0.0 - 1.0
    bounding_box: Optional[BoundingBox] = None
    scale: float = 1.0  # Skalierungsfaktor
    method: str = ""
    all_matches: List[BoundingBox] = None  # Alle gefundenen Positionen

    def __post_init__(self):
        if self.all_matches is None:
            self.all_matches = []


class TemplateMatcher:
    """
    Findet ein Template-Bild innerhalb eines größeren Bildes.

    Verwendet OpenCV Template Matching mit Multi-Scale Support.

    Verwendung:
        matcher = TemplateMatcher()

        # Bild im Screenshot finden
        result = matcher.find(template_path, screenshot_path)

        if result.found:
            print(f"Gefunden bei {result.bounding_box.x}, {result.bounding_box.y}")
            print(f"Confidence: {result.confidence:.1%}")
    """

    # Verfügbare Matching-Methoden
    METHODS = {
        "ccoeff_normed": cv2.TM_CCOEFF_NORMED,  # Beste für die meisten Fälle
        "ccorr_normed": cv2.TM_CCORR_NORMED,
        "sqdiff_normed": cv2.TM_SQDIFF_NORMED,  # Invertiert - 0 = beste Match
    }

    def __init__(
        self,
        method: str = "ccoeff_normed",
        threshold: float = 0.8,
        logger: Optional[logging.Logger] = None
    ):
        self.method = method
        self.threshold = threshold
        self.logger = logger or logging.getLogger("TemplateMatcher")

        self._cv_method = self.METHODS.get(method, cv2.TM_CCOEFF_NORMED)

    def find(
        self,
        template_path: Path,
        image_path: Path,
        threshold: Optional[float] = None
    ) -> TemplateMatchResult:
        """
        Sucht das Template im Bild.

        Args:
            template_path: Das zu suchende Bild
            image_path: Das Bild, in dem gesucht wird
            threshold: Mindest-Confidence (überschreibt Instanz-Wert)

        Returns:
            TemplateMatchResult
        """
        thresh = threshold or self.threshold

        try:
            # Bilder laden
            template = cv2.imread(str(template_path))
            image = cv2.imread(str(image_path))

            if template is None:
                self.logger.error(f"Template konnte nicht geladen werden: {template_path}")
                return TemplateMatchResult(found=False, confidence=0.0)

            if image is None:
                self.logger.error(f"Bild konnte nicht geladen werden: {image_path}")
                return TemplateMatchResult(found=False, confidence=0.0)

            # In Graustufen konvertieren
            template_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
            image_gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

            # Template Matching
            result = cv2.matchTemplate(image_gray, template_gray, self._cv_method)

            # Beste Position finden
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)

            # Bei SQDIFF ist das Minimum das beste Match
            if self.method == "sqdiff_normed":
                confidence = 1.0 - min_val
                location = min_loc
            else:
                confidence = max_val
                location = max_loc

            h, w = template_gray.shape

            if confidence >= thresh:
                bbox = BoundingBox(
                    x=location[0],
                    y=location[1],
                    width=w,
                    height=h,
                )

                return TemplateMatchResult(
                    found=True,
                    confidence=confidence,
                    bounding_box=bbox,
                    scale=1.0,
                    method=self.method,
                    all_matches=[bbox],
                )
            else:
                return TemplateMatchResult(
                    found=False,
                    confidence=confidence,
                    method=self.method,
                )

        except Exception as e:
            self.logger.error(f"Template Matching fehlgeschlagen: {e}")
            return TemplateMatchResult(found=False, confidence=0.0)

    def find_multi_scale(
        self,
        template_path: Path,
        image_path: Path,
        scales: List[float] = None,
        threshold: Optional[float] = None
    ) -> TemplateMatchResult:
        """
        Multi-Scale Template Matching.

        Sucht das Template in verschiedenen Größen.

        Args:
            template_path: Das zu suchende Bild
            image_path: Das Bild, in dem gesucht wird
            scales: Liste von Skalierungsfaktoren
            threshold: Mindest-Confidence

        Returns:
            TemplateMatchResult
        """
        if scales is None:
            scales = [0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.5, 2.0]

        thresh = threshold or self.threshold

        try:
            template = cv2.imread(str(template_path))
            image = cv2.imread(str(image_path))

            if template is None or image is None:
                return TemplateMatchResult(found=False, confidence=0.0)

            template_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
            image_gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

            best_match = None
            best_confidence = 0.0
            best_scale = 1.0
            best_location = None
            best_size = None

            for scale in scales:
                # Template skalieren
                new_width = int(template_gray.shape[1] * scale)
                new_height = int(template_gray.shape[0] * scale)

                # Mindestgröße prüfen
                if new_width < 20 or new_height < 20:
                    continue

                # Größer als Bild?
                if new_width > image_gray.shape[1] or new_height > image_gray.shape[0]:
                    continue

                scaled_template = cv2.resize(template_gray, (new_width, new_height))

                # Template Matching
                result = cv2.matchTemplate(image_gray, scaled_template, self._cv_method)

                min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)

                if self.method == "sqdiff_normed":
                    confidence = 1.0 - min_val
                    location = min_loc
                else:
                    confidence = max_val
                    location = max_loc

                if confidence > best_confidence:
                    best_confidence = confidence
                    best_scale = scale
                    best_location = location
                    best_size = (new_width, new_height)

            if best_confidence >= thresh and best_location:
                bbox = BoundingBox(
                    x=best_location[0],
                    y=best_location[1],
                    width=best_size[0],
                    height=best_size[1],
                )

                return TemplateMatchResult(
                    found=True,
                    confidence=best_confidence,
                    bounding_box=bbox,
                    scale=best_scale,
                    method=self.method,
                    all_matches=[bbox],
                )
            else:
                return TemplateMatchResult(
                    found=False,
                    confidence=best_confidence,
                    scale=best_scale,
                    method=self.method,
                )

        except Exception as e:
            self.logger.error(f"Multi-Scale Matching fehlgeschlagen: {e}")
            return TemplateMatchResult(found=False, confidence=0.0)

    def find_all(
        self,
        template_path: Path,
        image_path: Path,
        threshold: Optional[float] = None,
        max_matches: int = 10
    ) -> TemplateMatchResult:
        """
        Findet alle Vorkommen des Templates im Bild.
        """
        thresh = threshold or self.threshold

        try:
            template = cv2.imread(str(template_path))
            image = cv2.imread(str(image_path))

            if template is None or image is None:
                return TemplateMatchResult(found=False, confidence=0.0)

            template_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
            image_gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

            h, w = template_gray.shape

            result = cv2.matchTemplate(image_gray, template_gray, self._cv_method)

            # Alle Positionen über Threshold finden
            if self.method == "sqdiff_normed":
                locations = np.where(result <= (1.0 - thresh))
            else:
                locations = np.where(result >= thresh)

            matches = []

            for pt in zip(*locations[::-1]):
                # Position bereits gefunden? (Non-Maximum Suppression)
                is_duplicate = False
                for existing in matches:
                    if abs(existing.x - pt[0]) < w // 2 and abs(existing.y - pt[1]) < h // 2:
                        is_duplicate = True
                        break

                if not is_duplicate:
                    matches.append(BoundingBox(
                        x=pt[0],
                        y=pt[1],
                        width=w,
                        height=h,
                    ))

                if len(matches) >= max_matches:
                    break

            if matches:
                # Confidence für erstes Match
                best_loc = (matches[0].x, matches[0].y)
                confidence = result[best_loc[1], best_loc[0]]

                if self.method == "sqdiff_normed":
                    confidence = 1.0 - confidence

                return TemplateMatchResult(
                    found=True,
                    confidence=confidence,
                    bounding_box=matches[0],
                    method=self.method,
                    all_matches=matches,
                )
            else:
                return TemplateMatchResult(found=False, confidence=0.0, method=self.method)

        except Exception as e:
            self.logger.error(f"Find-All fehlgeschlagen: {e}")
            return TemplateMatchResult(found=False, confidence=0.0)

    def highlight_match(
        self,
        result: TemplateMatchResult,
        image_path: Path,
        output_path: Path,
        color: Tuple[int, int, int] = (0, 255, 0),
        thickness: int = 3
    ) -> bool:
        """
        Zeichnet einen Rahmen um das gefundene Match und speichert das Bild.
        """
        try:
            image = cv2.imread(str(image_path))

            if image is None or not result.found:
                return False

            for bbox in result.all_matches:
                cv2.rectangle(
                    image,
                    (bbox.x, bbox.y),
                    (bbox.x + bbox.width, bbox.y + bbox.height),
                    color,
                    thickness
                )

            cv2.imwrite(str(output_path), image)
            return True

        except Exception as e:
            self.logger.error(f"Highlight fehlgeschlagen: {e}")
            return False
