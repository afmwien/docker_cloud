"""
Cookie Handler - Robustes Cookie-Consent-Management

Features:
- Automatische CMP-Erkennung
- Multi-Strategie Accept-Handling
- Shadow DOM Support
- iFrame Support
- Storage State Management
- Retry-Mechanismen
- Ausführliches Logging
"""

import json
import logging
import time
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
from playwright.sync_api import Page, BrowserContext, Frame, Locator, TimeoutError as PlaywrightTimeout

from .consent_patterns import ConsentPatterns, KNOWN_COOKIE_VALUES


class ConsentAction(Enum):
    """Mögliche Consent-Aktionen."""
    ACCEPT_ALL = "accept_all"
    REJECT_ALL = "reject_all"
    ACCEPT_NECESSARY = "accept_necessary"
    CUSTOMIZE = "customize"


class CMPType(Enum):
    """Bekannte Consent Management Platforms."""
    ONETRUST = "onetrust"
    COOKIEBOT = "cookiebot"
    BORLABS = "borlabs"
    COMPLIANZ = "complianz"
    COOKIE_NOTICE = "cookie_notice"
    COOKIEYES = "cookieyes"
    KLARO = "klaro"
    OSANO = "osano"
    TRUSTARC = "trustarc"
    USERCENTRICS = "usercentrics"
    DIDOMI = "didomi"
    QUANTCAST = "quantcast"
    IUBENDA = "iubenda"
    COOKIESCRIPT = "cookiescript"
    GENERIC = "generic"
    UNKNOWN = "unknown"


@dataclass
class CookieHandlerResult:
    """Ergebnis eines Cookie-Handler-Durchlaufs."""
    success: bool
    action_taken: Optional[str] = None
    cmp_detected: Optional[str] = None
    selector_used: Optional[str] = None
    method_used: Optional[str] = None
    banner_found: bool = False
    error: Optional[str] = None
    duration_ms: float = 0
    cookies_before: int = 0
    cookies_after: int = 0


@dataclass
class CookieHandlerConfig:
    """Konfiguration für den Cookie Handler."""
    # Timing
    detection_timeout_ms: int = 5000
    click_timeout_ms: int = 3000
    wait_after_click_ms: int = 1000
    retry_attempts: int = 3
    retry_delay_ms: int = 500

    # Verhalten
    action: ConsentAction = ConsentAction.ACCEPT_ALL
    scroll_into_view: bool = True
    force_click: bool = False
    check_shadow_dom: bool = True
    check_iframes: bool = True

    # Storage
    storage_dir: Path = field(default_factory=lambda: Path("data/cookie_storage"))
    save_storage_state: bool = True
    load_storage_state: bool = True

    # Logging
    log_level: int = logging.INFO
    take_debug_screenshots: bool = False
    debug_screenshot_dir: Path = field(default_factory=lambda: Path("output/debug"))


