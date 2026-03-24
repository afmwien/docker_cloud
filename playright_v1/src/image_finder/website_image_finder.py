"""
Website Image Finder - 2-Phasen-System

Phase 1: Headless-Crawler (schnell)
- Durchsucht alle Seiten im Headless-Modus
- Findet Bild per Hash-Vergleich
- Gibt URL + Position zurück

Phase 2: Sichtbarer Browser (Screenshot)
- Öffnet gefundene URL mit persistentem Profil
- Cookie-Handler, Overlay-Cleaner
- Desktop-Screenshot mit URL-Bar
"""

import logging
import time
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List, Set
from urllib.parse import urlparse
from io import BytesIO

# SSL-Warnungen unterdrücken
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from playwright.sync_api import sync_playwright, Page, Browser
from PIL import Image
import imagehash
import requests

# Lokale Module
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from image_matcher.hash_matcher import HashMatcher


@dataclass
class SearchResult:
    """Ergebnis der Headless-Suche."""
    found: bool = False
    url: str = ""
    image_src: str = ""
    position_x: int = 0
    position_y: int = 0
    width: int = 0
    height: int = 0
    pages_searched: int = 0
    confidence: float = 0.0


@dataclass
class FinalResult:
    """Endergebnis mit Screenshot."""
    success: bool = False
    search_result: Optional[SearchResult] = None
    screenshot_path: Optional[Path] = None
    zoom_level: float = 1.0
    error: str = ""


