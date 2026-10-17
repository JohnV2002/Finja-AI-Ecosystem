#!/usr/bin/env bash
# ======================================================================
#          Flare (Finja Agentic Code) – VM Environment Configurator
# ======================================================================
#
#   Project: Finja - Twitch Interactivity Suite
#   Module:  finja-agentic-code
#   Author:  J. Apps (JohnV2002 / Sodakiller1)
#   Version: 1.11.0
#
# ----------------------------------------------------------------------
#
#   Copyright (c) 2026 J. Apps
#   Licensed under the MIT License
#
# ----------------------------------------------------------------------
#
#   Writes/updates the orchestrator's .env on the host VM (idempotent
#   key=value upsert). Optionally imports OPENROUTER_API_KEY from the
#   path provided through FINJA_ENV_FILE or private/finja.env.
#
# ======================================================================

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
mkdir -p agent_jobs private

touch .env

set_kv() {
    local key="$1"
    local value="$2"
    local line
    local found=0
    local temp_file
    temp_file="$(mktemp "$SCRIPT_DIR/private/.flare-env.XXXXXX")"
    while IFS= read -r line || [[ -n "$line" ]]; do
        if [[ "$line" == "$key="* ]]; then
            if (( found == 0 )); then
                printf '%s=%s\n' "$key" "$value" >> "$temp_file"
                found=1
            fi
        else
            printf '%s\n' "$line" >> "$temp_file"
        fi
    done < .env
    if (( found == 0 )); then
        printf '%s=%s\n' "$key" "$value" >> "$temp_file"
    fi
    chmod 600 "$temp_file"
    mv -f -- "$temp_file" .env
}

set_kv "OPENROUTER_MODEL" "moonshotai/kimi-k2.7-code"
set_kv "AGENT_JOBS_HOST_DIR" "$SCRIPT_DIR/agent_jobs"
set_kv "WORKER_IMAGE" "finja-agent-worker:dev"
set_kv "WORKER_NETWORK" "none"
set_kv "MAX_PARALLEL_JOBS" "2"
set_kv "JOB_TIMEOUT_SECONDS" "600"
set_kv "JOB_TOTAL_TIMEOUT_SECONDS" "900"
set_kv "OPENROUTER_TIMEOUT_SECONDS" "90"
set_kv "OPENROUTER_MAX_ATTEMPTS" "3"
set_kv "RETRY_BASE_DELAY_SECONDS" "1"

source_env="${FINJA_ENV_FILE:-$SCRIPT_DIR/private/finja.env}"
if [[ -f "$source_env" ]] && grep -q '^OPENROUTER_API_KEY=' "$source_env"; then
    keyline="$(grep '^OPENROUTER_API_KEY=' "$source_env" | tail -n 1)"
    set_kv "OPENROUTER_API_KEY" "${keyline#OPENROUTER_API_KEY=}"
fi

chmod 600 .env

echo "agent_env_ready"
grep -E '^(OPENROUTER_MODEL|WORKER_IMAGE|WORKER_NETWORK|MAX_PARALLEL_JOBS|JOB_TIMEOUT_SECONDS|JOB_TOTAL_TIMEOUT_SECONDS|OPENROUTER_TIMEOUT_SECONDS|OPENROUTER_MAX_ATTEMPTS|RETRY_BASE_DELAY_SECONDS)=' .env
echo "AGENT_JOBS_HOST_DIR=SET"
if grep -q '^OPENROUTER_API_KEY=.' .env; then
    echo "OPENROUTER_API_KEY=SET"
else
    echo "OPENROUTER_API_KEY=MISSING"
fi
