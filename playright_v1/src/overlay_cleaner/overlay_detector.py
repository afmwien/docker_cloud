"""
Overlay Detector - Erkennt alle sichtbaren Störelemente auf einer Seite
"""

import logging
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from playwright.sync_api import Page, Locator

from .overlay_patterns import OverlayPatterns, OverlayType


@dataclass
class DetectedOverlay:
    """Repräsentiert ein erkanntes Overlay."""
    overlay_type: OverlayType
    selector: str
    element: Optional[Locator] = None
    is_visible: bool = True
    priority: int = 0  # Höher = wichtiger, zuerst entfernen
    text_preview: str = ""


class OverlayDetector:
    """
    Scannt eine Seite nach allen Arten von Störelementen.

    Verwendung:
        detector = OverlayDetector(page)
        overlays = detector.scan()

        for overlay in overlays:
            print(f"{overlay.overlay_type}: {overlay.selector}")
    """

    # Prioritäten für Entfernungsreihenfolge
    PRIORITY_MAP = {
        OverlayType.COOKIE_BANNER: 100,      # Höchste Priorität
        OverlayType.AGE_VERIFICATION: 90,
        OverlayType.PUSH_NOTIFICATION: 80,
        OverlayType.GENERIC_MODAL: 70,
        OverlayType.NEWSLETTER: 60,
        OverlayType.ADVERTISEMENT: 50,
        OverlayType.EXIT_INTENT: 40,
        OverlayType.FEEDBACK_WIDGET: 30,
        OverlayType.CHAT_WIDGET: 20,
        OverlayType.SOCIAL_WIDGET: 15,
        OverlayType.STICKY_BANNER: 10,
    }

    def __init__(
        self,
        page: Page,
        logger: Optional[logging.Logger] = None
    ):
        self.page = page
        self.patterns = OverlayPatterns()
        self.logger = logger or self._setup_logger()

    def _setup_logger(self) -> logging.Logger:
        logger = logging.getLogger(f"OverlayDetector-{id(self)}")
        logger.setLevel(logging.INFO)
        if not logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter(
                "%(asctime)s [%(levelname)s] %(message)s",
                datefmt="%H:%M:%S"
            ))
            logger.addHandler(handler)
        return logger

    def scan(self) -> List[DetectedOverlay]:
        """
        Scannt die Seite nach allen sichtbaren Overlays.

        Returns:
            Liste von erkannten Overlays, sortiert nach Priorität
        """
        detected = []

        self.logger.debug("Starte Overlay-Scan...")

        # Alle Overlay-Typen durchgehen
        all_selectors = self.patterns.get_all_detection_selectors()

        for overlay_type, selectors in all_selectors.items():
            for selector in selectors:
                try:
                    overlay = self._check_selector(selector, overlay_type)
                    if overlay:
                        detected.append(overlay)
                        self.logger.debug(
                            f"Gefunden: {overlay_type.value} - {selector}"
                        )
                except Exception as e:
                    self.logger.debug(f"Fehler bei {selector}: {e}")

        # Nach Priorität sortieren (höchste zuerst)
        detected.sort(key=lambda x: x.priority, reverse=True)

        self.logger.info(f"Scan abgeschlossen: {len(detected)} Overlays gefunden")

        return detected

    def _check_selector(
        self,
        selector: str,
        overlay_type: OverlayType
    ) -> Optional[DetectedOverlay]:
        """Prüft ob ein Selektor auf ein sichtbares Element trifft."""
        try:
            locator = self.page.locator(selector).first

            # Prüfen ob Element existiert und sichtbar ist
            if locator.count() == 0:
                return None

            if not locator.is_visible(timeout=500):
                return None

            # Text-Preview extrahieren
            text_preview = ""
            try:
                text = locator.inner_text(timeout=500)
                text_preview = text[:100].replace("\n", " ").strip()
            except:
                pass

            return DetectedOverlay(
                overlay_type=overlay_type,
                selector=selector,
                element=locator,
                is_visible=True,
                priority=self.PRIORITY_MAP.get(overlay_type, 0),
                text_preview=text_preview,
            )

        except Exception:
            return None

    def scan_for_type(self, overlay_type: OverlayType) -> List[DetectedOverlay]:
        """Scannt nur nach einem bestimmten Overlay-Typ."""
        detected = []
        selectors = self.patterns.get_detection_selectors(overlay_type)

        for selector in selectors:
            try:
                overlay = self._check_selector(selector, overlay_type)
                if overlay:
                    detected.append(overlay)
            except:
                pass

        return detected

    def has_any_overlay(self) -> bool:
        """Schnelle Prüfung ob irgendein Overlay sichtbar ist."""
        # Nur die häufigsten/wichtigsten prüfen
        quick_check_types = [
            OverlayType.COOKIE_BANNER,
            OverlayType.NEWSLETTER,
            OverlayType.GENERIC_MODAL,
            OverlayType.PUSH_NOTIFICATION,
        ]

        for overlay_type in quick_check_types:
            if self.scan_for_type(overlay_type):
                return True

        return False

    def get_blocking_overlays(self) -> List[DetectedOverlay]:
        """
        Gibt nur Overlays zurück, die die Interaktion blockieren.
        (z.B. Modale Dialoge, nicht Chat-Widgets)
        """
        blocking_types = [
            OverlayType.COOKIE_BANNER,
            OverlayType.AGE_VERIFICATION,
            OverlayType.NEWSLETTER,
            OverlayType.ADVERTISEMENT,
            OverlayType.EXIT_INTENT,
            OverlayType.GENERIC_MODAL,
        ]

        all_overlays = self.scan()
        return [o for o in all_overlays if o.overlay_type in blocking_types]

    def check_page_is_clean(self) -> Tuple[bool, List[DetectedOverlay]]:
        """
        Prüft ob die Seite "sauber" ist (keine blockierenden Overlays).

        Returns:
            (is_clean, remaining_overlays)
        """
        blocking = self.get_blocking_overlays()
        return len(blocking) == 0, blocking