class CookieHandler:
    """
    Robuster Cookie-Consent-Handler für Playwright.

    Verwendung:
        handler = CookieHandler(page)
        result = handler.handle_consent()

        # Mit Konfiguration
        config = CookieHandlerConfig(action=ConsentAction.REJECT_ALL)
        handler = CookieHandler(page, config)
        result = handler.handle_consent()
    """

    def __init__(
        self,
        page: Page,
        config: Optional[CookieHandlerConfig] = None,
        logger: Optional[logging.Logger] = None
    ):
        self.page = page
        self.config = config or CookieHandlerConfig()
        self.patterns = ConsentPatterns()
        self.logger = logger or self._setup_logger()
        self._detected_cmp: Optional[CMPType] = None

    def _setup_logger(self) -> logging.Logger:
        """Erstellt einen konfigurierten Logger."""
        logger = logging.getLogger(f"CookieHandler-{id(self)}")
        logger.setLevel(self.config.log_level)
        if not logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter(
                "%(asctime)s [%(levelname)s] %(message)s",
                datefmt="%H:%M:%S"
            ))
            logger.addHandler(handler)
        return logger

    def handle_consent(self) -> CookieHandlerResult:
        """
        Hauptmethode - Versucht Cookie-Consent automatisch zu behandeln.

        Strategie:
        1. Prüfe ob gespeicherter Storage State geladen werden kann
        2. Erkenne verwendete CMP
        3. Versuche CMP-spezifische Selektoren
        4. Fallback auf generische Selektoren
        5. Fallback auf Text-basierte Selektoren
        6. Fallback auf JavaScript-Injection
        7. Speichere Storage State für zukünftige Besuche
        """
        start_time = time.time()
        result = CookieHandlerResult(success=False)

        try:
            # Cookie-Zählung vorher
            result.cookies_before = len(self.page.context.cookies())

            # 1. Storage State prüfen
            if self.config.load_storage_state:
                if self._try_load_storage_state():
                    self.logger.info("Storage State geladen - Banner sollte nicht erscheinen")
                    # Kurz warten und prüfen ob Banner trotzdem da ist
                    self.page.wait_for_timeout(1000)

            # 2. Banner-Erkennung
            result.banner_found = self._detect_banner()

            if not result.banner_found:
                self.logger.info("Kein Cookie-Banner gefunden")
                result.success = True
                result.action_taken = "no_banner"
                return result

            self.logger.info("Cookie-Banner erkannt")

            # 3. CMP erkennen
            result.cmp_detected = self._detect_cmp()
            self.logger.info(f"CMP erkannt: {result.cmp_detected}")

            # 4. Multi-Strategie Consent-Handling
            strategies = [
                ("cmp_specific", self._try_cmp_specific),
                ("generic_css", self._try_generic_css),
                ("text_based", self._try_text_based),
                ("shadow_dom", self._try_shadow_dom),
                ("iframe", self._try_iframes),
                ("javascript", self._try_javascript_injection),
                ("force_click", self._try_force_click),
            ]

            for strategy_name, strategy_func in strategies:
                self.logger.debug(f"Versuche Strategie: {strategy_name}")

                for attempt in range(self.config.retry_attempts):
                    try:
                        selector = strategy_func()
                        if selector:
                            result.success = True
                            result.method_used = strategy_name
                            result.selector_used = selector
                            result.action_taken = self.config.action.value
                            self.logger.info(
                                f"Erfolgreich! Strategie: {strategy_name}, "
                                f"Selektor: {selector}"
                            )

                            # Warten bis Banner verschwindet
                            self._wait_for_banner_dismiss()

                            # Storage State speichern
                            if self.config.save_storage_state:
                                self._save_storage_state()

                            break
                    except Exception as e:
                        self.logger.debug(
                            f"Strategie {strategy_name} fehlgeschlagen "
                            f"(Versuch {attempt + 1}): {e}"
                        )
                        if attempt < self.config.retry_attempts - 1:
                            self.page.wait_for_timeout(self.config.retry_delay_ms)

                if result.success:
                    break

            if not result.success:
                result.error = "Keine Strategie erfolgreich"
                self.logger.warning("Cookie-Consent konnte nicht behandelt werden")

                # Debug-Screenshot bei Fehlschlag
                if self.config.take_debug_screenshots:
                    self._take_debug_screenshot("consent_failed")

        except Exception as e:
            result.error = str(e)
            self.logger.error(f"Fehler beim Cookie-Handling: {e}")

        finally:
            result.duration_ms = (time.time() - start_time) * 1000
            result.cookies_after = len(self.page.context.cookies())

        return result

    def _detect_banner(self) -> bool:
        """Erkennt ob ein Cookie-Banner sichtbar ist."""
        for selector in self.patterns.banner_detection_selectors:
            try:
                element = self.page.locator(selector).first
                if element.is_visible(timeout=500):
                    return True
            except:
                continue

        # Fallback: Prüfe auf typische Keywords im DOM
        try:
            body_text = self.page.locator("body").inner_text(timeout=2000).lower()
            keywords = ["cookie", "consent", "datenschutz", "privacy", "gdpr", "dsgvo"]
            if any(kw in body_text for kw in keywords):
                # Prüfe ob ein modaler Dialog sichtbar ist
                modals = self.page.locator(
                    "[role='dialog'], [role='alertdialog'], .modal, .overlay"
                )
                if modals.count() > 0:
                    return True
        except:
            pass

        return False

    def _detect_cmp(self) -> str:
        """Erkennt die verwendete Consent Management Platform."""
        cmp_indicators = {
            CMPType.ONETRUST: ["#onetrust", ".onetrust", "onetrust.com"],
            CMPType.COOKIEBOT: ["#Cybot", ".Cybot", "cookiebot.com"],
            CMPType.BORLABS: [".BorlabsCookie", "#BorlabsCookie", "borlabs"],
            CMPType.COMPLIANZ: [".cmplz", "#cmplz", "complianz"],
            CMPType.USERCENTRICS: ["#usercentrics", "usercentrics"],
            CMPType.DIDOMI: ["#didomi", ".didomi", "didomi"],
            CMPType.QUANTCAST: [".qc-cmp", "quantcast"],
            CMPType.IUBENDA: [".iubenda", "iubenda"],
            CMPType.COOKIEYES: [".cky-", "cookieyes"],
            CMPType.KLARO: [".klaro", "klaro"],
            CMPType.OSANO: [".osano", "osano"],
            CMPType.TRUSTARC: [".truste", "trustarc"],
            CMPType.COOKIESCRIPT: ["#cookiescript", "cookiescript"],
            CMPType.COOKIE_NOTICE: ["#cookie-notice", "#cookie-law-info", ".cli-"],
        }

        html = ""
        try:
            html = self.page.content().lower()
        except:
            pass

        for cmp_type, indicators in cmp_indicators.items():
            for indicator in indicators:
                if indicator.lower() in html:
                    self._detected_cmp = cmp_type
                    return cmp_type.value

        self._detected_cmp = CMPType.GENERIC
        return CMPType.GENERIC.value

    def _try_cmp_specific(self) -> Optional[str]:
        """Versucht CMP-spezifische Selektoren."""
        if not self._detected_cmp or self._detected_cmp == CMPType.GENERIC:
            return None

        selectors = self.patterns.get_cmp_specific_selectors(self._detected_cmp.value)

        for selector in selectors:
            if self._try_click(selector):
                return selector

        return None

    def _try_generic_css(self) -> Optional[str]:
        """Versucht generische CSS-Selektoren."""
        for selector in self.patterns.generic_css_selectors:
            if self._try_click(selector):
                return selector
        return None

    def _try_text_based(self) -> Optional[str]:
        """Versucht text-basierte Selektoren."""
        patterns = (
            self.patterns.accept_text_patterns
            if self.config.action == ConsentAction.ACCEPT_ALL
            else self.patterns.reject_selectors
        )

        for text_selector in patterns:
            if self._try_click(text_selector):
                return text_selector
        return None

    def _try_shadow_dom(self) -> Optional[str]:
        """Durchsucht Shadow DOMs nach Accept-Buttons."""
        if not self.config.check_shadow_dom:
            return None

        try:
            # JavaScript um Shadow DOM zu durchsuchen
            result = self.page.evaluate("""
                () => {
                    const findInShadow = (root) => {
                        const buttons = [];
                        const walker = document.createTreeWalker(
                            root,
                            NodeFilter.SHOW_ELEMENT
                        );

                        let node;
                        while (node = walker.nextNode()) {
                            if (node.shadowRoot) {
                                buttons.push(...findInShadow(node.shadowRoot));
                            }
                            if (node.tagName === 'BUTTON' ||
                                (node.tagName === 'A' && node.getAttribute('role') === 'button')) {
                                const text = node.innerText?.toLowerCase() || '';
                                if (text.includes('accept') || text.includes('akzeptieren') ||
                                    text.includes('zustimmen') || text.includes('allow')) {
                                    buttons.push(node);
                                }
                            }
                        }
                        return buttons;
                    };

                    const buttons = findInShadow(document);
                    if (buttons.length > 0) {
                        buttons[0].click();
                        return true;
                    }
                    return false;
                }
            """)

            if result:
                return "shadow_dom_button"
        except Exception as e:
            self.logger.debug(f"Shadow DOM Suche fehlgeschlagen: {e}")

        return None

    def _try_iframes(self) -> Optional[str]:
        """Durchsucht iFrames nach Cookie-Bannern."""
        if not self.config.check_iframes:
            return None

        try:
            frames = self.page.frames

            for frame in frames:
                if frame == self.page.main_frame:
                    continue

                # Prüfe ob Frame Cookie-relevante URL hat
                frame_url = frame.url.lower()
                if not any(kw in frame_url for kw in ["cookie", "consent", "privacy", "gdpr"]):
                    continue

                self.logger.debug(f"Prüfe iFrame: {frame_url}")

                for selector in self.patterns.get_all_accept_selectors()[:20]:
                    try:
                        element = frame.locator(selector).first
                        if element.is_visible(timeout=500):
                            element.click(timeout=self.config.click_timeout_ms)
                            return f"iframe:{selector}"
                    except:
                        continue

        except Exception as e:
            self.logger.debug(f"iFrame Suche fehlgeschlagen: {e}")

        return None

    def _try_javascript_injection(self) -> Optional[str]:
        """Versucht Consent via JavaScript zu setzen."""
        try:
            # Versuche bekannte Consent-APIs
            js_methods = [
                # OneTrust
                "if(typeof OneTrust !== 'undefined') { OneTrust.AllowAll(); return true; }",
                # CookieBot
                "if(typeof Cookiebot !== 'undefined') { Cookiebot.submitCustomConsent(true,true,true); return true; }",
                # Didomi
                "if(typeof Didomi !== 'undefined') { Didomi.setUserAgreeToAll(); return true; }",
                # Usercentrics
                "if(typeof UC_UI !== 'undefined') { UC_UI.acceptAllConsents(); return true; }",
                # Quantcast
                "if(typeof __tcfapi !== 'undefined') { __tcfapi('acceptAll', 2, function(){}); return true; }",
                # Generisch - Cookie setzen
                """
                document.cookie = 'cookie_consent=accepted; path=/; max-age=31536000';
                document.cookie = 'cookies_accepted=true; path=/; max-age=31536000';
                return true;
                """,
            ]

            for js in js_methods:
                try:
                    result = self.page.evaluate(f"() => {{ {js} return false; }}")
                    if result:
                        return f"javascript:{js[:50]}..."
                except:
                    continue

        except Exception as e:
            self.logger.debug(f"JavaScript Injection fehlgeschlagen: {e}")

        return None

    def _try_force_click(self) -> Optional[str]:
        """Versucht Force-Click auf sichtbare Buttons."""
        if not self.config.force_click:
            return None

        try:
            # Finde alle sichtbaren Buttons
            buttons = self.page.locator("button:visible, a[role='button']:visible")
            count = buttons.count()

            for i in range(min(count, 10)):
                try:
                    btn = buttons.nth(i)
                    text = btn.inner_text().lower()

                    accept_keywords = [
                        "accept", "akzeptieren", "zustimmen", "agree",
                        "allow", "ok", "got it", "verstanden"
                    ]

                    if any(kw in text for kw in accept_keywords):
                        btn.click(force=True, timeout=self.config.click_timeout_ms)
                        return f"force_click:button[{i}]"
                except:
                    continue

        except Exception as e:
            self.logger.debug(f"Force Click fehlgeschlagen: {e}")

        return None

    def _try_click(self, selector: str) -> bool:
        """Versucht auf ein Element zu klicken."""
        try:
            element = self.page.locator(selector).first

            # Prüfe ob Element existiert und sichtbar ist
            if not element.is_visible(timeout=500):
                return False

            # Optional: Scroll into view
            if self.config.scroll_into_view:
                try:
                    element.scroll_into_view_if_needed(timeout=1000)
                except:
                    pass

            # Klicken
            element.click(timeout=self.config.click_timeout_ms)

            # Warten nach Klick
            self.page.wait_for_timeout(self.config.wait_after_click_ms)

            return True

        except PlaywrightTimeout:
            return False
        except Exception as e:
            self.logger.debug(f"Klick auf {selector} fehlgeschlagen: {e}")
            return False

    def _wait_for_banner_dismiss(self, timeout_ms: int = 5000):
        """Wartet bis der Cookie-Banner verschwindet."""
        start = time.time()

        while (time.time() - start) * 1000 < timeout_ms:
            if not self._detect_banner():
                self.logger.debug("Banner verschwunden")
                return
            self.page.wait_for_timeout(200)

        self.logger.warning("Banner ist nach Klick noch sichtbar")

    def _get_storage_path(self) -> Path:
        """Gibt den Pfad für den Storage State zurück."""
        # Domain aus URL extrahieren
        url = self.page.url
        from urllib.parse import urlparse
        domain = urlparse(url).netloc.replace(".", "_").replace(":", "_")

        self.config.storage_dir.mkdir(parents=True, exist_ok=True)
        return self.config.storage_dir / f"{domain}_storage.json"

    def _save_storage_state(self):
        """Speichert den aktuellen Storage State."""
        try:
            storage_path = self._get_storage_path()
            self.page.context.storage_state(path=str(storage_path))
            self.logger.info(f"Storage State gespeichert: {storage_path}")
        except Exception as e:
            self.logger.warning(f"Storage State speichern fehlgeschlagen: {e}")

    def _try_load_storage_state(self) -> bool:
        """Versucht gespeicherten Storage State zu laden (Cookies + localStorage)."""
        storage_path = self._get_storage_path()

        if not storage_path.exists():
            return False

        try:
            with open(storage_path, "r") as f:
                storage = json.load(f)

            # Cookies aus Storage State hinzufügen
            if "cookies" in storage and storage["cookies"]:
                self.page.context.add_cookies(storage["cookies"])
                self.logger.debug(f"{len(storage['cookies'])} Cookies geladen")

            # LocalStorage aus Storage State wiederherstellen (WICHTIG für CMPs!)
            if "origins" in storage:
                for origin_data in storage["origins"]:
                    origin = origin_data.get("origin", "")
                    local_storage = origin_data.get("localStorage", [])

                    if local_storage and origin:
                        # Prüfe ob aktuelle Seite zu dieser Origin gehört
                        current_url = self.page.url
                        if origin in current_url or current_url.startswith(origin):
                            # LocalStorage via JavaScript setzen
                            for item in local_storage:
                                name = item.get("name", "")
                                value = item.get("value", "")
                                if name and value:
                                    try:
                                        # Escape für JavaScript
                                        escaped_name = name.replace("'", "\\'")
                                        escaped_value = value.replace("'", "\\'")
                                        self.page.evaluate(
                                            f"localStorage.setItem('{escaped_name}', '{escaped_value}')"
                                        )
                                    except:
                                        pass

                            self.logger.debug(f"{len(local_storage)} localStorage Items geladen")

            return True

        except Exception as e:
            self.logger.warning(f"Storage State laden fehlgeschlagen: {e}")

        return False

    def _take_debug_screenshot(self, name: str):
        """Erstellt einen Debug-Screenshot."""
        try:
            self.config.debug_screenshot_dir.mkdir(parents=True, exist_ok=True)
            path = self.config.debug_screenshot_dir / f"{name}_{int(time.time())}.png"
            self.page.screenshot(path=str(path))
            self.logger.debug(f"Debug-Screenshot: {path}")
        except Exception as e:
            self.logger.debug(f"Screenshot fehlgeschlagen: {e}")

    # =========================================================================
    # CONVENIENCE METHODS
    # =========================================================================

    def accept_all(self) -> CookieHandlerResult:
        """Akzeptiert alle Cookies."""
        self.config.action = ConsentAction.ACCEPT_ALL
        return self.handle_consent()

    def reject_all(self) -> CookieHandlerResult:
        """Lehnt alle optionalen Cookies ab."""
        self.config.action = ConsentAction.REJECT_ALL
        return self.handle_consent()

    def get_current_cookies(self) -> List[Dict[str, Any]]:
        """Gibt die aktuellen Cookies zurück."""
        return self.page.context.cookies()

    def clear_cookies(self):
        """Löscht alle Cookies."""
        self.page.context.clear_cookies()
        self.logger.info("Alle Cookies gelöscht")

    def set_consent_cookie(self, domain: str, accepted: bool = True):
        """Setzt ein generisches Consent-Cookie."""
        self.page.context.add_cookies([
            {
                "name": "cookie_consent",
                "value": "accepted" if accepted else "rejected",
                "domain": domain,
                "path": "/",
                "expires": int(time.time()) + 365 * 24 * 60 * 60,
            }
        ])


def create_cookie_aware_context(
    browser,
    storage_dir: Path = Path("data/cookie_storage"),
    **context_kwargs
) -> BrowserContext:
    """
    Factory-Funktion um einen BrowserContext mit Cookie-Handling zu erstellen.

    Lädt automatisch gespeicherte Storage States wenn vorhanden.
    """
    # Prüfe ob ein allgemeiner Storage State existiert
    general_storage = storage_dir / "general_storage.json"

    if general_storage.exists():
        try:
            context = browser.new_context(
                storage_state=str(general_storage),
                **context_kwargs
            )
            return context
        except:
            pass

    return browser.new_context(**context_kwargs)
