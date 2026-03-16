"""
Screenshot Manager - Desktop-Screenshots mit URL-Leiste

Verwendet mss für Desktop-Screenshots (inkl. Browser-UI).
"""

import time
from pathlib import Path
from typing import Optional, Tuple
from dataclasses import dataclass
import mss
from PIL import Image
from playwright.sync_api import Page

from .window_manager import WindowManager


@dataclass
class ScreenshotConfig:
    """Screenshot-Konfiguration."""
    output_dir: Path = Path("output/screenshots")
    format: str = "png"  # png oder jpg
    quality: int = 95  # Nur für jpg
    include_browser_ui: bool = True  # Desktop-Screenshot mit URL-Leiste
    wait_before_screenshot_ms: int = 1000
    monitor: int = 1  # 1 = Hauptmonitor


@dataclass
class ScreenshotResult:
    """Ergebnis eines Screenshots."""
    success: bool
    filepath: Optional[Path] = None
    width: int = 0
    height: int = 0
    error: Optional[str] = None


class ScreenshotManager:
    """
    Erstellt Screenshots von Webseiten.

    Unterstützt:
    - Viewport-Screenshots (nur Seiteninhalt)
    - Desktop-Screenshots (mit Browser-UI/URL-Leiste)
    - Full-Page-Screenshots

    Verwendung:
        sm = ScreenshotManager(page)

        # Desktop-Screenshot mit URL-Leiste
        result = sm.capture_desktop("mein_screenshot.png")

        # Nur Seiteninhalt
        result = sm.capture_viewport("seite.png")
    """

    def __init__(
        self,
        page: Page,
        config: Optional[ScreenshotConfig] = None
    ):
        self.page = page
        self.config = config or ScreenshotConfig()
        self.window_manager = WindowManager(page)

        # Output-Verzeichnis erstellen
        self.config.output_dir.mkdir(parents=True, exist_ok=True)

    def capture_desktop(
        self,
        filename: str,
        maximize: bool = True,
        wait_ms: Optional[int] = None
    ) -> ScreenshotResult:
        """
        Erstellt einen Desktop-Screenshot (inkl. Browser-UI).

        Args:
            filename: Dateiname (ohne Pfad)
            maximize: Fenster vorher maximieren
            wait_ms: Wartezeit vor Screenshot

        Returns:
            ScreenshotResult
        """
        try:
            filepath = self.config.output_dir / filename

            # Fenster maximieren
            if maximize:
                self.window_manager.maximize()
                self.page.wait_for_timeout(500)

            # In Vordergrund bringen
            self.window_manager.bring_to_front()

            # Warten
            wait = wait_ms or self.config.wait_before_screenshot_ms
            time.sleep(wait / 1000)

            # Desktop-Screenshot mit mss
            with mss.mss() as sct:
                monitor = sct.monitors[self.config.monitor]
                screenshot = sct.grab(monitor)

                # Zu PIL Image konvertieren
                img = Image.frombytes(
                    'RGB',
                    screenshot.size,
                    screenshot.bgra,
                    'raw',
                    'BGRX'
                )

                # Speichern
                if self.config.format.lower() == "jpg":
                    img.save(str(filepath), "JPEG", quality=self.config.quality)
                else:
                    img.save(str(filepath), "PNG")

            return ScreenshotResult(
                success=True,
                filepath=filepath,
                width=img.width,
                height=img.height,
            )

        except Exception as e:
            return ScreenshotResult(
                success=False,
                error=str(e),
            )

    def capture_viewport(
        self,
        filename: str,
        full_page: bool = False
    ) -> ScreenshotResult:
        """
        Erstellt einen Viewport-Screenshot (nur Seiteninhalt).

        Args:
            filename: Dateiname (ohne Pfad)
            full_page: Ganze Seite oder nur sichtbarer Bereich

        Returns:
            ScreenshotResult
        """
        try:
            filepath = self.config.output_dir / filename

            # Playwright Screenshot
            self.page.screenshot(
                path=str(filepath),
                full_page=full_page,
            )

            # Größe ermitteln
            with Image.open(filepath) as img:
                width, height = img.size

            return ScreenshotResult(
                success=True,
                filepath=filepath,
                width=width,
                height=height,
            )

        except Exception as e:
            return ScreenshotResult(
                success=False,
                error=str(e),
            )

    def capture_element(
        self,
        selector: str,
        filename: str
    ) -> ScreenshotResult:
        """
        Erstellt einen Screenshot von einem bestimmten Element.

        Args:
            selector: CSS-Selektor des Elements
            filename: Dateiname

        Returns:
            ScreenshotResult
        """
        try:
            filepath = self.config.output_dir / filename

            element = self.page.locator(selector).first
            element.screenshot(path=str(filepath))

            with Image.open(filepath) as img:
                width, height = img.size

            return ScreenshotResult(
                success=True,
                filepath=filepath,
                width=width,
                height=height,
            )

        except Exception as e:
            return ScreenshotResult(
                success=False,
                error=str(e),
            )

    def capture_full_page(
        self,
        filename: str,
        wait_ms: int = 1000
    ) -> ScreenshotResult:
        """
        Erstellt einen Full-Page Screenshot der gesamten Seite.

        Playwright scrollt automatisch und erstellt ein Bild der kompletten Seite.
        HINWEIS: Kein Browser-UI (URL-Leiste) im Screenshot.

        Args:
            filename: Dateiname
            wait_ms: Wartezeit vor Screenshot

        Returns:
            ScreenshotResult
        """
        try:
            filepath = self.config.output_dir / filename

            # Warten bis Seite vollständig geladen
            self.page.wait_for_timeout(wait_ms)

            # Full-Page Screenshot mit Playwright
            self.page.screenshot(
                path=str(filepath),
                full_page=True,
            )

            with Image.open(filepath) as img:
                width, height = img.size

            return ScreenshotResult(
                success=True,
                filepath=filepath,
                width=width,
                height=height,
            )

        except Exception as e:
            return ScreenshotResult(
                success=False,
                error=str(e),
            )

    def capture_scrolling_desktop(
        self,
        filename: str,
        scroll_step: int = 800,
        max_height: int = 10000,
        overlap: int = 100
    ) -> ScreenshotResult:
        """
        Erstellt Full-Page Desktop-Screenshot durch Scrollen und Zusammenfügen.

        Macht mehrere Desktop-Screenshots beim Scrollen und fügt sie zusammen.
        INKLUDIERT Browser-UI (URL-Leiste) im ersten Screenshot.

        Args:
            filename: Dateiname
            scroll_step: Pixel pro Scroll-Schritt
            max_height: Maximale Gesamthöhe
            overlap: Überlappung zwischen Screenshots in Pixeln

        Returns:
            ScreenshotResult
        """
        try:
            filepath = self.config.output_dir / filename

            # Fenster maximieren
            self.window_manager.maximize()
            self.page.wait_for_timeout(500)
            self.window_manager.bring_to_front()

            # Scroll zum Anfang
            self.page.evaluate("window.scrollTo(0, 0)")
            self.page.wait_for_timeout(300)

            # Seitenhöhe ermitteln
            page_height = self.page.evaluate("document.documentElement.scrollHeight")
            viewport_height = self.page.evaluate("window.innerHeight")

            screenshots = []
            current_scroll = 0

            with mss.mss() as sct:
                monitor = sct.monitors[self.config.monitor]

                while current_scroll < min(page_height, max_height):
                    # Screenshot machen
                    time.sleep(0.3)
                    screenshot = sct.grab(monitor)

                    img = Image.frombytes(
                        'RGB',
                        screenshot.size,
                        screenshot.bgra,
                        'raw',
                        'BGRX'
                    )
                    screenshots.append((current_scroll, img))

                    # Weiter scrollen
                    current_scroll += scroll_step - overlap
                    if current_scroll >= page_height:
                        break

                    self.page.evaluate(f"window.scrollTo(0, {current_scroll})")
                    self.page.wait_for_timeout(200)

            if not screenshots:
                return ScreenshotResult(success=False, error="Keine Screenshots erstellt")

            # Bilder zusammenfügen
            first_img = screenshots[0][1]
            total_width = first_img.width

            # Gesamthöhe berechnen (grob)
            # Wir nehmen das erste Bild komplett und fügen dann die unteren Teile hinzu
            browser_ui_height = first_img.height - viewport_height  # URL-Leiste etc.

            total_height = browser_ui_height + min(page_height, max_height)
            total_height = min(total_height, max_height)

            # Neues Bild erstellen
            combined = Image.new('RGB', (total_width, total_height))

            # Erstes Bild (mit Browser-UI) einfügen
            combined.paste(first_img, (0, 0))

            # Weitere Bilder einfügen (nur Content-Bereich)
            for i, (scroll_pos, img) in enumerate(screenshots[1:], 1):
                # Nur den unteren Teil einfügen (ohne Browser-UI)
                content_area = img.crop((0, browser_ui_height, img.width, img.height))

                y_pos = browser_ui_height + scroll_pos
                if y_pos + content_area.height <= total_height:
                    combined.paste(content_area, (0, y_pos))

            # Auf tatsächliche Höhe zuschneiden
            combined = combined.crop((0, 0, total_width, min(combined.height, total_height)))

            # Speichern
            combined.save(str(filepath), "PNG")

            return ScreenshotResult(
                success=True,
                filepath=filepath,
                width=combined.width,
                height=combined.height,
            )

        except Exception as e:
            return ScreenshotResult(
                success=False,
                error=str(e),
            )

    def capture_with_comparison(
        self,
        filename: str,
        reference_image: Path,
        threshold: float = 0.95
    ) -> Tuple[ScreenshotResult, bool, float]:
        """
        Erstellt Screenshot und vergleicht mit Referenzbild.

        Returns:
            (ScreenshotResult, is_match, similarity_score)
        """
        result = self.capture_viewport(filename)

        if not result.success:
            return result, False, 0.0

        # Vergleich (vereinfacht)
        try:
            from PIL import ImageChops
            import math

            img1 = Image.open(result.filepath)
            img2 = Image.open(reference_image)

            # Auf gleiche Größe bringen
            img2 = img2.resize(img1.size)

            # Differenz berechnen
            diff = ImageChops.difference(img1, img2)

            # RMS (Root Mean Square) Error
            h = diff.histogram()
            sq = (value * ((idx % 256) ** 2) for idx, value in enumerate(h))
            sum_of_squares = sum(sq)
            rms = math.sqrt(sum_of_squares / float(img1.size[0] * img1.size[1]))

            # Normalisieren (0-1, wobei 1 = identisch)
            max_rms = 255
            similarity = 1 - (rms / max_rms)

            is_match = similarity >= threshold

            return result, is_match, similarity

        except Exception as e:
            return result, False, 0.0
