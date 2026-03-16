"""
Overlay Cleaner - Entfernt alle Störelemente von einer Seite

Hauptlogik mit Loop bis Seite sauber ist.
"""

import logging
import time
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field
from enum import Enum
from playwright.sync_api import Page

from .overlay_detector import OverlayDetector, DetectedOverlay
from .overlay_patterns import OverlayType, OverlayPatterns


class CleanAction(Enum):
    """Mögliche Aktionen zum Entfernen."""
    CLICK_CLOSE = "click_close"
    CLICK_ACCEPT = "click_accept"
    CLICK_OUTSIDE = "click_outside"
    PRESS_ESCAPE = "press_escape"
    HIDE_ELEMENT = "hide_element"
    REMOVE_ELEMENT = "remove_element"


@dataclass
class CleanResult:
    """Ergebnis eines Cleaning-Durchlaufs."""
    success: bool
    overlay_type: OverlayType
    action_taken: CleanAction
    selector_used: str
    error: Optional[str] = None


@dataclass
class OverlayCleanerConfig:
    """Konfiguration für den Overlay Cleaner."""
    max_loops: int = 5
    wait_after_action_ms: int = 1000
    wait_for_new_overlays_ms: int = 2000
    click_timeout_ms: int = 3000
    remove_chat_widgets: bool = False  # Optional, oft gewünscht
    remove_sticky_banners: bool = True
    use_cookie_handler: bool = True  # Cookie-Handler integrieren


@dataclass
class OverlayCleanerResult:
    """Gesamtergebnis des Cleanings."""
    success: bool
    loops_needed: int
    overlays_removed: int
    overlays_detected: List[str] = field(default_factory=list)
    actions_taken: List[CleanResult] = field(default_factory=list)
    remaining_overlays: List[str] = field(default_factory=list)
    duration_ms: float = 0


