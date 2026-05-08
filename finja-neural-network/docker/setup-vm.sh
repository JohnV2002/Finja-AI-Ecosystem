#!/bin/bash
# ==========================================
# YourAI AI - VM Setup Script
# ==========================================
# Einmalig auf der VM ausfuehren:
#   chmod +x docker/setup-vm.sh
#   ./docker/setup-vm.sh
# ==========================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DATA_DIR="$SCRIPT_DIR/data"

echo "========================================="
echo " YourAI AI - VM Setup"
echo "========================================="

# data/ Ordner erstellen
echo "[1/3] Erstelle data/ Ordner fuer Secrets & State ..."
mkdir -p "$DATA_DIR"

# Leere State-Dateien erstellen (falls nicht vorhanden)
for f in runtime_config.json persona_state.json feedback_data.json users_db.json user_sessions.json tts_volume.json discord_channels.json image_usage.json; do
    if [ ! -f "$DATA_DIR/$f" ]; then
        echo "{}" > "$DATA_DIR/$f"
        echo "  Erstellt: $f"
    else
        echo "  Existiert: $f"
    fi
done

# Secrets pruefen
echo ""
echo "[2/3] Pruefe Secrets ..."
if [ ! -f "$DATA_DIR/access_keys.json" ]; then
    echo "  FEHLT: access_keys.json"
    echo "  -> Kopiere von deinem PC: scp access_keys.json user@vm:$(pwd)/docker/data/"
else
    echo "  OK: access_keys.json"
fi

if [ ! -f "$DATA_DIR/.env" ]; then
    echo "  FEHLT: .env"
    echo "  -> Erstelle mit: nano $DATA_DIR/.env"
    echo "  -> Inhalt (mindestens):"
    echo "     OPENROUTER_API_KEY=your_openrouter_api_key_here"
    echo "     DISCORD_BOT_TOKEN=..."
    cat > "$DATA_DIR/.env.example" << 'EOF'
# YourAI AI - Environment Variables
# Kopiere diese Datei zu .env und fuege echte Keys ein!

OPENROUTER_API_KEY=your_openrouter_api_key_here
DISCORD_BOT_TOKEN=DEIN_TOKEN_HIER

# Optional:
# TWITCH_TOKEN=...
# SPOTIFY_CLIENT_ID=...
# SPOTIFY_CLIENT_SECRET=...
EOF
    echo "  -> Beispiel erstellt: .env.example"
else
    echo "  OK: .env"
fi

echo ""
echo "[3/3] .dockerignore ins Root kopieren ..."
if [ -f "$SCRIPT_DIR/.dockerignore" ]; then
    cp "$SCRIPT_DIR/.dockerignore" "$SCRIPT_DIR/../.dockerignore"
    echo "  Kopiert: .dockerignore -> Projekt-Root"
fi

echo ""
echo "========================================="
echo " Setup fertig!"
echo ""
echo " Naechste Schritte:"
echo "   1. Secrets in docker/data/ ablegen"
echo "   2. docker compose -f docker/docker-compose.yml up -d --build"
echo "   3. Dashboard: http://localhost:8051"
echo "========================================="
