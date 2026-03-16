"""
Image Locator - 2-Phasen Bild-Lokalisierung mit optimalem Screenshot

Phase 1: Schnelle Lokalisierung durch Scrollen (ohne Screenshots)
Phase 2: Ein optimaler Screenshot mit Zoom-Anpassung

Verwendung:
    locator = ImageLocator(page)
    result = locator.find_and_screenshot(
        reference_image=Path("reference.jpg"),
        output_path=Path("screenshot.png")
    )
"""

import logging
import time
from pathlib import Path
from typing import Optional, List, Tuple
from dataclasses import dataclass
from playwright.sync_api import Page
import mss
from PIL import Image

from .hash_matcher import HashMatcher
from .feature_matcher import FeatureMatcher


@dataclass
class ImageLocation:
    """Position eines gefundenen Bildes auf der Seite."""
    found: bool = False

    # Position auf der Seite (absolut)
    x: int = 0
    y: int = 0
    width: int = 0
    height: int = 0

    # Element-Info
    src: str = ""
    alt: str = ""
    selector: str = ""

    # Matching-Info
    confidence: float = 0.0
    method: str = ""  # hash, feature

    @property
    def center_y(self) -> int:
        return self.y + self.height // 2

    @property
    def center_x(self) -> int:
        return self.x + self.width // 2

    @property
    def bottom(self) -> int:
        return self.y + self.height


@dataclass
class LocatorResult:
    """Ergebnis der Lokalisierung + Screenshot."""
    success: bool
    location: Optional[ImageLocation] = None
    screenshot_path: Optional[Path] = None
    zoom_level: float = 1.0
    scroll_position: int = 0
    error: Optional[str] = None


