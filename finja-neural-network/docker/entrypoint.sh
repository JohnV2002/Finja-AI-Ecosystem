#!/bin/bash
# ==========================================
# YourAI AI - Docker Entrypoint
# ==========================================
# Starts the YourAI dashboard inside the Docker container.
#
# Main Responsibilities:
# - Load environment variables from the mounted docker_data folder.
# - Copy state files into /app so atomic writes with os.replace keep working.
# - Periodically copy changed state files back to docker_data.
#
# Side Effects:
# - Exports environment variables into the dashboard process.
# - Reads and writes state files in /app and /app/docker_data.
# - Starts dashboard_server.py as a background process.
# ==========================================

set -e

DATA_DIR="/app/docker_data"

# State files to synchronize.
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
    "subconscious_state.json"
)

# Load .env when present; preserves commas and spaces in values.
if [ -f "$DATA_DIR/.env" ]; then
    sed -i 's/\r$//' "$DATA_DIR/.env"
    while IFS= read -r line || [ -n "$line" ]; do
        # Skip empty lines and comments.
        [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]] && continue
        # Split and export Key=Value pairs.
        if [[ "$line" =~ ^([A-Za-z_][A-Za-z0-9_]*)=(.*) ]]; then
            key="${BASH_REMATCH[1]}"
            val="${BASH_REMATCH[2]}"
            # Strip optional quotes.
            val="${val%\"}"
            val="${val#\"}"
            val="${val%\'}"
            val="${val#\'}"
            export "$key=$val"
        fi
    done < "$DATA_DIR/.env"
    echo "[ENTRYPOINT] Loaded .env"
fi

# Copy state files into the working directory.
for f in "${STATE_FILES[@]}"; do
    if [ -f "$DATA_DIR/$f" ]; then
        cp "$DATA_DIR/$f" "/app/$f"
        echo "[ENTRYPOINT] Copied: $f"
    fi
done

# Save state back to the mounted data folder.
save_state() {
    echo "[ENTRYPOINT] Saving state back to docker_data/ ..."
    for f in "${STATE_FILES[@]}"; do
        if [ -f "/app/$f" ]; then
            cp "/app/$f" "$DATA_DIR/$f"
            echo "[ENTRYPOINT] Saved: $f"
        fi
    done
    echo "[ENTRYPOINT] State saved. Bye!"
}

# Save state on SIGTERM/SIGINT before the container exits.
trap save_state SIGTERM SIGINT

# Start YourAI.
echo "[ENTRYPOINT] Starting YourAI Dashboard ..."
python dashboard_server.py &
YOURAI_PID=$!

# Save state periodically every five minutes.
while kill -0 $YOURAI_PID 2>/dev/null; do
    sleep 300
    if kill -0 $YOURAI_PID 2>/dev/null; then
        for f in "${STATE_FILES[@]}"; do
            if [ -f "/app/$f" ]; then
                cp "/app/$f" "$DATA_DIR/$f" 2>/dev/null || true
            fi
        done
    fi
done

# Save state even when YourAI crashes.
save_state
wait $YOURAI_PID
