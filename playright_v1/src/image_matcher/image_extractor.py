"""
Image Extractor - Extrahiert alle Bilder von einer Webseite

Sammelt:
- Alle <img> Elemente
- Hintergrundbilder (CSS)
- Bilder aus srcset
- Lazy-loaded Bilder
"""

import re
import hashlib
import logging
from pathlib import Path
from typing import List, Optional, Dict, Set
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse
import requests
from playwright.sync_api import Page
from PIL import Image
import io


@dataclass
class ExtractedImage:
    """Ein extrahiertes Bild."""
    url: str
    local_path: Optional[Path] = None
    element_selector: Optional[str] = None
    element_position: Optional[Dict] = None  # x, y, width, height
    alt_text: str = ""
    width: int = 0
    height: int = 0
    file_size: int = 0
    content_hash: str = ""
    source_type: str = "img"  # img, background, srcset, lazy


@dataclass
class ExtractionResult:
    """Ergebnis der Bild-Extraktion."""
    success: bool
    page_url: str
    images: List[ExtractedImage] = field(default_factory=list)
    total_found: int = 0
    downloaded: int = 0
    failed: int = 0
    error: Optional[str] = None


class ImageExtractor:
    """
    Extrahiert alle Bilder von einer Webseite.

    Verwendung:
        extractor = ImageExtractor(page, download_dir=Path("temp/images"))
        result = extractor.extract_all()

        for img in result.images:
            print(f"{img.url} -> {img.local_path}")
    """

    def __init__(
        self,
        page: Page,
        download_dir: Path = Path("temp/extracted_images"),
        min_width: int = 50,
        min_height: int = 50,
        logger: Optional[logging.Logger] = None
    ):
        self.page = page
        self.download_dir = download_dir
        self.min_width = min_width
        self.min_height = min_height
        self.logger = logger or logging.getLogger("ImageExtractor")

        # Download-Verzeichnis erstellen
        self.download_dir.mkdir(parents=True, exist_ok=True)

        # Bereits verarbeitete URLs (Deduplication)
        self._processed_urls: Set[str] = set()

    def extract_all(self, download: bool = True) -> ExtractionResult:
        """
        Extrahiert alle Bilder von der aktuellen Seite.

        Args:
            download: Bilder herunterladen?

        Returns:
            ExtractionResult
        """
        result = ExtractionResult(
            success=False,
            page_url=self.page.url,
        )

        try:
            images = []

            # 1. Standard <img> Elemente
            img_elements = self._extract_img_elements()
            images.extend(img_elements)

            # 2. Hintergrundbilder
            bg_images = self._extract_background_images()
            images.extend(bg_images)

            # 3. Lazy-loaded Bilder (data-src, data-lazy, etc.)
            lazy_images = self._extract_lazy_images()
            images.extend(lazy_images)

            # Deduplizieren
            unique_images = self._deduplicate(images)

            result.total_found = len(unique_images)
            self.logger.info(f"Gefunden: {result.total_found} Bilder")

            # Download
            if download:
                for img in unique_images:
                    if self._download_image(img):
                        result.downloaded += 1
                    else:
                        result.failed += 1

            result.images = [img for img in unique_images if img.local_path or not download]
            result.success = True

        except Exception as e:
            result.error = str(e)
            self.logger.error(f"Extraktion fehlgeschlagen: {e}")

        return result

    def _extract_img_elements(self) -> List[ExtractedImage]:
        """Extrahiert alle <img> Elemente."""
        images = []

        try:
            # JavaScript ausführen um alle Bilder zu finden
            img_data = self.page.evaluate("""
                () => {
                    const images = [];
                    document.querySelectorAll('img').forEach((img, index) => {
                        const rect = img.getBoundingClientRect();
                        const src = img.currentSrc || img.src;

                        if (src && !src.startsWith('data:')) {
                            images.push({
                                url: src,
                                srcset: img.srcset || '',
                                alt: img.alt || '',
                                width: img.naturalWidth || rect.width,
                                height: img.naturalHeight || rect.height,
                                x: rect.x,
                                y: rect.y,
                                displayWidth: rect.width,
                                displayHeight: rect.height,
                                selector: `img:nth-of-type(${index + 1})`,
                                visible: rect.width > 0 && rect.height > 0
                            });
                        }
                    });
                    return images;
                }
            """)

            for data in img_data:
                # Mindestgröße prüfen
                if data["width"] < self.min_width or data["height"] < self.min_height:
                    continue

                img = ExtractedImage(
                    url=data["url"],
                    element_selector=data["selector"],
                    element_position={
                        "x": data["x"],
                        "y": data["y"],
                        "width": data["displayWidth"],
                        "height": data["displayHeight"],
                    },
                    alt_text=data["alt"],
                    width=int(data["width"]),
                    height=int(data["height"]),
                    source_type="img",
                )
                images.append(img)

        except Exception as e:
            self.logger.warning(f"Fehler bei img-Extraktion: {e}")

        return images

    def _extract_background_images(self) -> List[ExtractedImage]:
        """Extrahiert CSS Hintergrundbilder."""
        images = []

        try:
            bg_data = self.page.evaluate("""
                () => {
                    const images = [];
                    const elements = document.querySelectorAll('*');

                    elements.forEach((el, index) => {
                        const style = getComputedStyle(el);
                        const bgImage = style.backgroundImage;

                        if (bgImage && bgImage !== 'none') {
                            const urlMatch = bgImage.match(/url\\(['"']?(.+?)['"']?\\)/);
                            if (urlMatch && !urlMatch[1].startsWith('data:')) {
                                const rect = el.getBoundingClientRect();
                                if (rect.width > 50 && rect.height > 50) {
                                    images.push({
                                        url: urlMatch[1],
                                        x: rect.x,
                                        y: rect.y,
                                        width: rect.width,
                                        height: rect.height,
                                        selector: el.tagName.toLowerCase()
                                    });
                                }
                            }
                        }
                    });
                    return images;
                }
            """)

            for data in bg_data:
                # URL normalisieren
                url = urljoin(self.page.url, data["url"])

                img = ExtractedImage(
                    url=url,
                    element_position={
                        "x": data["x"],
                        "y": data["y"],
                        "width": data["width"],
                        "height": data["height"],
                    },
                    width=int(data["width"]),
                    height=int(data["height"]),
                    source_type="background",
                )
                images.append(img)

        except Exception as e:
            self.logger.warning(f"Fehler bei Background-Extraktion: {e}")

        return images

    def _extract_lazy_images(self) -> List[ExtractedImage]:
        """Extrahiert Lazy-loaded Bilder."""
        images = []

        try:
            lazy_data = self.page.evaluate("""
                () => {
                    const images = [];
                    const lazyAttrs = ['data-src', 'data-lazy', 'data-original',
                                       'data-lazy-src', 'data-srcset', 'loading'];

                    document.querySelectorAll('img, div, figure').forEach((el, index) => {
                        for (const attr of lazyAttrs) {
                            const value = el.getAttribute(attr);
                            if (value && !value.startsWith('data:') &&
                                (value.includes('.jpg') || value.includes('.png') ||
                                 value.includes('.webp') || value.includes('.jpeg'))) {
                                const rect = el.getBoundingClientRect();
                                images.push({
                                    url: value,
                                    x: rect.x,
                                    y: rect.y,
                                    width: rect.width,
                                    height: rect.height,
                                    attr: attr
                                });
                                break;
                            }
                        }
                    });
                    return images;
                }
            """)

            for data in lazy_data:
                url = urljoin(self.page.url, data["url"])

                # Bereits als normales Bild erfasst?
                if url in self._processed_urls:
                    continue

                img = ExtractedImage(
                    url=url,
                    element_position={
                        "x": data["x"],
                        "y": data["y"],
                        "width": data["width"],
                        "height": data["height"],
                    },
                    source_type="lazy",
                )
                images.append(img)

        except Exception as e:
            self.logger.warning(f"Fehler bei Lazy-Extraktion: {e}")

        return images

    def _deduplicate(self, images: List[ExtractedImage]) -> List[ExtractedImage]:
        """Entfernt doppelte Bilder basierend auf URL."""
        seen_urls = set()
        unique = []

        for img in images:
            # URL normalisieren
            parsed = urlparse(img.url)
            normalized_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

            if normalized_url not in seen_urls:
                seen_urls.add(normalized_url)
                unique.append(img)

        return unique

    def _download_image(self, img: ExtractedImage) -> bool:
        """Lädt ein Bild herunter und speichert es lokal."""
        try:
            # URL validieren
            if not img.url or img.url in self._processed_urls:
                return False

            self._processed_urls.add(img.url)

            # Dateiname aus URL oder Hash
            parsed = urlparse(img.url)
            filename = Path(parsed.path).name

            if not filename or len(filename) > 100:
                filename = hashlib.md5(img.url.encode()).hexdigest()[:16]

            # Extension sicherstellen
            if not any(filename.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.webp', '.gif']):
                filename += '.jpg'

            filepath = self.download_dir / filename

            # Download
            response = requests.get(
                img.url,
                timeout=10,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0",
                    "Accept": "image/*",
                }
            )

            if response.status_code != 200:
                return False

            # Bild validieren
            try:
                pil_img = Image.open(io.BytesIO(response.content))
                img.width = pil_img.width
                img.height = pil_img.height

                # Mindestgröße prüfen
                if img.width < self.min_width or img.height < self.min_height:
                    return False

            except Exception:
                return False

            # Speichern
            with open(filepath, 'wb') as f:
                f.write(response.content)

            # Metadaten aktualisieren
            img.local_path = filepath
            img.file_size = len(response.content)
            img.content_hash = hashlib.md5(response.content).hexdigest()

            return True

        except Exception as e:
            self.logger.debug(f"Download fehlgeschlagen für {img.url}: {e}")
            return False

    def get_image_at_position(self, x: int, y: int) -> Optional[ExtractedImage]:
        """Findet das Bild an einer bestimmten Position."""
        for img in self._processed_urls:
            if img.element_position:
                pos = img.element_position
                if (pos["x"] <= x <= pos["x"] + pos["width"] and
                    pos["y"] <= y <= pos["y"] + pos["height"]):
                    return img
        return None
