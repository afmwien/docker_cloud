# Playwright Docker Projekt

## Voraussetzungen
- Docker Desktop installiert und gestartet

## Befehle

### Container bauen und starten
```bash
docker-compose up --build
```

### Nur bauen
```bash
docker-compose build
```

### Im Hintergrund starten
```bash
docker-compose up -d
```

### Stoppen
```bash
docker-compose down
```

### Logs anzeigen
```bash
docker-compose logs -f
```

## Entwicklung lokal (ohne Docker)
```bash
pip install -r requirements.txt
playwright install chromium
python main.py
```

## Projektstruktur
```
playright_v1/
├── Dockerfile          # Container-Definition
├── docker-compose.yml  # Container-Orchestrierung
├── requirements.txt    # Python-Abhängigkeiten
├── .dockerignore       # Dateien, die nicht ins Image sollen
├── .gitignore          # Dateien, die nicht ins Git sollen
├── main.py             # Hauptskript
├── data/               # Persistente Daten (Volume)
└── screenshots/        # Screenshots (Volume)
```
