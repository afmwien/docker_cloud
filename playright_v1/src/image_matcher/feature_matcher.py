"""
Feature Matcher - SIFT/ORB Feature-basiertes Matching

Robuster als Template Matching bei:
- Skalierung
- Rotation
- Teilweiser Verdeckung
- Unterschiedlicher Kompression
"""

import logging
from pathlib import Path
from typing import Optional, List, Tuple
from dataclasses import dataclass
import cv2
import numpy as np


@dataclass
class FeatureMatchResult:
    """Ergebnis des Feature Matchings."""
    is_match: bool
    confidence: float  # 0.0 - 1.0
    good_matches: int  # Anzahl guter Matches
    total_matches: int  # Alle Matches
    method: str  # ORB, SIFT, etc.
    homography: Optional[np.ndarray] = None  # Transformationsmatrix
    inliers: int = 0  # Matches nach RANSAC


class FeatureMatcher:
    """
    Feature-basiertes Bildmatching mit SIFT oder ORB.

    Funktioniert auch wenn:
    - Bilder unterschiedlich skaliert sind
    - Bilder beschnitten sind
    - Unterschiedliche Kompression/Qualität

    Verwendung:
        matcher = FeatureMatcher(method="orb")

        result = matcher.match(reference_path, candidate_path)

        if result.is_match:
            print(f"Match! {result.good_matches} Features übereinstimmend")
    """

    def __init__(
        self,
        method: str = "orb",  # "orb" oder "sift"
        min_match_count: int = 10,
        ratio_threshold: float = 0.75,
        logger: Optional[logging.Logger] = None
    ):
        self.method = method.lower()
        self.min_match_count = min_match_count
        self.ratio_threshold = ratio_threshold
        self.logger = logger or logging.getLogger("FeatureMatcher")

        # Feature Detector erstellen
        if self.method == "sift":
            self._detector = cv2.SIFT_create()
            self._matcher = cv2.BFMatcher(cv2.NORM_L2)
        else:
            # ORB ist schneller und braucht keine Patent-Lizenz
            self._detector = cv2.ORB_create(nfeatures=1000)
            self._matcher = cv2.BFMatcher(cv2.NORM_HAMMING)

    def match(
        self,
        reference_path: Path,
        candidate_path: Path,
    ) -> FeatureMatchResult:
        """
        Vergleicht zwei Bilder mittels Feature Matching.

        Args:
            reference_path: Referenzbild
            candidate_path: Zu vergleichendes Bild

        Returns:
            FeatureMatchResult
        """
        try:
            # Bilder laden
            ref_img = cv2.imread(str(reference_path), cv2.IMREAD_GRAYSCALE)
            cand_img = cv2.imread(str(candidate_path), cv2.IMREAD_GRAYSCALE)

            if ref_img is None or cand_img is None:
                return FeatureMatchResult(
                    is_match=False,
                    confidence=0.0,
                    good_matches=0,
                    total_matches=0,
                    method=self.method,
                )

            # Features erkennen
            kp1, des1 = self._detector.detectAndCompute(ref_img, None)
            kp2, des2 = self._detector.detectAndCompute(cand_img, None)

            if des1 is None or des2 is None:
                return FeatureMatchResult(
                    is_match=False,
                    confidence=0.0,
                    good_matches=0,
                    total_matches=0,
                    method=self.method,
                )

            # Matches finden (KNN)
            matches = self._matcher.knnMatch(des1, des2, k=2)

            # Ratio Test (Lowe's ratio test)
            good_matches = []
            for match in matches:
                if len(match) == 2:
                    m, n = match
                    if m.distance < self.ratio_threshold * n.distance:
                        good_matches.append(m)

            # Confidence berechnen
            # Basiert auf Verhältnis von guten Matches zu erwarteten Matches
            if len(kp1) > 0:
                confidence = min(1.0, len(good_matches) / max(self.min_match_count, len(kp1) * 0.1))
            else:
                confidence = 0.0

            is_match = len(good_matches) >= self.min_match_count

            # Homographie berechnen wenn genug Matches
            homography = None
            inliers = 0

            if len(good_matches) >= 4:
                src_pts = np.float32([kp1[m.queryIdx].pt for m in good_matches]).reshape(-1, 1, 2)
                dst_pts = np.float32([kp2[m.trainIdx].pt for m in good_matches]).reshape(-1, 1, 2)

                homography, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)

                if mask is not None:
                    inliers = int(mask.sum())
                    # Aktualisiere Match-Qualität basierend auf Inliers
                    if inliers >= self.min_match_count:
                        is_match = True
                        confidence = min(1.0, inliers / self.min_match_count)

            return FeatureMatchResult(
                is_match=is_match,
                confidence=confidence,
                good_matches=len(good_matches),
                total_matches=len(matches),
                method=self.method,
                homography=homography,
                inliers=inliers,
            )

        except Exception as e:
            self.logger.error(f"Feature Matching fehlgeschlagen: {e}")
            return FeatureMatchResult(
                is_match=False,
                confidence=0.0,
                good_matches=0,
                total_matches=0,
                method=self.method,
            )

    def find_in_image(
        self,
        template_path: Path,
        image_path: Path,
    ) -> Tuple[bool, Optional[np.ndarray]]:
        """
        Findet das Template im größeren Bild mittels Features.

        Returns:
            (gefunden, bounding_box_corners)
        """
        result = self.match(template_path, image_path)

        if not result.is_match or result.homography is None:
            return False, None

        try:
            # Template-Ecken transformieren
            template = cv2.imread(str(template_path))
            h, w = template.shape[:2]

            corners = np.float32([
                [0, 0],
                [w, 0],
                [w, h],
                [0, h]
            ]).reshape(-1, 1, 2)

            transformed = cv2.perspectiveTransform(corners, result.homography)

            return True, transformed

        except Exception:
            return False, None

    def find_best_match(
        self,
        reference_path: Path,
        candidate_paths: List[Path],
        min_confidence: float = 0.5
    ) -> Optional[Tuple[Path, FeatureMatchResult]]:
        """
        Findet das beste Match aus einer Liste von Kandidaten.
        """
        best_match = None
        best_result = None

        for candidate in candidate_paths:
            result = self.match(reference_path, candidate)

            if result.confidence >= min_confidence:
                if best_result is None or result.confidence > best_result.confidence:
                    best_match = candidate
                    best_result = result

        if best_match:
            return (best_match, best_result)
        return None

    def visualize_matches(
        self,
        reference_path: Path,
        candidate_path: Path,
        output_path: Path,
        max_matches: int = 50
    ) -> bool:
        """
        Erstellt eine Visualisierung der Matches.
        """
        try:
            ref_img = cv2.imread(str(reference_path))
            cand_img = cv2.imread(str(candidate_path))

            if ref_img is None or cand_img is None:
                return False

            ref_gray = cv2.cvtColor(ref_img, cv2.COLOR_BGR2GRAY)
            cand_gray = cv2.cvtColor(cand_img, cv2.COLOR_BGR2GRAY)

            kp1, des1 = self._detector.detectAndCompute(ref_gray, None)
            kp2, des2 = self._detector.detectAndCompute(cand_gray, None)

            if des1 is None or des2 is None:
                return False

            matches = self._matcher.knnMatch(des1, des2, k=2)

            good_matches = []
            for match in matches:
                if len(match) == 2:
                    m, n = match
                    if m.distance < self.ratio_threshold * n.distance:
                        good_matches.append(m)

            # Sortieren nach Distanz und begrenzen
            good_matches = sorted(good_matches, key=lambda x: x.distance)[:max_matches]

            # Visualisierung erstellen
            result_img = cv2.drawMatches(
                ref_img, kp1,
                cand_img, kp2,
                good_matches, None,
                flags=cv2.DrawMatchesFlags_NOT_DRAW_SINGLE_POINTS
            )

            cv2.imwrite(str(output_path), result_img)
            return True

        except Exception as e:
            self.logger.error(f"Visualisierung fehlgeschlagen: {e}")
            return False
