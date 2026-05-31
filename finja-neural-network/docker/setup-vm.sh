#!/bin/bash
# ==========================================
# YourAI AI - VM Setup Script
# ==========================================
# Prepares the Docker data folder on the deployment VM.
#
# Main Responsibilities:
# - Create docker/data when it does not exist.
# - Seed missing state JSON files with empty objects.
# - Point the operator at required secrets and copy .dockerignore to the project root.
#
# Side Effects:
# - Creates files under docker/data.
# - Writes docker/data/.env.example when .env is missing.
# - Copies docker/.dockerignore into the project root when available.
#
# Run once on the VM:
#   chmod +x docker/setup-vm.sh
#   ./docker/setup-vm.sh
# ==========================================

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DATA_DIR="$SCRIPT_DIR/data"

echo "========================================="
echo " YourAI AI - VM Setup"
echo "========================================="

# Create the data folder.
echo "[1/3] Creating data folder for secrets and state ..."
mkdir -p "$DATA_DIR"

# Create empty state files when they are missing.
for f in runtime_config.json persona_state.json feedback_data.json users_db.json user_sessions.json tts_volume.json discord_channels.json image_usage.json; do
    if [ ! -f "$DATA_DIR/$f" ]; then
        echo "{}" > "$DATA_DIR/$f"
        echo "  Created: $f"
    else
        echo "  Exists: $f"
    fi
done

# Check secrets.
echo ""
echo "[2/3] Checking secrets ..."
if [ ! -f "$DATA_DIR/access_keys.json" ]; then
    echo "  MISSING: access_keys.json"
    echo "  -> Copy from your PC: scp access_keys.json user@vm:$(pwd)/docker/data/"
else
    echo "  OK: access_keys.json"
fi

if [ ! -f "$DATA_DIR/.env" ]; then
    echo "  MISSING: .env"
    echo "  -> Create it with: nano $DATA_DIR/.env"
    echo "  -> Minimum content:"
    echo "     OPENROUTER_API_KEY=your_openrouter_api_key_here"
    echo "     DISCORD_BOT_TOKEN=..."
    cat > "$DATA_DIR/.env.example" << 'EOF'
# YourAI AI - Environment Variables
# Copy this file to .env and add real keys.

OPENROUTER_API_KEY=your_openrouter_api_key_here
DISCORD_BOT_TOKEN=YOUR_TOKEN_HERE

# Optional:
# TWITCH_TOKEN=...
# SPOTIFY_CLIENT_ID=...
# SPOTIFY_CLIENT_SECRET=...
EOF
    echo "  -> Created example: .env.example"
else
    echo "  OK: .env"
fi

echo ""
echo "[3/3] Copying .dockerignore into the project root ..."
if [ -f "$SCRIPT_DIR/.dockerignore" ]; then
    cp "$SCRIPT_DIR/.dockerignore" "$SCRIPT_DIR/../.dockerignore"
    echo "  Copied: .dockerignore -> project root"
fi

echo ""
echo "========================================="
echo " Setup complete!"
echo ""
echo " Next steps:"
echo "   1. Place secrets in docker/data/"
echo "   2. docker compose -f docker/docker-compose.yml up -d --build"
echo "   3. Dashboard: http://localhost:8051"
echo "========================================="
