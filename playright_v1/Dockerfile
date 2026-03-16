# Offizielles Playwright-Image mit vorinstallierten Browsern
FROM mcr.microsoft.com/playwright/python:v1.42.0-jammy

# Arbeitsverzeichnis im Container
WORKDIR /app

# Zuerst nur requirements kopieren (besseres Caching)
COPY requirements.txt .

# Abhängigkeiten installieren
RUN pip install --no-cache-dir -r requirements.txt

# Restlichen Code kopieren
COPY . .

# Standard-Befehl beim Container-Start
CMD ["python", "main.py"]