class HeadlessCrawler:
    """
    Phase 1: Schnelle Headless-Suche durch alle Seiten.
    """

    def __init__(
        self,
        reference_image: Path,
        hash_threshold: int = 25,
        logger: Optional[logging.Logger] = None
    ):
        self.reference_image = reference_image
        self.hash_threshold = hash_threshold
        self.logger = logger or logging.getLogger("HeadlessCrawler")

        # Referenz-Hash berechnen
        self._ref_hash = self._compute_hash(reference_image)
        self.logger.info(f"Referenz-Hash berechnet: {str(self._ref_hash)[:20]}...")

    def _compute_hash(self, image_path: Path) -> imagehash.ImageHash:
        """Berechnet pHash für ein Bild."""
        img = Image.open(image_path)
        return imagehash.phash(img, hash_size=16)

    def search(
        self,
        base_url: str,
        max_pages: int = 500,
        timeout_per_page: int = 10000,
    ) -> SearchResult:
        """
        Durchsucht die Website im Headless-Modus.

        Args:
            base_url: Startseite der Website
            max_pages: Maximale Anzahl Seiten
            timeout_per_page: Timeout pro Seite in ms

        Returns:
            SearchResult mit URL falls gefunden
        """
        result = SearchResult()

        pending_urls: Set[str] = {base_url}
        visited_urls: Set[str] = set()

        parsed_base = urlparse(base_url)
        base_domain = parsed_base.netloc

        self.logger.info("=" * 60)
        self.logger.info("HEADLESS-SUCHE GESTARTET")
        self.logger.info(f"Domain: {base_domain}")
        self.logger.info(f"Max. Seiten: {max_pages}")
        self.logger.info("=" * 60)

        start_time = time.time()

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"
            )
            page = context.new_page()

            page_count = 0

            while pending_urls and page_count < max_pages:
                current_url = pending_urls.pop()

                if current_url in visited_urls:
                    continue

                visited_urls.add(current_url)
                page_count += 1

                # Fortschritt alle 10 Seiten loggen
                if page_count % 10 == 0 or page_count <= 5:
                    elapsed = time.time() - start_time
                    rate = page_count / elapsed if elapsed > 0 else 0
                    self.logger.info(f"[{page_count}/{max_pages}] {rate:.1f} Seiten/s - {current_url[:50]}...")

                try:
                    # Seite laden (schnell, ohne networkidle)
                    page.goto(current_url, wait_until="domcontentloaded", timeout=timeout_per_page)

                    # Kurz warten für lazy-loading
                    page.wait_for_timeout(500)

                    # Bilder auf dieser Seite prüfen
                    match = self._check_page_images(page)

                    if match:
                        result.found = True
                        result.url = current_url
                        result.image_src = match["src"]
                        result.position_x = match["x"]
                        result.position_y = match["y"]
                        result.width = match["width"]
                        result.height = match["height"]
                        result.confidence = match["confidence"]
                        result.pages_searched = page_count

                        elapsed = time.time() - start_time
                        self.logger.info("")
                        self.logger.info("=" * 60)
                        self.logger.info(f"✓ BILD GEFUNDEN!")
                        self.logger.info(f"  Seite: {current_url}")
                        self.logger.info(f"  Nach: {page_count} Seiten in {elapsed:.1f}s")
                        self.logger.info(f"  Confidence: {match['confidence']:.1%}")
                        self.logger.info("=" * 60)
                        break

                    # Neue Links sammeln
                    new_links = self._collect_links(page, base_domain)
                    for link in new_links:
                        if link not in visited_urls:
                            pending_urls.add(link)

                except Exception as e:
                    self.logger.debug(f"Fehler bei {current_url[:50]}: {e}")
                    continue

            browser.close()

        elapsed = time.time() - start_time
        result.pages_searched = page_count

        if not result.found:
            self.logger.warning(f"Bild nicht gefunden nach {page_count} Seiten ({elapsed:.1f}s)")

        return result

    def _check_page_images(self, page: Page) -> Optional[dict]:
        """Prüft alle Bilder auf der aktuellen Seite (parallelisiert)."""
        from concurrent.futures import ThreadPoolExecutor, as_completed

        # Alle Bild-URLs sammeln
        images = page.evaluate("""
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
                            x: Math.round(rect.x),
                            y: Math.round(rect.y + scrollY),
                            width: Math.round(rect.width),
                            height: Math.round(rect.height)
                        });
                    }
                });

                return images;
            }
        """)

        if not images:
            return None

        # Parallelisierter Download und Hash-Check
        def check_single_image(img_info: dict) -> Optional[dict]:
            try:
                response = requests.get(
                    img_info["src"],
                    timeout=3,
                    headers={"User-Agent": "Mozilla/5.0 Chrome/120.0.0.0"},
                    verify=False  # Schneller, SSL-Probleme vermeiden
                )

                if response.status_code != 200 or len(response.content) < 1000:
                    return None

                img = Image.open(BytesIO(response.content))
                img_hash = imagehash.phash(img, hash_size=16)
                distance = self._ref_hash - img_hash

                if distance <= self.hash_threshold:
                    return {
                        "src": img_info["src"],
                        "x": img_info["x"],
                        "y": img_info["y"],
                        "width": img_info["width"],
                        "height": img_info["height"],
                        "confidence": 1 - (distance / 256)
                    }
                return None
            except Exception:
                return None

        # Parallel prüfen (max 10 gleichzeitig)
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(check_single_image, img): img for img in images}

            for future in as_completed(futures):
                result = future.result()
                if result:
                    # Gefunden! Alle anderen abbrechen
                    executor.shutdown(wait=False, cancel_futures=True)
                    return result

        return None

    def _collect_links(self, page: Page, base_domain: str) -> List[str]:
        """Sammelt alle internen Links."""
        links = page.evaluate("""
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
                return [...new Set(links)];
            }
        """)

        # Nur interne Links
        internal = []
        for link in links:
            try:
                parsed = urlparse(link)
                if parsed.netloc == base_domain:
                    # Keine Dateien
                    path = parsed.path.lower()
                    if not any(path.endswith(ext) for ext in
                               ['.pdf', '.jpg', '.jpeg', '.png', '.gif', '.zip', '.doc', '.mp4', '.mp3']):
                        internal.append(link)
            except:
                pass

        return internal