class OverlayCleaner:
    """
    Entfernt alle Störelemente von einer Seite.

    Verwendet einen Loop-Ansatz:
    1. Scan nach Overlays
    2. Entferne gefundene Overlays
    3. Warte auf neue Overlays
    4. Wiederhole bis sauber oder max_loops erreicht

    Verwendung:
        cleaner = OverlayCleaner(page)
        result = cleaner.clean()

        if result.success:
            print("Seite ist sauber!")
    """

    def __init__(
        self,
        page: Page,
        config: Optional[OverlayCleanerConfig] = None,
        logger: Optional[logging.Logger] = None
    ):
        self.page = page
        self.config = config or OverlayCleanerConfig()
        self.patterns = OverlayPatterns()
        self.detector = OverlayDetector(page, logger)
        self.logger = logger or self._setup_logger()

        # Cookie Handler importieren wenn aktiviert
        self._cookie_handler = None
        if self.config.use_cookie_handler:
            try:
                from ..cookie_handler import CookieHandler
                self._cookie_handler = CookieHandler(page)
            except ImportError:
                self.logger.warning("Cookie Handler nicht verfügbar")

    def _setup_logger(self) -> logging.Logger:
        logger = logging.getLogger(f"OverlayCleaner-{id(self)}")
        logger.setLevel(logging.INFO)
        if not logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter(
                "%(asctime)s [%(levelname)s] %(message)s",
                datefmt="%H:%M:%S"
            ))
            logger.addHandler(handler)
        return logger

    def clean(self) -> OverlayCleanerResult:
        """
        Hauptmethode - Entfernt alle Overlays in einem Loop.
        """
        start_time = time.time()
        result = OverlayCleanerResult(
            success=False,
            loops_needed=0,
            overlays_removed=0,
        )

        self.logger.info("Starte Overlay-Cleaning...")

        for loop in range(1, self.config.max_loops + 1):
            result.loops_needed = loop
            self.logger.info(f"--- Loop {loop}/{self.config.max_loops} ---")

            # Schritt 1: Scan
            overlays = self.detector.get_blocking_overlays()

            if not overlays:
                self.logger.info("Keine blockierenden Overlays gefunden")
                result.success = True
                break

            self.logger.info(f"Gefunden: {len(overlays)} Overlays")

            for overlay in overlays:
                result.overlays_detected.append(
                    f"{overlay.overlay_type.value}: {overlay.selector}"
                )

            # Schritt 2: Entfernen
            for overlay in overlays:
                clean_result = self._remove_overlay(overlay)
                result.actions_taken.append(clean_result)

                if clean_result.success:
                    result.overlays_removed += 1
                    self.logger.info(
                        f"✓ Entfernt: {overlay.overlay_type.value} "
                        f"via {clean_result.action_taken.value}"
                    )
                else:
                    self.logger.warning(
                        f"✗ Fehlgeschlagen: {overlay.overlay_type.value}"
                    )

            # Schritt 3: Warten auf neue Overlays
            self.page.wait_for_timeout(self.config.wait_for_new_overlays_ms)

        # Finale Prüfung
        is_clean, remaining = self.detector.check_page_is_clean()

        if not is_clean:
            result.remaining_overlays = [
                f"{o.overlay_type.value}: {o.selector}" for o in remaining
            ]
            self.logger.warning(
                f"Nach {self.config.max_loops} Loops noch "
                f"{len(remaining)} Overlays übrig"
            )
        else:
            result.success = True
            self.logger.info("✓ Seite ist sauber!")

        result.duration_ms = (time.time() - start_time) * 1000

        return result

    def _remove_overlay(self, overlay: DetectedOverlay) -> CleanResult:
        """Entfernt ein einzelnes Overlay."""

        # Strategie basierend auf Overlay-Typ
        strategies = self._get_removal_strategies(overlay.overlay_type)

        for action, execute_fn in strategies:
            try:
                success = execute_fn(overlay)
                if success:
                    self.page.wait_for_timeout(self.config.wait_after_action_ms)

                    # Prüfen ob wirklich weg
                    if not overlay.element.is_visible(timeout=500):
                        return CleanResult(
                            success=True,
                            overlay_type=overlay.overlay_type,
                            action_taken=action,
                            selector_used=overlay.selector,
                        )
            except Exception as e:
                self.logger.debug(f"Strategie {action.value} fehlgeschlagen: {e}")
                continue

        # Fallback: Element verstecken via JavaScript
        try:
            self._hide_element(overlay)
            return CleanResult(
                success=True,
                overlay_type=overlay.overlay_type,
                action_taken=CleanAction.HIDE_ELEMENT,
                selector_used=overlay.selector,
            )
        except Exception as e:
            return CleanResult(
                success=False,
                overlay_type=overlay.overlay_type,
                action_taken=CleanAction.HIDE_ELEMENT,
                selector_used=overlay.selector,
                error=str(e),
            )

    def _get_removal_strategies(self, overlay_type: OverlayType):
        """Gibt Entfernungsstrategien für einen Overlay-Typ zurück."""

        # Cookie-Banner: Spezieller Handler
        if overlay_type == OverlayType.COOKIE_BANNER and self._cookie_handler:
            return [
                (CleanAction.CLICK_ACCEPT, self._use_cookie_handler),
            ]

        # Standard-Strategien nach Typ
        strategies = {
            OverlayType.NEWSLETTER: [
                (CleanAction.CLICK_CLOSE, self._click_close_button),
                (CleanAction.PRESS_ESCAPE, self._press_escape),
                (CleanAction.CLICK_OUTSIDE, self._click_outside),
            ],
            OverlayType.PUSH_NOTIFICATION: [
                (CleanAction.CLICK_CLOSE, self._click_close_button),
                (CleanAction.PRESS_ESCAPE, self._press_escape),
            ],
            OverlayType.AGE_VERIFICATION: [
                (CleanAction.CLICK_ACCEPT, self._click_accept_button),
            ],
            OverlayType.ADVERTISEMENT: [
                (CleanAction.CLICK_CLOSE, self._click_close_button),
                (CleanAction.PRESS_ESCAPE, self._press_escape),
                (CleanAction.CLICK_OUTSIDE, self._click_outside),
            ],
            OverlayType.EXIT_INTENT: [
                (CleanAction.CLICK_CLOSE, self._click_close_button),
                (CleanAction.PRESS_ESCAPE, self._press_escape),
            ],
            OverlayType.GENERIC_MODAL: [
                (CleanAction.CLICK_CLOSE, self._click_close_button),
                (CleanAction.PRESS_ESCAPE, self._press_escape),
                (CleanAction.CLICK_OUTSIDE, self._click_outside),
            ],
            OverlayType.CHAT_WIDGET: [
                (CleanAction.CLICK_CLOSE, self._click_close_button),
                (CleanAction.HIDE_ELEMENT, self._hide_element),
            ],
            OverlayType.STICKY_BANNER: [
                (CleanAction.CLICK_CLOSE, self._click_close_button),
                (CleanAction.HIDE_ELEMENT, self._hide_element),
            ],
        }

        return strategies.get(overlay_type, [
            (CleanAction.CLICK_CLOSE, self._click_close_button),
            (CleanAction.PRESS_ESCAPE, self._press_escape),
        ])

    def _use_cookie_handler(self, overlay: DetectedOverlay) -> bool:
        """Verwendet den Cookie-Handler."""
        if self._cookie_handler:
            result = self._cookie_handler.handle_consent()
            return result.success
        return False

    def _click_close_button(self, overlay: DetectedOverlay) -> bool:
        """Klickt auf den Schließen-Button."""
        close_selectors = self.patterns.get_close_selectors(overlay.overlay_type)

        for selector in close_selectors:
            try:
                btn = self.page.locator(selector).first
                if btn.is_visible(timeout=500):
                    btn.click(timeout=self.config.click_timeout_ms)
                    return True
            except:
                continue

        # Fallback: Generische Close-Buttons im Overlay suchen
        try:
            close_btn = overlay.element.locator(
                "button[class*='close'], [aria-label*='close' i], .close, .btn-close"
            ).first
            if close_btn.is_visible(timeout=500):
                close_btn.click(timeout=self.config.click_timeout_ms)
                return True
        except:
            pass

        return False

    def _click_accept_button(self, overlay: DetectedOverlay) -> bool:
        """Klickt auf den Akzeptieren-Button."""
        close_selectors = self.patterns.get_close_selectors(overlay.overlay_type)

        for selector in close_selectors:
            try:
                btn = self.page.locator(selector).first
                if btn.is_visible(timeout=500):
                    btn.click(timeout=self.config.click_timeout_ms)
                    return True
            except:
                continue

        return False

    def _press_escape(self, overlay: DetectedOverlay) -> bool:
        """Drückt Escape um das Overlay zu schließen."""
        try:
            self.page.keyboard.press("Escape")
            self.page.wait_for_timeout(500)
            return not overlay.element.is_visible(timeout=500)
        except:
            return False

    def _click_outside(self, overlay: DetectedOverlay) -> bool:
        """Klickt außerhalb des Overlays."""
        try:
            # Klick in die linke obere Ecke
            self.page.mouse.click(10, 10)
            self.page.wait_for_timeout(500)
            return not overlay.element.is_visible(timeout=500)
        except:
            return False

    def _hide_element(self, overlay: DetectedOverlay) -> bool:
        """Versteckt das Element via JavaScript."""
        try:
            self.page.evaluate(f"""
                const el = document.querySelector('{overlay.selector}');
                if (el) {{
                    el.style.display = 'none';
                    el.style.visibility = 'hidden';
                    el.remove();
                }}
            """)
            return True
        except:
            return False

    def quick_clean(self) -> bool:
        """
        Schnelle Reinigung ohne vollständigen Loop.
        Gut für Seiten wo bereits Cookies gesetzt sind.
        """
        # Kurz warten auf Overlays
        self.page.wait_for_timeout(1000)

        # Escape drücken (schließt viele Modals)
        self.page.keyboard.press("Escape")
        self.page.wait_for_timeout(500)

        # Cookie-Handler falls Cookie-Banner
        if self._cookie_handler:
            self._cookie_handler.handle_consent()

        # Prüfen
        is_clean, _ = self.detector.check_page_is_clean()
        return is_clean
