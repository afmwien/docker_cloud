#!/bin/bash
# ============================================================
# Startup-Script für Xvfb-Desktop-Container
# Startet alle Dienste über supervisord
# ============================================================

set -e

export DISPLAY=:99
export SCREEN_WIDTH=${SCREEN_WIDTH:-1920}
export SCREEN_HEIGHT=${SCREEN_HEIGHT:-1080}
export SCREEN_DEPTH=${SCREEN_DEPTH:-24}

echo "=== Desktop-Container startet ==="
echo "Display: $DISPLAY"
echo "Auflösung: ${SCREEN_WIDTH}x${SCREEN_HEIGHT}x${SCREEN_DEPTH}"

# Output-Verzeichnis sicherstellen
mkdir -p /app/output/screenshots
mkdir -p /var/log

# Supervisord starten (managed alle Prozesse)
exec /usr/bin/supervisord -c /etc/supervisor/conf.d/app.conf
