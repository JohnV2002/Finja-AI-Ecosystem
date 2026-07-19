#!/bin/bash
# ======================================================================
#          Finja YouTube Shorts – Entrypoint
# ======================================================================
#
#   Project: Finja - Twitch Interactivity Suite
#   Module:  finja-youtube / entrypoint
#   Author:  J. Apps (JohnV2002 / Sodakiller1)
#   Version: 1.1.0
#
# ----------------------------------------------------------------------
#
#   Copyright (c) 2026 J. Apps
#   Licensed under the MIT License
#
# ----------------------------------------------------------------------
#
#   Startup sequence:
#     1. Wait for VPN tunnel (Gluetun) to establish
#     2. Display current VPN IP
#     3. Start Chrome headless in mobile emulation mode
#     4. Wait until Chrome CDP port is ready
#     5. Start the FastAPI server (youtube_api.py)
#
# ----------------------------------------------------------------------
#   New in v1.1.0:
#     • Adopted into Production (Z:\Bilder\Streaming\Finja - Browser test)
#       as part of the module version/header unification (2026-07-19) --
#       no functional changes in this file specifically
# ======================================================================

set -e

CHROME_PORT="${CHROME_PORT:-9222}"
API_PORT="${YOUTUBE_API_PORT:-8060}"
PROFILE_DIR="/data/chrome-profile"
# Mobile User-Agent (Samsung S22 Ultra)
MOBILE_UA="${MOBILE_UA:-Mozilla/5.0 (Linux; Android 13; SM-S908B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36}"
YOUTUBE_TARGET_URL="${YOUTUBE_TARGET_URL:-https://www.youtube.com/shorts}"

echo "[ENTRYPOINT] Starting Finja YouTube Shorts container..."
echo "[ENTRYPOINT] Chrome Port: $CHROME_PORT | API Port: $API_PORT"

# ---- Wait for VPN tunnel (external IP check) ----
echo "[ENTRYPOINT] Waiting for internet / VPN tunnel..."
VPN_READY=false
for i in $(seq 1 60); do
    if curl -sf "https://api.ipify.org" > /dev/null 2>&1; then
        VPN_READY=true
        break
    fi
    sleep 1
done

if [ "$VPN_READY" = true ]; then
    VPN_IP=$(curl -sf "https://api.ipify.org" 2>/dev/null || echo "???")
    echo "[ENTRYPOINT] VPN active! Public IP: $VPN_IP"
else
    echo "[ENTRYPOINT] WARNING: No internet after 60 seconds!"
    echo "[ENTRYPOINT] Chrome will start anyway — VPN tunnel may not be ready yet."
fi

# ---- Clean up stale Chrome locks (from previous container) ----
rm -f "$PROFILE_DIR/SingletonLock" "$PROFILE_DIR/SingletonSocket" "$PROFILE_DIR/SingletonCookie" 2>/dev/null

# ---- Start Chrome headless ----
echo "[ENTRYPOINT] Starting Chromium headless (mobile mode)..."

chromium \
    --headless=new \
    --no-sandbox \
    --disable-dev-shm-usage \
    --disable-gpu \
    --remote-debugging-port="$CHROME_PORT" \
    --remote-allow-origins=* \
    --no-first-run \
    --no-default-browser-check \
    --user-agent="$MOBILE_UA" \
    --window-size=412,915 \
    --hide-scrollbars \
    --disable-background-networking \
    --disable-sync \
    --disable-translate \
    --disable-extensions \
    --user-data-dir="$PROFILE_DIR" \
    "$YOUTUBE_TARGET_URL" &

CHROME_PID=$!
echo "[ENTRYPOINT] Chrome PID: $CHROME_PID"

# ---- Wait for Chrome CDP to become ready ----
echo "[ENTRYPOINT] Waiting for Chrome CDP (Port $CHROME_PORT)..."
READY=false
for i in $(seq 1 40); do
    if curl -sf "http://127.0.0.1:$CHROME_PORT/json/version" > /dev/null 2>&1; then
        READY=true
        break
    fi
    sleep 0.5
done

if [ "$READY" = true ]; then
    echo "[ENTRYPOINT] Chrome is ready! CDP active."
else
    echo "[ENTRYPOINT] ERROR: Chrome not responding after 20 seconds! FINJA-130"
    kill $CHROME_PID 2>/dev/null || true
    exit 1
fi

# ---- Graceful Shutdown ----
cleanup() {
    echo "[ENTRYPOINT] Shutdown... stopping Chrome and API."
    kill $API_PID 2>/dev/null || true
    kill $CHROME_PID 2>/dev/null || true
    wait $API_PID 2>/dev/null || true
    wait $CHROME_PID 2>/dev/null || true
    echo "[ENTRYPOINT] Bye! :3"
}
trap cleanup SIGTERM SIGINT

# ---- Start FastAPI ----
echo "[ENTRYPOINT] Starting YouTube API on port $API_PORT..."
python youtube_api.py &
API_PID=$!

# ---- Wait (container runs until signal is received) ----
wait $API_PID
cleanup
