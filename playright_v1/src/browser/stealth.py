"""
Browser Stealth Module - Umgeht Bot-Erkennung
"""
from playwright.sync_api import Page, BrowserContext


def apply_stealth_settings(page: Page) -> None:
    """
    Wendet Stealth-Einstellungen an um Bot-Erkennung zu umgehen.
    """
    # WebDriver Flag verstecken
    page.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined,
        });
    """)

    # Chrome Runtime simulieren
    page.add_init_script("""
        window.chrome = {
            runtime: {},
        };
    """)

    # Permissions simulieren
    page.add_init_script("""
        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (parameters) => (
            parameters.name === 'notifications' ?
                Promise.resolve({ state: Notification.permission }) :
                originalQuery(parameters)
        );
    """)

    # Plugins simulieren
    page.add_init_script("""
        Object.defineProperty(navigator, 'plugins', {
            get: () => [1, 2, 3, 4, 5],
        });
    """)

    # Languages simulieren
    page.add_init_script("""
        Object.defineProperty(navigator, 'languages', {
            get: () => ['de-DE', 'de', 'en-US', 'en'],
        });
    """)


def get_stealth_context_options() -> dict:
    """
    Gibt Optionen für einen Browser-Context zurück, der Bot-Erkennung umgeht.
    """
    return {
        "viewport": {"width": 1920, "height": 1080},
        "user_agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "locale": "de-DE",
        "timezone_id": "Europe/Vienna",
        "geolocation": {"latitude": 48.2082, "longitude": 16.3738},  # Wien
        "permissions": ["geolocation"],
        "color_scheme": "light",
        "java_script_enabled": True,
        "bypass_csp": True,
        "ignore_https_errors": True,
        "extra_http_headers": {
            "Accept-Language": "de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
        },
    }


def create_stealth_page(context: BrowserContext) -> Page:
    """
    Erstellt eine neue Seite mit Stealth-Einstellungen.
    """
    page = context.new_page()
    apply_stealth_settings(page)
    return page