class WebsiteImageFinder:
    """
    Orchestrator für das 2-Phasen-System.

    Verwendung:
        finder = WebsiteImageFinder()
        result = finder.find_and_screenshot(
            reference_image=Path("referenz.jpg"),
            website_url="https://example.com",
            output_path=Path("screenshot.png")
        )
    """

    def __init__(self, logger: Optional[logging.Logger] = None):
        self.logger = logger or logging.getLogger("WebsiteImageFinder")

        # Konfiguriere Logging
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter(
                '%(asctime)s [%(levelname)s] %(message)s',
                datefmt='%H:%M:%S'
            ))
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)

    def find_and_screenshot(
        self,
        reference_image: Path,
        website_url: str,
        output_path: Path,
        max_pages: int = 500,
        context_pixels: int = 150,
        chrome_profile_path: Optional[Path] = None,
        skip_search: bool = False,
    ) -> FinalResult:
        """
        Hauptmethode: Sucht Bild und erstellt Screenshot.

        Args:
            reference_image: Pfad zum Referenzbild
            website_url: Basis-URL der Website
            output_path: Pfad für den Screenshot
            max_pages: Maximale Seiten für Headless-Suche
            context_pixels: Pixel Kontext um das Bild
            chrome_profile_path: Pfad zum Chrome-Profil (optional)
            skip_search: Wenn True, überspringe Headless-Suche und gehe direkt zur URL

        Returns:
            FinalResult
        """
        result = FinalResult()

        if skip_search:
            # Direkt zur URL navigieren ohne Suche
            self.logger.info("")
            self.logger.info("╔" + "═" * 58 + "╗")
            self.logger.info("║  DIREKTER MODUS (ohne Suche)                            ║")
            self.logger.info("╚" + "═" * 58 + "╝")

            # Fake SearchResult für Kompatibilität
            search_result = SearchResult(
                found=True,
                url=website_url,
                image_src="",
                position_y=300,  # Standard-Position
                height=200,
            )
            result.search_result = search_result
        else:
            # ============================================
            # PHASE 1: Headless-Suche
            # ============================================
            self.logger.info("")
            self.logger.info("╔" + "═" * 58 + "╗")
            self.logger.info("║  PHASE 1: HEADLESS-SUCHE                                ║")
            self.logger.info("╚" + "═" * 58 + "╝")

            crawler = HeadlessCrawler(
                reference_image=reference_image,
                logger=self.logger
            )

            search_result = crawler.search(
                base_url=website_url,
                max_pages=max_pages
            )

            result.search_result = search_result

            if not search_result.found:
                result.error = f"Bild nicht gefunden nach {search_result.pages_searched} Seiten"
                return result

        # ============================================
        # PHASE 2: Sichtbarer Browser + Screenshot
        # ============================================
        self.logger.info("")
        self.logger.info("╔" + "═" * 58 + "╗")
        self.logger.info("║  PHASE 2: SICHTBARER BROWSER + SCREENSHOT               ║")
        self.logger.info("╚" + "═" * 58 + "╝")

        try:
            screenshot_result = self._capture_with_visible_browser(
                url=search_result.url,
                image_src=search_result.image_src,  # Bild-URL für Zentrierung
                image_position_y=search_result.position_y,
                image_height=search_result.height,
                output_path=output_path,
                context_pixels=context_pixels,
                chrome_profile_path=chrome_profile_path,
                reference_image=reference_image,
            )

            result.success = screenshot_result["success"]
            result.screenshot_path = output_path if screenshot_result["success"] else None
            result.zoom_level = screenshot_result.get("zoom", 1.0)

            if result.success:
                self.logger.info(f"✓ Screenshot gespeichert: {output_path}")

        except Exception as e:
            result.error = str(e)
            self.logger.error(f"Screenshot-Fehler: {e}")

        return result

    def _capture_with_visible_browser(
        self,
        url: str,
        image_src: str,
        image_position_y: int,
        image_height: int,
        output_path: Path,
        context_pixels: int,
        chrome_profile_path: Optional[Path],
        reference_image: Optional[Path] = None,
        max_attempts: int = 6,  # Mehr Versuche für verschiedene Scroll-Positionen
    ) -> dict:
        """
        Phase 2: Sichtbarer Browser mit allen Modulen.
        Findet das Bild im Browser und zentriert es für den Screenshot.
        """
        import mss

        result = {"success": False, "zoom": 1.0}

        # Chrome-Profil Pfad
        profile_path = chrome_profile_path or Path("data/chrome_profile")
        profile_path.mkdir(parents=True, exist_ok=True)

        with sync_playwright() as p:
            # Sichtbaren Browser mit persistentem Profil starten
            self.logger.info(f"Starte Chrome mit Profil: {profile_path}")

            context = p.chromium.launch_persistent_context(
                user_data_dir=str(profile_path),
                headless=False,
                channel="chrome",
                args=[
                    "--start-maximized",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-infobars",
                    "--no-default-browser-check",
                    "--no-first-run",
                    "--disable-extensions",
                    # Dialoge deaktivieren
                    "--disable-notifications",
                    "--disable-popup-blocking",
                    "--disable-features=ExternalProtocolDialogShowAlwaysOpenCheckbox",
                    "--autoplay-policy=no-user-gesture-required",
                    # Permission-Prompts unterdrücken
                    "--deny-permission-prompts",
                    # Warnungs-Banner unterdrücken
                    "--test-type",
                    "--disable-gpu",
                ],
                ignore_default_args=["--enable-automation", "--no-sandbox"],
                no_viewport=True,
            )

            page = context.pages[0] if context.pages else context.new_page()

            try:
                # URL laden
                self.logger.info(f"Lade URL: {url[:60]}...")
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(2000)  # Extra Zeit für dynamischen Content

                # Cookie-Handler
                self._handle_cookies(page)

                # Overlay-Cleaner
                self._remove_overlays(page)

                # Fenster maximieren (Windows API)
                self._maximize_window(page)

                # Viewport-Höhe ermitteln
                viewport_height = page.evaluate("window.innerHeight")

                # ============================================
                # BILD IM BROWSER FINDEN UND ZENTRIEREN
                # ============================================
                image_info = self._find_and_center_image(page, image_src, viewport_height)

                if image_info:
                    actual_y = image_info["y"]
                    actual_height = image_info["height"]
                    self.logger.info(f"✓ Bild im Browser gefunden: Y={actual_y:.0f}px, Höhe={actual_height:.0f}px")
                else:
                    # Fallback auf Headless-Werte
                    actual_y = image_position_y
                    actual_height = image_height
                    self.logger.warning(f"Bild nicht gefunden, nutze Headless-Position: Y={actual_y}px")

                # Zoom berechnen falls nötig
                needed_height = actual_height + (context_pixels * 2)
                if needed_height > viewport_height:
                    zoom = viewport_height / needed_height
                    zoom = max(0.5, min(zoom, 1.0))
                else:
                    zoom = 1.0

                result["zoom"] = zoom

                if zoom < 1.0:
                    page.evaluate(f"document.body.style.zoom = '{zoom}'")
                    page.wait_for_timeout(300)
                    self.logger.info(f"Zoom: {zoom:.0%}")
                    # Position neu berechnen nach Zoom
                    actual_y = actual_y * zoom
                    actual_height = actual_height * zoom

                # Bild MITTIG im Viewport zentrieren
                scroll_to = actual_y - (viewport_height - actual_height) / 2
                scroll_to = max(0, scroll_to)

                self.logger.info(f"Zentriere Bild: Scrolle zu {scroll_to:.0f}px")

                # Banner-Blocker installieren (MutationObserver der neue Banner sofort entfernt)
                self._install_banner_blocker(page)

                # Warten statt erstem Screenshot
                time.sleep(2)

                # Screenshot mit Validierung (mehrere Versuche mit feinen Anpassungen)
                scroll_offsets = [-50, +50, -100, +100, -150]
                base_scroll = scroll_to

                for attempt, offset in enumerate(scroll_offsets[:max_attempts], 1):
                    current_scroll = max(0, base_scroll + offset)

                    self.logger.info(f"Versuch {attempt}: Scrolle zu {current_scroll:.0f}px (Offset: {offset:+d})")

                    # VOR JEDEM VERSUCH: Nochmal auf verzögerte Banner/Overlays prüfen
                    self._quick_remove_overlays(page)

                    page.evaluate(f"window.scrollTo(0, {current_scroll})")
                    page.wait_for_timeout(1200)  # Warten auf Lazy-Loading

                    # Nochmal prüfen (Banner können nach Scroll erscheinen)
                    self._quick_remove_overlays(page)

                    # Fenster in Vordergrund
                    page.bring_to_front()
                    time.sleep(0.8)

                    # Desktop-Screenshot
                    output_path.parent.mkdir(parents=True, exist_ok=True)

                    with mss.mss() as sct:
                        monitor = sct.monitors[1]  # Hauptmonitor
                        screenshot = sct.grab(monitor)

                        from PIL import Image as PILImage
                        img = PILImage.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
                        img.save(str(output_path), "PNG")

                    # Screenshot validieren - nur bei 50%+ Match akzeptieren
                    if reference_image and self._validate_screenshot(output_path, reference_image):
                        self.logger.info(f"✓ Screenshot validiert (Versuch {attempt})")
                        result["success"] = True
                        break
                    elif reference_image:
                        self.logger.warning(f"Bild nicht vollständig sichtbar (Versuch {attempt}/{max_attempts})")
                    else:
                        # Keine Validierung, Screenshot akzeptieren
                        result["success"] = True
                        break
                        break

                if not result["success"] and reference_image:
                    self.logger.warning("Validierung nach allen Versuchen fehlgeschlagen, verwende letzten Screenshot")
                    result["success"] = True  # Trotzdem speichern

            finally:
                context.close()

        return result

    def _handle_cookies(self, page: Page):
        """Cookie-Banner behandeln."""
        try:
            # Import Cookie-Handler falls vorhanden
            from cookie_handler.cookie_handler import CookieHandler
            handler = CookieHandler(page)
            handler.handle_consent()
            self.logger.info("✓ Cookie-Handler ausgeführt")
        except ImportError:
            # Fallback: Einfache Selektoren
            self.logger.info("Cookie-Handler nicht verfügbar, versuche Standard-Selektoren...")
            selectors = [
                "button:has-text('Accept')",
                "button:has-text('Akzeptieren')",
                "button:has-text('Alle akzeptieren')",
                "[id*='accept']",
                "[class*='accept']",
            ]
            for sel in selectors:
                try:
                    btn = page.locator(sel).first
                    if btn.is_visible(timeout=1000):
                        btn.click()
                        self.logger.info(f"  Cookie-Button geklickt: {sel[:30]}")
                        page.wait_for_timeout(500)
                        break
                except:
                    pass

    def _remove_overlays(self, page: Page):
        """Overlays entfernen."""
        try:
            from overlay_cleaner.overlay_cleaner import OverlayCleaner
            cleaner = OverlayCleaner(page)
            cleaner.clean()
            self.logger.info("✓ Overlay-Cleaner ausgeführt")
        except ImportError:
            # Fallback
            self.logger.info("Overlay-Cleaner nicht verfügbar, versuche Standard-Entfernung...")
            page.evaluate("""
                () => {
                    // Häufige Overlay-Selektoren
                    const selectors = [
                        '[class*="modal"]',
                        '[class*="popup"]',
                        '[class*="overlay"]',
                        '[id*="modal"]',
                        '[id*="popup"]'
                    ];

                    selectors.forEach(sel => {
                        document.querySelectorAll(sel).forEach(el => {
                            if (el.offsetWidth > 200 && el.offsetHeight > 200) {
                                el.remove();
                            }
                        });
                    });

                    // Body-Scroll aktivieren
                    document.body.style.overflow = 'auto';
                    document.documentElement.style.overflow = 'auto';
                }
            """)

    def _quick_remove_overlays(self, page: Page):
        """
        Schnelle Entfernung von Cookie-Bannern und Overlays.
        Wird mehrfach aufgerufen um verzögerte Banner zu erwischen.
        Unterstützt auch Shadow DOM Elemente!
        """
        try:
            # Umfassender JavaScript-basierter Removal inkl. Shadow DOM
            removed = page.evaluate("""
                () => {
                    let removed = 0;

                    // Funktion zum Verstecken eines Elements
                    function hideElement(el) {
                        el.style.setProperty('display', 'none', 'important');
                        el.style.setProperty('visibility', 'hidden', 'important');
                        el.style.setProperty('opacity', '0', 'important');
                        el.style.setProperty('pointer-events', 'none', 'important');
                        el.style.setProperty('position', 'absolute', 'important');
                        el.style.setProperty('top', '-9999px', 'important');
                        el.style.setProperty('left', '-9999px', 'important');
                    }

                    // Cookie-Banner Selektoren
                    const cookieSelectors = [
                        '[class*="cookie"]',
                        '[class*="consent"]',
                        '[class*="gdpr"]',
                        '[class*="privacy"]',
                        '[class*="banner"]',
                        '[class*="notice"]',
                        '[id*="cookie"]',
                        '[id*="consent"]',
                        '[id*="gdpr"]',
                        '[id*="privacy"]',
                        '#CybotCookiebotDialog',
                        '#onetrust-consent-sdk',
                        '.cc-window',
                        '.cky-consent-container',
                        '#usercentrics-root',
                        '.sp-message-container',
                        '#didomi-host',
                        '.fc-consent-root',
                        '[class*="modal"]',
                        '[class*="popup"]',
                        '[class*="overlay"]',
                    ];

                    // 1. Normale DOM-Elemente
                    cookieSelectors.forEach(sel => {
                        try {
                            document.querySelectorAll(sel).forEach(el => {
                                const style = getComputedStyle(el);
                                const rect = el.getBoundingClientRect();
                                if (style.display !== 'none' &&
                                    style.visibility !== 'hidden' &&
                                    rect.width > 100 && rect.height > 50) {
                                    hideElement(el);
                                    removed++;
                                }
                            });
                        } catch(e) {}
                    });

                    // 2. SHADOW DOM SUPPORT - Rekursiv alle Shadow Roots durchsuchen
                    function processNode(node) {
                        // Shadow Root vorhanden?
                        if (node.shadowRoot) {
                            // Alle Elemente im Shadow Root durchsuchen
                            cookieSelectors.forEach(sel => {
                                try {
                                    node.shadowRoot.querySelectorAll(sel).forEach(el => {
                                        const style = getComputedStyle(el);
                                        const rect = el.getBoundingClientRect();
                                        if (rect.width > 100 && rect.height > 50) {
                                            hideElement(el);
                                            removed++;
                                        }
                                    });
                                } catch(e) {}
                            });

                            // Auch nested Shadow Roots
                            node.shadowRoot.querySelectorAll('*').forEach(child => {
                                processNode(child);
                            });
                        }
                    }

                    // Alle Elemente mit Shadow Root finden
                    document.querySelectorAll('*').forEach(el => {
                        processNode(el);
                    });

                    // 3. Shadow Host Elemente komplett verstecken (oft Web Components)
                    const shadowHostSelectors = [
                        '[id*="usercentrics"]',
                        '[id*="cookiebot"]',
                        '[id*="onetrust"]',
                        '[class*="cmp"]',
                        'cmp-root',
                        'usercentrics-cmp',
                        'cookie-consent',
                        'privacy-manager',
                        '[data-nosnippet]',  // Oft für Cookie-Banner verwendet
                    ];

                    shadowHostSelectors.forEach(sel => {
                        try {
                            document.querySelectorAll(sel).forEach(el => {
                                const rect = el.getBoundingClientRect();
                                if (rect.width > 100 && rect.height > 50) {
                                    hideElement(el);
                                    removed++;
                                }
                            });
                        } catch(e) {}
                    });

                    // 4. Fixed/Sticky Elemente die große Bereiche überdecken
                    document.querySelectorAll('*').forEach(el => {
                        try {
                            const style = getComputedStyle(el);
                            const rect = el.getBoundingClientRect();

                            if ((style.position === 'fixed' || style.position === 'sticky') &&
                                rect.width > window.innerWidth * 0.5 &&
                                rect.height > 100) {

                                // Hauptcontent-Elemente ausschließen
                                const tag = el.tagName.toLowerCase();
                                if (!['header', 'nav', 'main', 'article', 'section'].includes(tag)) {
                                    hideElement(el);
                                    removed++;
                                }
                            }
                        } catch(e) {}
                    });

                    // 5. Elemente mit hohem z-index die blockieren
                    document.querySelectorAll('*').forEach(el => {
                        try {
                            const style = getComputedStyle(el);
                            const zIndex = parseInt(style.zIndex);
                            const rect = el.getBoundingClientRect();

                            if (zIndex > 9999 &&
                                rect.width > 200 &&
                                rect.height > 100) {
                                hideElement(el);
                                removed++;
                            }
                        } catch(e) {}
                    });

                    // Body-Scroll aktivieren
                    document.body.style.setProperty('overflow', 'auto', 'important');
                    document.body.style.setProperty('position', 'static', 'important');
                    document.documentElement.style.setProperty('overflow', 'auto', 'important');

                    // Blur-Effekte entfernen
                    document.querySelectorAll('*').forEach(el => {
                        const style = getComputedStyle(el);
                        if (style.backdropFilter !== 'none' || style.filter.includes('blur')) {
                            el.style.setProperty('backdrop-filter', 'none', 'important');
                            el.style.setProperty('filter', 'none', 'important');
                        }
                    });

                    return removed;
                }
            """)

            if removed > 0:
                self.logger.info(f"  Quick-Remove: {removed} Elemente versteckt")

        except Exception as e:
            self.logger.debug(f"Quick-Remove Fehler: {e}")

    def _find_and_center_image(self, page: Page, image_src: str, viewport_height: int) -> Optional[dict]:
        """
        Findet das Bild im sichtbaren Browser anhand der src-URL und gibt Position zurück.

        Returns:
            dict mit y, height, width, x oder None wenn nicht gefunden
        """
        try:
            # Bild per JavaScript suchen (verschiedene Varianten der URL)
            result = page.evaluate("""
                (imageSrc) => {
                    // URL-Varianten generieren (mit/ohne Query-Parameter, relativ/absolut)
                    const searchUrls = [imageSrc];

                    // Ohne Query-String
                    if (imageSrc.includes('?')) {
                        searchUrls.push(imageSrc.split('?')[0]);
                    }

                    // Dateiname extrahieren
                    const filename = imageSrc.split('/').pop().split('?')[0];

                    // Alle Bilder durchsuchen
                    const images = document.querySelectorAll('img');

                    for (const img of images) {
                        const src = img.src || img.dataset.src || img.dataset.lazySrc || '';
                        const srcset = img.srcset || '';

                        // Prüfe ob URL übereinstimmt
                        const matches = searchUrls.some(url =>
                            src.includes(url) ||
                            url.includes(src) ||
                            src.endsWith(filename) ||
                            srcset.includes(filename)
                        );

                        if (matches && img.offsetWidth > 50 && img.offsetHeight > 50) {
                            // Scroll Position berücksichtigen
                            const rect = img.getBoundingClientRect();
                            const scrollY = window.scrollY || window.pageYOffset;

                            return {
                                found: true,
                                x: rect.left,
                                y: rect.top + scrollY,  // Absolute Position
                                width: rect.width,
                                height: rect.height,
                                src: src
                            };
                        }
                    }

                    // Auch in <picture> und <figure> suchen
                    const pictures = document.querySelectorAll('picture source, figure img');
                    for (const el of pictures) {
                        const src = el.srcset || el.src || '';
                        if (src.includes(filename)) {
                            const img = el.tagName === 'SOURCE' ? el.parentElement.querySelector('img') : el;
                            if (img) {
                                const rect = img.getBoundingClientRect();
                                const scrollY = window.scrollY || window.pageYOffset;
                                return {
                                    found: true,
                                    x: rect.left,
                                    y: rect.top + scrollY,
                                    width: rect.width,
                                    height: rect.height,
                                    src: src
                                };
                            }
                        }
                    }

                    return { found: false };
                }
            """, image_src)

            if result and result.get("found"):
                return {
                    "x": result["x"],
                    "y": result["y"],
                    "width": result["width"],
                    "height": result["height"],
                    "src": result.get("src", "")
                }

            return None

        except Exception as e:
            self.logger.debug(f"Bild-Suche fehlgeschlagen: {e}")
            return None

    def _install_banner_blocker(self, page: Page):
        """
        Installiert einen MutationObserver der alle neuen Banner/Overlays
        sofort versteckt. Bleibt aktiv solange die Seite offen ist.
        """
        try:
            page.evaluate("""
                () => {
                    // Bereits installiert?
                    if (window.__bannerBlockerInstalled) return;
                    window.__bannerBlockerInstalled = true;

                    const hideElement = (el) => {
                        el.style.setProperty('display', 'none', 'important');
                        el.style.setProperty('visibility', 'hidden', 'important');
                        el.style.setProperty('opacity', '0', 'important');
                        el.style.setProperty('pointer-events', 'none', 'important');
                        el.style.setProperty('position', 'absolute', 'important');
                        el.style.setProperty('top', '-9999px', 'important');
                    };

                    const bannerPatterns = [
                        'cookie', 'consent', 'gdpr', 'privacy', 'banner',
                        'modal', 'popup', 'overlay', 'notice', 'cmp'
                    ];

                    const isBanner = (el) => {
                        const id = (el.id || '').toLowerCase();
                        const cls = (el.className || '').toLowerCase();
                        const rect = el.getBoundingClientRect();

                        // Zu klein = kein Banner
                        if (rect.width < 100 || rect.height < 50) return false;

                        // Pattern-Check
                        for (const p of bannerPatterns) {
                            if (id.includes(p) || cls.includes(p)) return true;
                        }

                        // Fixed/Sticky mit hohem z-index
                        const style = getComputedStyle(el);
                        const zIndex = parseInt(style.zIndex) || 0;
                        if ((style.position === 'fixed' || style.position === 'sticky') &&
                            zIndex > 1000 &&
                            rect.width > window.innerWidth * 0.5) {
                            return true;
                        }

                        return false;
                    };

                    // Observer für neue Elemente
                    const observer = new MutationObserver((mutations) => {
                        for (const mutation of mutations) {
                            for (const node of mutation.addedNodes) {
                                if (node.nodeType === 1) { // Element node
                                    if (isBanner(node)) {
                                        hideElement(node);
                                    }
                                    // Auch Children prüfen
                                    node.querySelectorAll?.('*').forEach(child => {
                                        if (isBanner(child)) hideElement(child);
                                    });
                                }
                            }
                        }
                    });

                    observer.observe(document.body, {
                        childList: true,
                        subtree: true
                    });

                    // Body-Scroll sicherstellen
                    const styleSheet = document.createElement('style');
                    styleSheet.textContent = `
                        html, body {
                            overflow: auto !important;
                            position: static !important;
                        }
                    `;
                    document.head.appendChild(styleSheet);

                    console.log('[BannerBlocker] Installiert');
                }
            """)
            self.logger.info("✓ Banner-Blocker installiert")
        except Exception as e:
            self.logger.debug(f"Banner-Blocker Fehler: {e}")

    def _maximize_window(self, page: Page):
        """Fenster maximieren (Windows)."""
        try:
            import ctypes
            from ctypes import wintypes

            user32 = ctypes.windll.user32

            # Chrome-Fenster finden
            hwnd = user32.FindWindowW(None, None)

            def callback(hwnd, _):
                length = user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buffer = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buffer, length + 1)
                    if "Chrome" in buffer.value:
                        user32.ShowWindow(hwnd, 3)  # SW_MAXIMIZE
                return True

            WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
            user32.EnumWindows(WNDENUMPROC(callback), 0)

            self.logger.info("✓ Fenster maximiert")
        except Exception as e:
            self.logger.debug(f"Fenster-Maximierung fehlgeschlagen: {e}")

    def _validate_screenshot(self, screenshot_path: Path, reference_image: Path) -> bool:
        """
        Validiert ob das Referenzbild im Screenshot sichtbar ist.

        Verwendet Template-Matching um das Referenzbild im Screenshot zu finden.
        """
        try:
            import cv2
            import numpy as np
            from PIL import Image as PILImage

            # Bilder mit PIL laden (unterstützt WEBP, Unicode-Pfade)
            pil_screenshot = PILImage.open(screenshot_path).convert('RGB')
            pil_reference = PILImage.open(reference_image).convert('RGB')

            # Zu numpy arrays konvertieren
            screenshot = cv2.cvtColor(np.array(pil_screenshot), cv2.COLOR_RGB2BGR)
            reference = cv2.cvtColor(np.array(pil_reference), cv2.COLOR_RGB2BGR)

            if screenshot is None or reference is None:
                self.logger.warning("Konnte Bilder für Validierung nicht laden")
                return False

            # Referenz skalieren falls größer als Screenshot
            ref_h, ref_w = reference.shape[:2]
            scr_h, scr_w = screenshot.shape[:2]

            # Verschiedene Skalierungen testen (breiterer Bereich)
            scales = [0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6, 0.7, 0.8, 0.9, 1.0]
            best_match = 0.0
            best_scale = 0.0

            for scale in scales:
                scaled_w = int(ref_w * scale)
                scaled_h = int(ref_h * scale)

                if scaled_w >= scr_w or scaled_h >= scr_h:
                    continue

                if scaled_w < 30 or scaled_h < 30:
                    continue

                # Referenz skalieren
                scaled_ref = cv2.resize(reference, (scaled_w, scaled_h))

                # Template Matching
                result = cv2.matchTemplate(screenshot, scaled_ref, cv2.TM_CCOEFF_NORMED)
                _, max_val, _, max_loc = cv2.minMaxLoc(result)

                if max_val > best_match:
                    best_match = max_val
                    best_scale = scale

                if max_val >= 0.5:  # 50% Übereinstimmung = Bild vollständig sichtbar
                    self.logger.info(f"  ✓ Bild VOLLSTÄNDIG im Screenshot (Skalierung: {scale:.0%}, Match: {max_val:.1%})")
                    return True

            # Unter 50% = Bild möglicherweise abgeschnitten, weiter scrollen!
            self.logger.warning(f"  Bild nicht vollständig sichtbar (beste Übereinstimmung: {best_match:.1%} bei {best_scale:.0%})")
            return False

        except Exception as e:
            self.logger.warning(f"Validierungsfehler: {e}")
            return True  # Bei Fehler akzeptieren


