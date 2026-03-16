"""
Zentrale Konfiguration für das Playwright-Projekt

Liest Einstellungen aus config/settings.json und stellt sie zur Verfügung.
"""

import json
from pathlib import Path
from typing import Optional
from dataclasses import dataclass


# Projekt-Root ermitteln
PROJECT_ROOT = Path(__file__).parent.parent
CONFIG_FILE = PROJECT_ROOT / "config" / "settings.json"


@dataclass
class ChromeProfileConfig:
    """Chrome-Profil Konfiguration."""
    use_project_profile: bool = True
    project_profile_path: Path = Path("data/chrome_profile")
    external_profile_path: Optional[Path] = None

    def get_profile_path(self) -> Path:
        """Gibt den aktiven Profil-Pfad zurück."""
        if self.use_project_profile:
            return PROJECT_ROOT / self.project_profile_path
        elif self.external_profile_path:
            return self.external_profile_path
        else:
            return PROJECT_ROOT / self.project_profile_path


@dataclass
class BrowserSettings:
    """Browser-Einstellungen."""
    headless: bool = True
    viewport_width: int = 1920
    viewport_height: int = 1080
    locale: str = "de-DE"
    timezone: str = "Europe/Vienna"


@dataclass
class CookieSettings:
    """Cookie-Einstellungen."""
    auto_accept: bool = True
    save_storage_state: bool = True


class Settings:
    """Zentrale Settings-Klasse."""

    def __init__(self):
        self.chrome_profile = ChromeProfileConfig()
        self.browser = BrowserSettings()
        self.cookies = CookieSettings()
        self._load()

    def _load(self):
        """Lädt Einstellungen aus der JSON-Datei."""
        if not CONFIG_FILE.exists():
            print(f"Keine Konfiguration gefunden: {CONFIG_FILE}")
            return

        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)

            # Chrome Profile
            if "chrome_profile" in data:
                cp = data["chrome_profile"]
                self.chrome_profile.use_project_profile = cp.get("use_project_profile", True)
                if cp.get("project_profile_path"):
                    self.chrome_profile.project_profile_path = Path(cp["project_profile_path"])
                if cp.get("external_profile_path"):
                    self.chrome_profile.external_profile_path = Path(cp["external_profile_path"])

            # Browser
            if "browser" in data:
                b = data["browser"]
                self.browser.headless = b.get("headless", True)
                self.browser.viewport_width = b.get("viewport_width", 1920)
                self.browser.viewport_height = b.get("viewport_height", 1080)
                self.browser.locale = b.get("locale", "de-DE")
                self.browser.timezone = b.get("timezone", "Europe/Vienna")

            # Cookies
            if "cookies" in data:
                c = data["cookies"]
                self.cookies.auto_accept = c.get("auto_accept", True)
                self.cookies.save_storage_state = c.get("save_storage_state", True)

        except Exception as e:
            print(f"Fehler beim Laden der Konfiguration: {e}")

    def save(self):
        """Speichert die aktuellen Einstellungen."""
        data = {
            "chrome_profile": {
                "use_project_profile": self.chrome_profile.use_project_profile,
                "project_profile_path": str(self.chrome_profile.project_profile_path),
                "external_profile_path": str(self.chrome_profile.external_profile_path) if self.chrome_profile.external_profile_path else None,
            },
            "browser": {
                "headless": self.browser.headless,
                "viewport_width": self.browser.viewport_width,
                "viewport_height": self.browser.viewport_height,
                "locale": self.browser.locale,
                "timezone": self.browser.timezone,
            },
            "cookies": {
                "auto_accept": self.cookies.auto_accept,
                "save_storage_state": self.cookies.save_storage_state,
            }
        }

        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

        print(f"Konfiguration gespeichert: {CONFIG_FILE}")


# Globale Settings-Instanz
settings = Settings()


def get_chrome_profile_path() -> Path:
    """Convenience-Funktion für den Chrome-Profil-Pfad."""
    return settings.chrome_profile.get_profile_path()
