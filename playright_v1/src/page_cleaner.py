"""
Page Cleaner - Orchestriert die komplette Seitenreinigung

Ablauf:
1. Seite laden
2. Overlays entfernen (Loop bis sauber)
3. Cookies speichern
4. Sauberen Screenshot erstellen
"""

import logging
import time
from pathlib import Path
from typing import Optional, List
from dataclasses import dataclass, field
from playwright.sync_api import sync_playwright, Page, BrowserContext

from .browser import PersistentBrowser, BrowserConfig
from .cookie_handler import CookieHandler, CookieHandlerConfig
from .overlay_cleaner import OverlayCleaner, OverlayCleanerConfig, OverlayCleanerResult
from .screenshot import ScreenshotManager, ScreenshotConfig, ScreenshotResult


@dataclass
class PageCleanerConfig:
    """Konfiguration für den Page Cleaner."""
    # Browser
    profile_dir: Path = field(default_factory=lambda: Path("data/chrome_profile"))
    headless: bool = False  # False für Desktop-Screenshots

    # Overlay Cleaner
    max_cleaning_loops: int = 5
    wait_after_load_ms: int = 3000

    # Screenshots
    screenshot_dir: Path = field(default_factory=lambda: Path("output/screenshots"))
    include_browser_ui: bool = True

    # Verhalten
    reload_after_cleaning: bool = True  # Seite nach Cleaning neu laden
    save_cookies: bool = True


@dataclass
class PageCleanerResult:
    """Ergebnis der Seitenreinigung."""
    success: bool
    url: str
    title: str = ""

    # Cleaning
    cleaning_result: Optional[OverlayCleanerResult] = None
    page_is_clean: bool = False

    # Screenshot
    screenshot_result: Optional[ScreenshotResult] = None
    screenshot_path: Optional[Path] = None

    # Timing
    total_duration_ms: float = 0

    # Fehler
    error: Optional[str] = None


