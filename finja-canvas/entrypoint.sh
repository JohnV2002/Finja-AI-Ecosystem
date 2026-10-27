#!/bin/sh
# ======================================================================
#          Finja Canvas – Entrypoint
# ======================================================================
#
#   Project: Finja - Twitch Interactivity Suite
#   Module:  finja-canvas
#   Author:  J. Apps (JohnV2002 / Sodakiller1)
#   Version: 1.2.0
#
#   Changes (1.2.0): CANVAS_PAINTER_ENABLED=false serves the canvas only
#                    (no key needed, no Recraft credit used).
#   Changes (1.1.0): Starts the painter with Recraft Vector motifs.
#
# ----------------------------------------------------------------------
#
#   Copyright (c) 2026 J. Apps
#   Licensed under the MIT License
#
# ======================================================================

set -e

case "$(echo "${CANVAS_PAINTER_ENABLED:-true}" | tr '[:upper:]' '[:lower:]')" in
    0|false|no|off)
        echo "🖌️ Painter is off (CANVAS_PAINTER_ENABLED) - serving the canvas only."
        exec python server.py
        ;;
esac

if [ -z "$OPENROUTER_API_KEY" ]; then
    echo "ERROR: OPENROUTER_API_KEY is not set (pass via -e or .env/env_file)."
    exit 1
fi

python server.py &
SERVER_PID=$!

cleanup() {
    kill -TERM "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
    exit 0
}
trap cleanup TERM INT

# Paints one motif after another automatically. painter.py exits with:
#   Exit 0 = this motif finished, still space left    -> start next motif
#   Exit 2 = canvas completely full                   -> final snapshot is already saved,
#                                                        reset canvas and start over
#   Exit 1 = real error (e.g. no API key)             -> stop container
while true; do
    STATUS=0
    python painter.py || STATUS=$?

    if [ $STATUS -eq 2 ]; then
        echo "🖼️ Canvas was completely full (snapshot saved) - resetting and starting anew."
        python reset_canvas.py
    elif [ $STATUS -ne 0 ]; then
        echo "⚠️ painter.py exited with a real error (Exit $STATUS), stopping container."
        cleanup
        exit $STATUS
    else
        python new_motif.py
    fi
done

wait "$SERVER_PID"
