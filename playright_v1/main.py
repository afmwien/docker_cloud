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
        reference_image='data/reference_images/csm_Stefan_Wernhart_7ff580844a.webp',
        website_url='https://www.ehl.at/ueber-ehl/team',
        output_path='output/screenshots/ehl_team.png',
        max_pages=10
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
