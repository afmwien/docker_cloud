"""
Hauptskript zur Bildsuche auf einer Website.
Nutzt das robuste 2-Phasen-System (Headless-Suche + sichtbarer Screenshot).
"""
import sys
from pathlib import Path

# Füge das src-Verzeichnis zum Python-Pfad hinzu, um lokale Module zu importieren
sys.path.insert(0, str(Path(__file__).parent / 'src'))
from image_finder import find_image_on_website


def main():
    print("Starte 2-Phasen-Bildsuche...")

    result = find_image_on_website(
        reference_image='data/reference_images/facebook_profile.jpg',
        website_url='https://www.facebook.com/profile.php?id=61565079419157',
        output_path='output/screenshots/facebook_profile.png',
        max_pages=10,
        skip_search=True,  # Direkt zur URL, ohne Suche
    )

    print()
    print('=' * 60)
    print('ERGEBNIS')
    print('=' * 60)
    print(f'Erfolg: {result.success}')
    if result.search_result:
        print(f'Gefunden auf: {result.search_result.url}')
        print(f'Confidence: {result.search_result.confidence:.1%}')
    if result.screenshot_path:
        print(f'Screenshot: {result.screenshot_path}')


if __name__ == "__main__":
    main()