class PageCleaner:
    """
    Hauptklasse für die komplette Seitenreinigung.

    Orchestriert:
    - Browser mit persistentem Profil
    - Cookie-Handler
    - Overlay-Cleaner
    - Screenshot-Manager

    Verwendung:
        cleaner = PageCleaner()
        result = cleaner.clean_and_screenshot("https://example.com", "example.png")

        if result.success:
            print(f"Screenshot: {result.screenshot_path}")

    Mit Context Manager:
        with PageCleaner() as cleaner:
            result = cleaner.clean_and_screenshot(url, filename)
    """

    def __init__(
        self,
        config: Optional[PageCleanerConfig] = None,
        logger: Optional[logging.Logger] = None
    ):
        self.config = config or PageCleanerConfig()
        self.logger = logger or self._setup_logger()

        self._browser: Optional[PersistentBrowser] = None
        self._page: Optional[Page] = None

    def __enter__(self) -> "PageCleaner":
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def _setup_logger(self) -> logging.Logger:
        logger = logging.getLogger("PageCleaner")
        logger.setLevel(logging.INFO)
        if not logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter(
                "%(asctime)s [%(levelname)s] %(message)s",
                datefmt="%H:%M:%S"
            ))
            logger.addHandler(handler)
        return logger

    def start(self):
        """Startet den Browser."""
        browser_config = BrowserConfig(
            user_data_dir=self.config.profile_dir,
            headless=self.config.headless,
        )

        self._browser = PersistentBrowser(browser_config)
        self._browser.start()
        self._page = self._browser.new_page()

        self.logger.info(f"Browser gestartet (Profil: {self.config.profile_dir})")

    def close(self):
        """Schließt den Browser."""
        if self._browser:
            self._browser.close()
            self._browser = None
            self._page = None
            self.logger.info("Browser geschlossen")

    def clean_and_screenshot(
        self,
        url: str,
        screenshot_filename: str,
    ) -> PageCleanerResult:
        """
        Hauptmethode: Seite laden, reinigen, Screenshot erstellen.

        Args:
            url: URL der zu reinigenden Seite
            screenshot_filename: Dateiname für Screenshot

        Returns:
            PageCleanerResult mit allen Details
        """
        start_time = time.time()

        result = PageCleanerResult(
            success=False,
            url=url,
        )

        try:
            # Browser starten falls nötig
            if not self._browser or not self._page:
                self.start()

            self.logger.info(f"=== Starte Cleaning für: {url} ===")

            # Phase 1: Seite laden
            self.logger.info("Phase 1: Seite laden")
            self._page.goto(url, wait_until="networkidle", timeout=30000)
            self._page.wait_for_timeout(self.config.wait_after_load_ms)

            result.title = self._page.title()
            self.logger.info(f"Titel: {result.title}")

            # Phase 2: Overlays entfernen
            self.logger.info("Phase 2: Overlays entfernen")

            overlay_config = OverlayCleanerConfig(
                max_loops=self.config.max_cleaning_loops,
            )
            overlay_cleaner = OverlayCleaner(self._page, overlay_config, self.logger)

            result.cleaning_result = overlay_cleaner.clean()
            result.page_is_clean = result.cleaning_result.success

            self.logger.info(
                f"Cleaning: {result.cleaning_result.overlays_removed} Overlays entfernt "
                f"in {result.cleaning_result.loops_needed} Loops"
            )

            # Phase 3: Optional neu laden (für frischen State)
            if self.config.reload_after_cleaning and result.page_is_clean:
                self.logger.info("Phase 3: Seite neu laden")
                self._page.reload(wait_until="networkidle")
                self._page.wait_for_timeout(2000)

                # Quick-Clean nach Reload
                overlay_cleaner.quick_clean()

            # Phase 4: Screenshot erstellen
            self.logger.info("Phase 4: Screenshot erstellen")

            screenshot_config = ScreenshotConfig(
                output_dir=self.config.screenshot_dir,
                include_browser_ui=self.config.include_browser_ui,
            )
            screenshot_manager = ScreenshotManager(self._page, screenshot_config)

            if self.config.include_browser_ui:
                result.screenshot_result = screenshot_manager.capture_desktop(
                    screenshot_filename,
                    maximize=True,
                )
            else:
                result.screenshot_result = screenshot_manager.capture_viewport(
                    screenshot_filename
                )

            if result.screenshot_result.success:
                result.screenshot_path = result.screenshot_result.filepath
                self.logger.info(f"Screenshot: {result.screenshot_path}")
            else:
                self.logger.error(f"Screenshot fehlgeschlagen: {result.screenshot_result.error}")

            # Erfolg
            result.success = result.page_is_clean and result.screenshot_result.success

        except Exception as e:
            result.error = str(e)
            self.logger.error(f"Fehler: {e}")

        finally:
            result.total_duration_ms = (time.time() - start_time) * 1000

        self.logger.info(
            f"=== Fertig: {'Erfolg' if result.success else 'Fehlgeschlagen'} "
            f"({result.total_duration_ms:.0f}ms) ==="
        )

        return result

    def clean_multiple(
        self,
        urls_and_filenames: List[tuple],
    ) -> List[PageCleanerResult]:
        """
        Reinigt mehrere Seiten.

        Args:
            urls_and_filenames: Liste von (url, filename) Tupeln

        Returns:
            Liste von PageCleanerResult
        """
        results = []

        for url, filename in urls_and_filenames:
            result = self.clean_and_screenshot(url, filename)
            results.append(result)

        return results

    def clean_from_json(
        self,
        json_path: Path,
    ) -> List[PageCleanerResult]:
        """
        Reinigt Seiten aus einer JSON-Datei.

        Erwartet Format:
        [
            {"url": "...", "name": "...", "reference_image": "..."},
            ...
        ]
        """
        import json

        with open(json_path, "r", encoding="utf-8") as f:
            sites = json.load(f)

        results = []

        for site in sites:
            url = site["url"]
            name = site.get("name", "unknown")
            filename = f"{name.lower().replace(' ', '_')}.png"

            result = self.clean_and_screenshot(url, filename)
            results.append(result)

        return results


# Convenience-Funktion
def clean_page(
    url: str,
    screenshot_filename: str,
    profile_dir: str = "data/chrome_profile",
    include_browser_ui: bool = True,
) -> PageCleanerResult:
    """
    Einfache Funktion zum Reinigen einer einzelnen Seite.

    Args:
        url: URL der Seite
        screenshot_filename: Dateiname für Screenshot
        profile_dir: Chrome-Profil-Verzeichnis
        include_browser_ui: Desktop-Screenshot mit URL-Leiste

    Returns:
        PageCleanerResult
    """
    config = PageCleanerConfig(
        profile_dir=Path(profile_dir),
        include_browser_ui=include_browser_ui,
    )

    with PageCleaner(config) as cleaner:
        return cleaner.clean_and_screenshot(url, screenshot_filename)
