"""
Persistent Browser Manager - Verwaltet persistente Chrome-Profile

Features:
- Persistentes User Data Directory für dauerhafte Cookie-Speicherung
- Automatische Profilverwaltung
- Stealth-Integration
- Synchroner und asynchroner Modus
"""

import sys
import shutil
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass, field
from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page, Playwright

# Config importieren
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from config import get_chrome_profile_path, settings

from .stealth import apply_stealth_settings, get_stealth_context_options


@dataclass
class BrowserConfig:
    """Konfiguration für den persistenten Browser."""

    # Pfade - Default aus zentraler Config
    user_data_dir: Path = field(default_factory=get_chrome_profile_path)
    downloads_dir: Path = field(default_factory=lambda: Path("output/downloads"))

    # Browser-Optionen
    headless: bool = True
    slow_mo: int = 0  # Millisekunden zwischen Aktionen (für Debugging)

    # Viewport
    viewport_width: int = 1920
    viewport_height: int = 1080

    # Stealth
    use_stealth: bool = True

    # Locale
    locale: str = "de-DE"
    timezone: str = "Europe/Vienna"

    # Performance
    disable_images: bool = False
    disable_javascript: bool = False

    # Proxy (optional)
    proxy_server: Optional[str] = None
    proxy_username: Optional[str] = None
    proxy_password: Optional[str] = None


