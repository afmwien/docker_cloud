"""
Hash Matcher - Perceptual Hashing für schnelle Bildvergleiche

Verwendet verschiedene Hash-Algorithmen:
- pHash (perceptual hash) - robust gegen Skalierung
- dHash (difference hash) - schnell
- aHash (average hash) - einfach
- wHash (wavelet hash) - beste Qualität
"""

import logging
from pathlib import Path
from typing import Optional, List, Tuple
from dataclasses import dataclass
from PIL import Image
import imagehash


@dataclass
class HashMatchResult:
    """Ergebnis eines Hash-Vergleichs."""
    is_match: bool
    similarity: float  # 0.0 - 1.0
    hash_distance: int  # Hamming-Distanz
    method: str  # welcher Hash-Algorithmus
    reference_hash: str
    candidate_hash: str


class HashMatcher:
    """
    Schneller Bildvergleich mittels Perceptual Hashing.

    Verwendet Hamming-Distanz zwischen Hashes um Ähnlichkeit zu messen.

    Verwendung:
        matcher = HashMatcher()

        # Einzelvergleich
        result = matcher.compare(reference_path, candidate_path)
        if result.is_match:
            print(f"Match! Similarity: {result.similarity:.1%}")

        # Bestes Match finden
        best = matcher.find_best_match(reference_path, [img1, img2, img3])
    """

    # Hash-Größe (bits) - größer = genauer aber langsamer
    HASH_SIZE = 16

    # Standard-Schwellenwerte für Hamming-Distanz
    # (bei hash_size=16: max Distanz = 256)
    THRESHOLDS = {
        "exact": 5,       # Praktisch identisch
        "very_similar": 15,  # Sehr ähnlich (Kompression, leichte Änderungen)
        "similar": 25,    # Ähnlich (Crop, Resize)
        "maybe": 40,      # Vielleicht verwandt
    }

    def __init__(
        self,
        hash_size: int = 16,
        threshold: int = 15,
        logger: Optional[logging.Logger] = None
    ):
        self.hash_size = hash_size
        self.threshold = threshold
        self.logger = logger or logging.getLogger("HashMatcher")

    def compute_hash(
        self,
        image_path: Path,
        method: str = "phash"
    ) -> Optional[imagehash.ImageHash]:
        """
        Berechnet den Hash eines Bildes.

        Args:
            image_path: Pfad zum Bild
            method: Hash-Methode (phash, dhash, ahash, whash)

        Returns:
            ImageHash oder None bei Fehler
        """
        try:
            img = Image.open(image_path)

            if method == "phash":
                return imagehash.phash(img, hash_size=self.hash_size)
            elif method == "dhash":
                return imagehash.dhash(img, hash_size=self.hash_size)
            elif method == "ahash":
                return imagehash.average_hash(img, hash_size=self.hash_size)
            elif method == "whash":
                return imagehash.whash(img, hash_size=self.hash_size)
            else:
                return imagehash.phash(img, hash_size=self.hash_size)

        except Exception as e:
            self.logger.warning(f"Hash-Berechnung fehlgeschlagen für {image_path}: {e}")
            return None

    def compare(
        self,
        reference_path: Path,
        candidate_path: Path,
        method: str = "phash"
    ) -> HashMatchResult:
        """
        Vergleicht zwei Bilder mittels Hash.

        Args:
            reference_path: Referenzbild
            candidate_path: Zu vergleichendes Bild
            method: Hash-Methode

        Returns:
            HashMatchResult
        """
        ref_hash = self.compute_hash(reference_path, method)
        cand_hash = self.compute_hash(candidate_path, method)

        if ref_hash is None or cand_hash is None:
            return HashMatchResult(
                is_match=False,
                similarity=0.0,
                hash_distance=999,
                method=method,
                reference_hash="",
                candidate_hash="",
            )

        # Hamming-Distanz berechnen
        distance = ref_hash - cand_hash

        # Similarity berechnen (0 = identisch, max = hash_size^2)
        max_distance = self.hash_size * self.hash_size
        similarity = 1.0 - (distance / max_distance)

        return HashMatchResult(
            is_match=distance <= self.threshold,
            similarity=similarity,
            hash_distance=distance,
            method=method,
            reference_hash=str(ref_hash),
            candidate_hash=str(cand_hash),
        )

    def compare_multi_hash(
        self,
        reference_path: Path,
        candidate_path: Path,
    ) -> HashMatchResult:
        """
        Vergleicht mit mehreren Hash-Methoden und nimmt das beste Ergebnis.
        """
        methods = ["phash", "dhash", "ahash"]
        best_result = None

        for method in methods:
            result = self.compare(reference_path, candidate_path, method)

            if best_result is None or result.similarity > best_result.similarity:
                best_result = result

        return best_result

    def find_best_match(
        self,
        reference_path: Path,
        candidate_paths: List[Path],
        method: str = "phash",
        min_similarity: float = 0.8
    ) -> Optional[Tuple[Path, HashMatchResult]]:
        """
        Findet das beste Match aus einer Liste von Kandidaten.

        Args:
            reference_path: Referenzbild
            candidate_paths: Liste von Kandidaten
            method: Hash-Methode
            min_similarity: Minimale Ähnlichkeit für Match

        Returns:
            Tuple (Pfad, Ergebnis) oder None
        """
        best_match = None
        best_result = None

        ref_hash = self.compute_hash(reference_path, method)
        if ref_hash is None:
            return None

        for candidate in candidate_paths:
            cand_hash = self.compute_hash(candidate, method)
            if cand_hash is None:
                continue

            distance = ref_hash - cand_hash
            max_distance = self.hash_size * self.hash_size
            similarity = 1.0 - (distance / max_distance)

            if similarity >= min_similarity:
                if best_result is None or similarity > best_result.similarity:
                    best_match = candidate
                    best_result = HashMatchResult(
                        is_match=True,
                        similarity=similarity,
                        hash_distance=distance,
                        method=method,
                        reference_hash=str(ref_hash),
                        candidate_hash=str(cand_hash),
                    )

        if best_match:
            return (best_match, best_result)
        return None

    def find_all_matches(
        self,
        reference_path: Path,
        candidate_paths: List[Path],
        method: str = "phash",
        min_similarity: float = 0.7
    ) -> List[Tuple[Path, HashMatchResult]]:
        """
        Findet alle Matches über einem Schwellenwert.
        """
        matches = []

        ref_hash = self.compute_hash(reference_path, method)
        if ref_hash is None:
            return matches

        for candidate in candidate_paths:
            result = self.compare(reference_path, candidate, method)

            if result.similarity >= min_similarity:
                matches.append((candidate, result))

        # Nach Ähnlichkeit sortieren
        matches.sort(key=lambda x: x[1].similarity, reverse=True)

        return matches


def quick_compare(image1: Path, image2: Path, threshold: int = 15) -> bool:
    """
    Schneller Vergleich zweier Bilder.

    Returns:
        True wenn Bilder ähnlich sind
    """
    matcher = HashMatcher(threshold=threshold)
    result = matcher.compare(image1, image2)
    return result.is_match