class ImageLocator:
    """
    Findet ein Bild auf einer Webseite und erstellt einen optimalen Screenshot.

    Phase 1: Scrollt durch die Seite und vergleicht sichtbare Bilder
    Phase 2: Berechnet optimalen Zoom und erstellt einen Screenshot

    Verwendung:
        locator = ImageLocator(page)

        result = locator.find_and_screenshot(
            reference_image=Path("data/reference_images/bild.jpg"),
            output_path=Path("output/screenshot.png"),
            context_pixels=200  # Kontext um das Bild
        )

        if result.success:
            print(f"Bild gefunden bei Y={result.location.y}")
            print(f"Screenshot: {result.screenshot_path}")
    """

    def __init__(
        self,
        page: Page,
        logger: Optional[logging.Logger] = None
    ):
        self.page = page
        self.logger = logger or logging.getLogger("ImageLocator")

        # Matcher
        self._hash_matcher = HashMatcher(threshold=25)
        self._feature_matcher = FeatureMatcher(min_match_count=8)

        # Temp-Verzeichnis für heruntergeladene Bilder
        self._temp_dir = Path("temp/locator")
        self._temp_dir.mkdir(parents=True, exist_ok=True)

    def find_and_screenshot(
        self,
        reference_image: Path,
        output_path: Path,
        context_pixels: int = 150,
        min_zoom: float = 0.5,
        max_zoom: float = 1.0,
    ) -> LocatorResult:
        """
        Hauptmethode: Bild finden und optimalen Screenshot erstellen.

        Args:
            reference_image: Pfad zum Referenzbild
            output_path: Pfad für den Screenshot
            context_pixels: Pixel Kontext oben/unten um das Bild
            min_zoom: Minimaler Zoom-Level
            max_zoom: Maximaler Zoom-Level

        Returns:
            LocatorResult
        """
        result = LocatorResult(success=False)

        try:
            self.logger.info("=" * 50)
            self.logger.info("PHASE 1: Lokalisierung (ohne Screenshots)")
            self.logger.info("=" * 50)

            # Phase 1: Bild lokalisieren
            location = self._locate_image(reference_image)

            if not location.found:
                self.logger.warning("Bild nicht gefunden!")
                result.error = "Bild nicht auf der Seite gefunden"
                return result

            result.location = location
            self.logger.info(f"✓ Bild gefunden!")
            self.logger.info(f"  Position: Y={location.y}, X={location.x}")
            self.logger.info(f"  Größe: {location.width}x{location.height}")
            self.logger.info(f"  Confidence: {location.confidence:.1%}")

            self.logger.info("")
            self.logger.info("=" * 50)
            self.logger.info("PHASE 2: Optimaler Screenshot mit Zoom")
            self.logger.info("=" * 50)

            # Phase 2: Optimalen Screenshot erstellen
            screenshot_result = self._capture_optimal_screenshot(
                location=location,
                output_path=output_path,
                context_pixels=context_pixels,
                min_zoom=min_zoom,
                max_zoom=max_zoom,
            )

            result.success = screenshot_result["success"]
            result.screenshot_path = output_path if screenshot_result["success"] else None
            result.zoom_level = screenshot_result.get("zoom", 1.0)
            result.scroll_position = screenshot_result.get("scroll", 0)

            if result.success:
                self.logger.info(f"✓ Screenshot erstellt: {output_path}")

        except Exception as e:
            result.error = str(e)
            self.logger.error(f"Fehler: {e}")

        return result

    def _locate_image(self, reference_image: Path) -> ImageLocation:
        """
        Phase 1: Scrollt durch die Seite und sucht das Bild.
        """
        location = ImageLocation(found=False)

        # Seiten-Info holen
        page_height = self.page.evaluate("document.documentElement.scrollHeight")
        viewport_height = self.page.evaluate("window.innerHeight")

        self.logger.info(f"Seiten-Höhe: {page_height}px, Viewport: {viewport_height}px")

        # Zum Anfang scrollen
        self.page.evaluate("window.scrollTo(0, 0)")
        self.page.wait_for_timeout(300)

        scroll_step = viewport_height - 100  # Leichte Überlappung
        current_scroll = 0
        viewport_num = 0

        while current_scroll < page_height:
            viewport_num += 1
            self.logger.info(f"Scanne Viewport {viewport_num} (Y={current_scroll})...")

            # Alle sichtbaren Bilder im aktuellen Viewport holen
            visible_images = self._get_visible_images()

            self.logger.info(f"  {len(visible_images)} Bilder sichtbar")

            # Jedes Bild mit Referenz vergleichen
            for img_info in visible_images:
                match_result = self._match_image(reference_image, img_info)

                if match_result["matched"]:
                    # Gefunden!
                    location.found = True
                    location.x = img_info["x"]
                    location.y = img_info["absolute_y"]
                    location.width = img_info["width"]
                    location.height = img_info["height"]
                    location.src = img_info["src"]
                    location.alt = img_info.get("alt", "")
                    location.confidence = match_result["confidence"]
                    location.method = match_result["method"]

                    return location

            # Weiter scrollen
            current_scroll += scroll_step
            if current_scroll >= page_height:
                break

            self.page.evaluate(f"window.scrollTo(0, {current_scroll})")
            self.page.wait_for_timeout(200)

        return location

    def _get_visible_images(self) -> List[dict]:
        """Holt alle aktuell sichtbaren Bilder mit Position."""
        return self.page.evaluate("""
            () => {
                const images = [];
                const scrollY = window.scrollY;
                const viewportHeight = window.innerHeight;

                document.querySelectorAll('img').forEach((img) => {
                    const rect = img.getBoundingClientRect();
                    const src = img.currentSrc || img.src;

                    // Nur sichtbare Bilder mit Mindestgröße
                    if (src && !src.startsWith('data:') &&
                        rect.width > 50 && rect.height > 50 &&
                        rect.bottom > 0 && rect.top < viewportHeight) {

                        images.push({
                            src: src,
                            alt: img.alt || '',
                            x: Math.round(rect.x),
                            y: Math.round(rect.y),
                            absolute_y: Math.round(rect.y + scrollY),
                            width: Math.round(rect.width),
                            height: Math.round(rect.height),
                            natural_width: img.naturalWidth,
                            natural_height: img.naturalHeight
                        });
                    }
                });

                return images;
            }
        """)

    def _match_image(self, reference_path: Path, img_info: dict) -> dict:
        """Vergleicht ein Seiten-Bild mit dem Referenzbild."""
        result = {"matched": False, "confidence": 0.0, "method": ""}

        try:
            # Bild herunterladen
            import requests
            import hashlib

            url = img_info["src"]
            filename = hashlib.md5(url.encode()).hexdigest()[:12] + ".jpg"
            temp_path = self._temp_dir / filename

            if not temp_path.exists():
                response = requests.get(url, timeout=10, headers={
                    "User-Agent": "Mozilla/5.0 Chrome/120.0.0.0"
                })
                if response.status_code == 200:
                    with open(temp_path, 'wb') as f:
                        f.write(response.content)
                else:
                    return result

            # Hash-Vergleich (schnell und zuverlässig)
            hash_result = self._hash_matcher.compare(reference_path, temp_path)

            if hash_result.is_match:
                result["matched"] = True
                result["confidence"] = hash_result.similarity
                result["method"] = "hash"
                return result

            # Feature-Vergleich nur als Fallback bei hoher Hash-Ähnlichkeit
            # UND nur wenn Feature-Confidence hoch genug ist (vermeidet false positives)
            if hash_result.similarity > 0.65:
                feature_result = self._feature_matcher.match(reference_path, temp_path)

                # Mindestens 30% Feature-Confidence für ein Match
                if feature_result.is_match and feature_result.confidence >= 0.30:
                    result["matched"] = True
                    result["confidence"] = feature_result.confidence
                    result["method"] = "feature"
                    return result

        except Exception as e:
            self.logger.debug(f"Match-Fehler für {img_info['src'][:50]}: {e}")

        return result

    def _capture_optimal_screenshot(
        self,
        location: ImageLocation,
        output_path: Path,
        context_pixels: int,
        min_zoom: float,
        max_zoom: float,
    ) -> dict:
        """
        Phase 2: Erstellt einen optimalen Screenshot mit Zoom.
        """
        try:
            # Viewport-Info
            viewport_height = self.page.evaluate("window.innerHeight")
            viewport_width = self.page.evaluate("window.innerWidth")

            # Benötigte Höhe für Bild + Kontext
            needed_height = location.height + (context_pixels * 2)

            # Zoom berechnen
            if needed_height > viewport_height:
                zoom = viewport_height / needed_height
                zoom = max(min_zoom, min(zoom, max_zoom))
            else:
                zoom = max_zoom  # Kein Zoom nötig

            self.logger.info(f"Bild-Höhe: {location.height}px")
            self.logger.info(f"Benötigt (mit Kontext): {needed_height}px")
            self.logger.info(f"Viewport: {viewport_height}px")
            self.logger.info(f"Zoom-Level: {zoom:.0%}")

            # Zoom anwenden
            if zoom < 1.0:
                self.page.evaluate(f"document.body.style.zoom = '{zoom}'")
                self.page.wait_for_timeout(300)

            # Scroll-Position berechnen (Bild zentriert)
            # Bei Zoom ändert sich die Position!
            zoomed_y = location.y * zoom
            zoomed_height = location.height * zoom
            zoomed_viewport = viewport_height  # Viewport bleibt gleich

            # Bild in der Mitte des Viewports
            scroll_to = zoomed_y - (zoomed_viewport - zoomed_height) / 2
            scroll_to = max(0, scroll_to)

            self.logger.info(f"Scroll zu: {scroll_to:.0f}px")

            # Scrollen
            self.page.evaluate(f"window.scrollTo(0, {scroll_to})")
            self.page.wait_for_timeout(500)

            # Fenster in Vordergrund
            self.page.bring_to_front()
            time.sleep(0.3)

            # Desktop-Screenshot
            output_path.parent.mkdir(parents=True, exist_ok=True)

            with mss.mss() as sct:
                monitor = sct.monitors[1]
                screenshot = sct.grab(monitor)

                img = Image.frombytes(
                    'RGB',
                    screenshot.size,
                    screenshot.bgra,
                    'raw',
                    'BGRX'
                )
                img.save(str(output_path), "PNG")

            # Zoom zurücksetzen
            if zoom < 1.0:
                self.page.evaluate("document.body.style.zoom = '1'")

            return {
                "success": True,
                "zoom": zoom,
                "scroll": int(scroll_to),
            }

        except Exception as e:
            self.logger.error(f"Screenshot-Fehler: {e}")
            return {"success": False, "error": str(e)}

    def locate_only(self, reference_image: Path) -> ImageLocation:
        """
        Nur Phase 1: Bild lokalisieren ohne Screenshot.
        """
        return self._locate_image(reference_image)

    def find_on_website(
        self,
        reference_image: Path,
        output_path: Path,
        base_url: str,
        max_pages: int = 50,
        context_pixels: int = 150,
    ) -> LocatorResult:
        """
        Durchsucht die gesamte Website nach dem Bild.

        Crawlt durch alle internen Links und sucht das Bild per Hash-Vergleich.
        Bei Fund: Navigiert zur Seite und erstellt optimalen Screenshot.

        Args:
            reference_image: Pfad zum Referenzbild
            output_path: Pfad für den Screenshot
            base_url: Basis-URL der Website (z.B. "https://example.com")
            max_pages: Maximale Anzahl zu prüfender Seiten
            context_pixels: Pixel Kontext um das Bild

        Returns:
            LocatorResult
        """
        from urllib.parse import urlparse, urljoin

        result = LocatorResult(success=False)

        # URLs die noch zu prüfen sind
        pending_urls = set()
        # Bereits besuchte URLs
        visited_urls = set()
        # Gefundene Seite
        found_url = None
        found_location = None

        # Base-URL parsen
        parsed_base = urlparse(base_url)
        base_domain = parsed_base.netloc

        self.logger.info("=" * 50)
        self.logger.info("WEBSITE-SUCHE")
        self.logger.info(f"Domain: {base_domain}")
        self.logger.info(f"Max. Seiten: {max_pages}")
        self.logger.info("=" * 50)

        # Mit Startseite beginnen
        pending_urls.add(base_url)

        page_count = 0

        while pending_urls and page_count < max_pages and not found_url:
            # Nächste URL holen
            current_url = pending_urls.pop()

            if current_url in visited_urls:
                continue

            visited_urls.add(current_url)
            page_count += 1

            self.logger.info(f"\n[{page_count}/{max_pages}] {current_url[:60]}...")

            try:
                # Seite laden
                self.page.goto(current_url, wait_until="networkidle", timeout=15000)
                self.page.wait_for_timeout(1000)

                # Auf dieser Seite nach dem Bild suchen
                location = self._quick_scan_page(reference_image)

                if location.found:
                    self.logger.info(f"   ✓ BILD GEFUNDEN!")
                    found_url = current_url
                    found_location = location
                    break

                # Neue Links sammeln (nur wenn noch nicht gefunden)
                new_links = self._collect_internal_links(base_domain)

                for link in new_links:
                    if link not in visited_urls:
                        pending_urls.add(link)

                self.logger.info(f"   {len(new_links)} neue Links gesammelt")

            except Exception as e:
                self.logger.warning(f"   Fehler: {e}")
                continue

        # Ergebnis
        if found_url and found_location:
            self.logger.info("")
            self.logger.info("=" * 50)
            self.logger.info(f"Bild gefunden auf: {found_url}")
            self.logger.info("Erstelle Screenshot...")
            self.logger.info("=" * 50)

            # Zur gefundenen Seite navigieren (falls nötig)
            if self.page.url != found_url:
                self.page.goto(found_url, wait_until="networkidle")
                self.page.wait_for_timeout(1000)

            # Optimalen Screenshot erstellen
            screenshot_result = self._capture_optimal_screenshot(
                location=found_location,
                output_path=output_path,
                context_pixels=context_pixels,
                min_zoom=0.5,
                max_zoom=1.0,
            )

            result.success = screenshot_result["success"]
            result.location = found_location
            result.screenshot_path = output_path if screenshot_result["success"] else None
            result.zoom_level = screenshot_result.get("zoom", 1.0)
            result.scroll_position = screenshot_result.get("scroll", 0)
        else:
            self.logger.warning(f"\nBild nicht gefunden nach {page_count} Seiten")
            result.error = f"Bild nicht gefunden (durchsucht: {page_count} Seiten)"

        return result

    def _quick_scan_page(self, reference_image: Path) -> ImageLocation:
        """
        Schneller Scan einer Seite - prüft nur sichtbare + lazy-loaded Bilder.
        """
        location = ImageLocation(found=False)

        # Alle Bilder auf der Seite (nicht nur sichtbare)
        all_images = self.page.evaluate("""
            () => {
                const images = [];
                const scrollY = window.scrollY;

                document.querySelectorAll('img').forEach((img) => {
                    const rect = img.getBoundingClientRect();
                    const src = img.currentSrc || img.src ||
                                img.dataset.src || img.dataset.lazySrc;

                    if (src && !src.startsWith('data:') &&
                        rect.width > 30 && rect.height > 30) {

                        images.push({
                            src: src,
                            alt: img.alt || '',
                            x: Math.round(rect.x),
                            y: Math.round(rect.y),
                            absolute_y: Math.round(rect.y + scrollY),
                            width: Math.round(rect.width),
                            height: Math.round(rect.height)
                        });
                    }
                });

                return images;
            }
        """)

        # Scroll zum Anfang
        self.page.evaluate("window.scrollTo(0, 0)")

        # Bilder prüfen
        for img_info in all_images:
            match_result = self._match_image(reference_image, img_info)

            if match_result["matched"]:
                location.found = True
                location.x = img_info["x"]
                location.y = img_info["absolute_y"]
                location.width = img_info["width"]
                location.height = img_info["height"]
                location.src = img_info["src"]
                location.confidence = match_result["confidence"]
                location.method = match_result["method"]
                return location

        return location

    def _collect_internal_links(self, base_domain: str) -> List[str]:
        """
        Sammelt alle internen Links auf der aktuellen Seite.
        """
        from urllib.parse import urlparse

        links = self.page.evaluate("""
            () => {
                const links = [];
                document.querySelectorAll('a[href]').forEach(a => {
                    const href = a.href;
                    if (href && !href.startsWith('javascript:') &&
                        !href.startsWith('mailto:') && !href.startsWith('tel:') &&
                        !href.includes('#')) {
                        links.push(href);
                    }
                });
                return [...new Set(links)];  // Unique
            }
        """)

        # Nur interne Links behalten
        internal_links = []
        for link in links:
            try:
                parsed = urlparse(link)
                if parsed.netloc == base_domain or parsed.netloc == "":
                    # Keine Dateien
                    path = parsed.path.lower()
                    if not any(path.endswith(ext) for ext in
                               ['.pdf', '.jpg', '.jpeg', '.png', '.gif', '.zip', '.doc']):
                        internal_links.append(link)
            except:
                continue

        return internal_links