class PersistentBrowser:
    """
    Manager für einen persistenten Chromium-Browser mit dauerhafter Cookie-Speicherung.

    Verwendung:
        # Als Context Manager
        with PersistentBrowser() as browser:
            page = browser.new_page()
            page.goto("https://example.com")
            # Cookies werden automatisch im Profil gespeichert

        # Manuell
        browser = PersistentBrowser()
        browser.start()
        page = browser.new_page()
        # ...
        browser.close()

    Die Cookies bleiben nach dem Schließen erhalten und werden beim
    nächsten Start automatisch geladen.
    """

    def __init__(self, config: Optional[BrowserConfig] = None):
        self.config = config or BrowserConfig()
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._pages: list[Page] = []

    def __enter__(self) -> "PersistentBrowser":
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def start(self) -> None:
        """Startet den Browser mit persistentem Profil."""
        # Verzeichnisse erstellen
        self.config.user_data_dir.mkdir(parents=True, exist_ok=True)
        self.config.downloads_dir.mkdir(parents=True, exist_ok=True)

        # Playwright starten
        self._playwright = sync_playwright().start()

        # Browser-Launch-Optionen
        launch_options = self._get_launch_options()

        # Browser mit persistentem Kontext starten
        self._context = self._playwright.chromium.launch_persistent_context(
            user_data_dir=str(self.config.user_data_dir),
            **launch_options
        )

        # Stealth-Skripte für alle neuen Seiten
        if self.config.use_stealth:
            self._context.add_init_script(self._get_stealth_script())

    def _get_launch_options(self) -> Dict[str, Any]:
        """Erstellt die Launch-Optionen für den Browser."""
        options = {
            "headless": self.config.headless,
            "slow_mo": self.config.slow_mo,
            "locale": self.config.locale,
            "timezone_id": self.config.timezone,
            "accept_downloads": True,
            "ignore_https_errors": True,
            "bypass_csp": True,
            "java_script_enabled": not self.config.disable_javascript,
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-web-security",
                "--disable-features=IsolateOrigins,site-per-process",
                "--start-maximized",  # Fenster maximiert starten
            ],
        }

        # WICHTIG: Kein fester Viewport bei maximiertem Fenster
        if not self.config.headless:
            # no_viewport = True damit Browser echte Fenstergröße nutzt
            options["no_viewport"] = True
        else:
            options["viewport"] = {
                "width": self.config.viewport_width,
                "height": self.config.viewport_height,
            }

        # User-Agent setzen
        if self.config.use_stealth:
            options["user_agent"] = (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )

        # Proxy konfigurieren
        if self.config.proxy_server:
            options["proxy"] = {"server": self.config.proxy_server}
            if self.config.proxy_username and self.config.proxy_password:
                options["proxy"]["username"] = self.config.proxy_username
                options["proxy"]["password"] = self.config.proxy_password

        # Bilder deaktivieren (Performance)
        if self.config.disable_images:
            options["args"].append("--blink-settings=imagesEnabled=false")

        # Extra HTTP Headers
        options["extra_http_headers"] = {
            "Accept-Language": f"{self.config.locale},{self.config.locale.split('-')[0]};q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
        }

        return options

    def _get_stealth_script(self) -> str:
        """Gibt das Stealth-Skript zurück."""
        return """
            // WebDriver verstecken
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined,
            });

            // Chrome Runtime simulieren
            window.chrome = {
                runtime: {},
            };

            // Permissions API patchen
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                    Promise.resolve({ state: Notification.permission }) :
                    originalQuery(parameters)
            );

            // Plugins simulieren
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5],
            });

            // Languages setzen
            Object.defineProperty(navigator, 'languages', {
                get: () => ['de-DE', 'de', 'en-US', 'en'],
            });

            // Hardware Concurrency
            Object.defineProperty(navigator, 'hardwareConcurrency', {
                get: () => 8,
            });

            // Device Memory
            Object.defineProperty(navigator, 'deviceMemory', {
                get: () => 8,
            });

            // WebGL Vendor/Renderer
            const getParameter = WebGLRenderingContext.prototype.getParameter;
            WebGLRenderingContext.prototype.getParameter = function(parameter) {
                if (parameter === 37445) {
                    return 'Intel Inc.';
                }
                if (parameter === 37446) {
                    return 'Intel Iris OpenGL Engine';
                }
                return getParameter.apply(this, arguments);
            };
        """

    def new_page(self) -> Page:
        """Erstellt eine neue Seite."""
        if not self._context:
            raise RuntimeError("Browser nicht gestartet. Rufe start() auf.")

        page = self._context.new_page()
        self._pages.append(page)

        # Zusätzliche Stealth-Einstellungen per Seite
        if self.config.use_stealth:
            apply_stealth_settings(page)

        return page

    @property
    def context(self) -> BrowserContext:
        """Gibt den Browser-Kontext zurück."""
        if not self._context:
            raise RuntimeError("Browser nicht gestartet.")
        return self._context

    @property
    def pages(self) -> list[Page]:
        """Gibt alle offenen Seiten zurück."""
        return self._pages

    def get_cookies(self, urls: Optional[list[str]] = None) -> list[dict]:
        """Gibt alle Cookies zurück (optional gefiltert nach URLs)."""
        if not self._context:
            raise RuntimeError("Browser nicht gestartet.")

        if urls:
            return self._context.cookies(urls)
        return self._context.cookies()

    def add_cookies(self, cookies: list[dict]) -> None:
        """Fügt Cookies hinzu."""
        if not self._context:
            raise RuntimeError("Browser nicht gestartet.")
        self._context.add_cookies(cookies)

    def clear_cookies(self) -> None:
        """Löscht alle Cookies."""
        if not self._context:
            raise RuntimeError("Browser nicht gestartet.")
        self._context.clear_cookies()

    def close(self) -> None:
        """Schließt den Browser (Cookies werden automatisch im Profil gespeichert)."""
        if self._context:
            self._context.close()
            self._context = None

        if self._playwright:
            self._playwright.stop()
            self._playwright = None

        self._pages.clear()

    def reset_profile(self) -> None:
        """Löscht das gesamte Browser-Profil (alle Cookies, Cache, etc.)."""
        self.close()

        if self.config.user_data_dir.exists():
            shutil.rmtree(self.config.user_data_dir)
            print(f"Profil gelöscht: {self.config.user_data_dir}")

    def get_profile_size(self) -> int:
        """Gibt die Größe des Profil-Ordners in Bytes zurück."""
        if not self.config.user_data_dir.exists():
            return 0

        total = 0
        for path in self.config.user_data_dir.rglob("*"):
            if path.is_file():
                total += path.stat().st_size
        return total

    def get_profile_size_mb(self) -> float:
        """Gibt die Größe des Profil-Ordners in MB zurück."""
        return self.get_profile_size() / (1024 * 1024)


# Convenience-Funktion
def create_persistent_browser(
    profile_dir: str = "data/chrome_profile",
    headless: bool = True,
    **kwargs
) -> PersistentBrowser:
    """
    Erstellt einen persistenten Browser mit den angegebenen Optionen.

    Args:
        profile_dir: Pfad zum Chrome-Profil
        headless: Headless-Modus
        **kwargs: Weitere Optionen für BrowserConfig

    Returns:
        PersistentBrowser-Instanz
    """
    config = BrowserConfig(
        user_data_dir=Path(profile_dir),
        headless=headless,
        **kwargs
    )
    return PersistentBrowser(config)