# ============================================
# Hauptfunktion für direkten Aufruf
# ============================================

def find_image_on_website(
    reference_image: str | Path,
    website_url: str,
    output_path: str | Path,
    max_pages: int = 500,
    skip_search: bool = False,
) -> FinalResult:
    """
    Convenience-Funktion für einfache Nutzung.

    Args:
        reference_image: Pfad zum Referenzbild
        website_url: URL der Website
        output_path: Pfad für Screenshot
        max_pages: Max. Seiten für Suche
        skip_search: Wenn True, überspringe Headless-Suche und gehe direkt zur URL

    Returns:
        FinalResult
    """
    finder = WebsiteImageFinder()
    return finder.find_and_screenshot(
        reference_image=Path(reference_image),
        website_url=website_url,
        output_path=Path(output_path),
        max_pages=max_pages,
        skip_search=skip_search,
    )


if __name__ == "__main__":
    # Test
    result = find_image_on_website(
        reference_image="data/reference_images/pregarten.jpg",
        website_url="https://www.muehlviertel.at/",
        output_path="output/screenshots/test_2phase.png",
        max_pages=100,
    )

    print("\n" + "=" * 60)
    print("ERGEBNIS")
    print("=" * 60)
    print(f"Erfolg: {result.success}")
    if result.search_result:
        print(f"Gefunden auf: {result.search_result.url}")
        print(f"Confidence: {result.search_result.confidence:.1%}")
        print(f"Seiten durchsucht: {result.search_result.pages_searched}")
    if result.screenshot_path:
        print(f"Screenshot: {result.screenshot_path}")
    if result.error:
        print(f"Fehler: {result.error}")
