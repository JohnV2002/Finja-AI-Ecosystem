#!/usr/bin/env bash
set -euo pipefail

cd /home/john/finja-agentic-code
mkdir -p agent_jobs

touch .env

set_kv() {
    local key="$1"
    local value="$2"
    if grep -q "^${key}=" .env; then
        sed -i "s#^${key}=.*#${key}=${value}#" .env
    else
        printf '%s=%s\n' "$key" "$value" >> .env
    fi
}

set_kv "OPENROUTER_MODEL" "moonshotai/kimi-k2.7-code"
set_kv "AGENT_JOBS_HOST_DIR" "/home/john/finja-agentic-code/agent_jobs"
set_kv "WORKER_IMAGE" "finja-agent-worker:dev"
set_kv "WORKER_NETWORK" "none"
set_kv "MAX_PARALLEL_JOBS" "2"
set_kv "JOB_TIMEOUT_SECONDS" "600"

if grep -q '^OPENROUTER_API_KEY=' /home/john/Finja_brain/docker/data/.env 2>/dev/null; then
    keyline="$(grep '^OPENROUTER_API_KEY=' /home/john/Finja_brain/docker/data/.env | tail -n 1)"
    if grep -q '^OPENROUTER_API_KEY=' .env; then
        sed -i "s#^OPENROUTER_API_KEY=.*#${keyline}#" .env
    else
        printf '%s\n' "$keyline" >> .env
    fi
fi

chmod 600 .env

echo "agent_env_ready"
grep -E '^(OPENROUTER_MODEL|AGENT_JOBS_HOST_DIR|WORKER_IMAGE|WORKER_NETWORK|MAX_PARALLEL_JOBS|JOB_TIMEOUT_SECONDS)=' .env
if grep -q '^OPENROUTER_API_KEY=.' .env; then
    echo "OPENROUTER_API_KEY=SET"
else
    echo "OPENROUTER_API_KEY=MISSING"
fi
