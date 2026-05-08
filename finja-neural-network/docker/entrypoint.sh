#!/bin/bash
# ==========================================
# YourAI AI - Docker Entrypoint
# ==========================================
# Kopiert State-Files aus dem gemounteten data/ Ordner
# in /app, damit atomic writes (os.replace) funktionieren.
# Beim Shutdown werden die Dateien zurueck kopiert.
# ==========================================

set -e

DATA_DIR="/app/docker_data"

# Liste der State-Dateien die synchronisiert werden
STATE_FILES=(
    "access_keys.json"
    "runtime_config.json"
    "persona_state.json"
    "feedback_data.json"
    "users_db.json"
    "user_sessions.json"
    "tts_volume.json"
    "discord_channels.json"
    "image_usage.json"
    "debug_log.jsonl"
    "yourai_output.txt"
    "prompt_router_cache.json"
)

# .env laden (falls vorhanden) - sicher, auch mit Kommas/Spaces in Werten
if [ -f "$DATA_DIR/.env" ]; then
    sed -i 's/\r$//' "$DATA_DIR/.env"
    while IFS= read -r line || [ -n "$line" ]; do
        # Leerzeilen und Kommentare skippen
        [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]] && continue
        # Key=Value splitten und exportieren
        if [[ "$line" =~ ^([A-Za-z_][A-Za-z0-9_]*)=(.*) ]]; then
            key="${BASH_REMATCH[1]}"
            val="${BASH_REMATCH[2]}"
            # Quotes entfernen falls vorhanden
            val="${val%\"}"
            val="${val#\"}"
            val="${val%\'}"
            val="${val#\'}"
            export "$key=$val"
        fi
    done < "$DATA_DIR/.env"
    echo "[ENTRYPOINT] .env geladen"
fi

# State-Dateien ins Arbeitsverzeichnis kopieren
for f in "${STATE_FILES[@]}"; do
    if [ -f "$DATA_DIR/$f" ]; then
        cp "$DATA_DIR/$f" "/app/$f"
        echo "[ENTRYPOINT] Kopiert: $f"
    fi
done

# Funktion: State zurueck sichern
save_state() {
    echo "[ENTRYPOINT] Sichere State zurueck nach docker_data/ ..."
    for f in "${STATE_FILES[@]}"; do
        if [ -f "/app/$f" ] && [ "$f" != "access_keys.json" ]; then
            cp "/app/$f" "$DATA_DIR/$f"
            echo "[ENTRYPOINT] Gesichert: $f"
        fi
    done
    echo "[ENTRYPOINT] State gesichert. Bye!"
}

# Bei SIGTERM/SIGINT State sichern bevor Container stirbt
trap save_state SIGTERM SIGINT

# YourAI starten
echo "[ENTRYPOINT] Starte YourAI Dashboard ..."
python dashboard_server.py &
YOURAI_PID=$!

# Periodisch State sichern (alle 5 Minuten)
while kill -0 $YOURAI_PID 2>/dev/null; do
    sleep 300
    if kill -0 $YOURAI_PID 2>/dev/null; then
        for f in "${STATE_FILES[@]}"; do
            if [ -f "/app/$f" ] && [ "$f" != "access_keys.json" ]; then
                cp "/app/$f" "$DATA_DIR/$f" 2>/dev/null || true
            fi
        done
    fi
done

# Falls YourAI crashed, trotzdem State sichern
save_state
wait $YOURAI_PID
