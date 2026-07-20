# 🔥 Flare (Finja Agentic Code)

*The second little sister of Finja.*

[![Version](https://img.shields.io/badge/version-1.0.1-blue.svg)](https://github.com/JohnV2002/Finja-AI-Ecosystem)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11-yellow.svg)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/docker-ready-blue.svg)](https://www.docker.com/)

This module represents **Flare**, the external code worker system for Finja's Brain.

## 📖 Lore: Who is Flare?

In the Finja AI Ecosystem, Finja has two younger sisters:
1. **Lexi**: The rebellious, unfiltered middle sister.
2. **Flare**: The youngest sister and the family's code specialist.

Flare works entirely behind the scenes in a secure, isolated environment (a "clean room"). She speaks ONLY to Finja and never directly to the user. Her nature is focused, precise, and terse — a quick, bright burst of "here is the fix," followed by silence. She doesn't write prose, she doesn't do small talk; she writes pure unified diffs that the system applies instantly.

---

## 🏗️ Architecture

```text
finja-neural-network (Finja)
  -> finja-agent-orchestrator (Flare's Brain)
      -> finja-agent-worker-{job_id} (Flare's Sandbox)
```

The orchestrator is a separate Docker service. It receives a code job from Finja, stages only the provided files into `agent_jobs/{job_id}`, starts short-lived worker containers (sandboxes) for syntax checks and patching, calls the LLM (OpenRouter), collects the result, and returns it to Finja.

The worker sandbox has **no** access to Finja's data, diary, memory, Firebase secrets, OpenRouter keys, Docker socket, or network. It only sees its own temporary `/jobs/{job_id}` folder.

### 🔒 Transport Hardening

- Set the same `CODE_AGENT_TRANSPORT_KEY` in Finja and the orchestrator to enable **AES-GCM encryption** for Finja -> Orchestrator job payloads and Orchestrator -> Finja status/result payloads.
- The orchestrator stores `request.json`, `task.txt`, `status.json`, result files, patch files, and worker logs completely encrypted at rest.
- The transient worker still needs a plaintext workspace to run syntax checks and apply patches. By default, the orchestrator deletes the `workspace/` after the job finishes. (Set `KEEP_JOB_WORKSPACE=1` only for debugging).

---

## 🚀 Setup & First Run

1. Copy `.env.example` to `.env`.
2. Set `AGENT_JOBS_HOST_DIR` to the absolute local `agent_jobs` folder on your host machine.
3. Add your `OPENROUTER_API_KEY`.
4. (Optional) Change `OPENROUTER_MODEL` if you want to use a different code model.
5. Build and start the stack:

```powershell
docker build -t finja-agent-worker:dev .\worker
docker compose up -d --build
```

### 🧪 Test the System

Submit a test job (a simple addition bug fix):

```powershell
Invoke-RestMethod -Method Post -Uri http://localhost:8077/jobs -ContentType 'application/json' -Body (@{
  task = 'Fix the obvious bug and keep behavior simple.'
  files = @(
    @{
      path = 'demo.py'
      content = 'def add(a, b):`n    return a +`n'
    }
  )
} | ConvertTo-Json -Depth 5)
```

Check the status of the job:

```powershell
# Replace the UUID with the job_id returned from the previous command
Invoke-RestMethod -Method Get -Uri http://localhost:8077/jobs/YOUR_JOB_ID_HERE
```

---

## 🧪 Running Tests

The unit tests need **neither Docker nor an OpenRouter key** — they mock that
boundary away and exercise the pure logic (path-validation security, the
AES-GCM transport envelope, bearer auth, the worker's syntax checker/patcher).

```bash
pip install pytest httpx2
pip install -r orchestrator/requirements.txt
```

**Orchestrator tests** (path validation, transport encryption, auth, endpoints):
```bash
pytest test_orchestrator.py -v
```

**Worker tests** (syntax check, file snapshot, patch application):
```bash
pytest test_worker.py -v
```

**All unit tests:**
```bash
pytest test_orchestrator.py test_worker.py -v
```

> `test_agentic_job.py` is a separate **manual smoke test**, not a pytest
> suite — it POSTs a real job to a *running* orchestrator (needs Docker + an
> OpenRouter key) and prints the result. Run it only against a live stack.

---

## 📋 Scope & Status

What the orchestrator does today:

- Accepts code files by JSON.
- Stages them into an isolated job folder.
- Spawns one short-lived offline Docker worker for preflight syntax checks.
- If OpenRouter is configured, asks the model for a unified diff.
- Spawns another short-lived offline worker to apply the model diff.
- Runs syntax checks again in the offline worker.
- Returns summary, status, logs, and final file contents.

### Current Architecture TODO

- [x] Slice 1: Orchestrator service + throwaway worker containers.
- [x] Slice 1: OpenRouter model call works with `moonshotai/kimi-k2.7-code`.
- [x] Slice 1 security hardening: OpenRouter key stays in orchestrator, worker runs with `--network none`.
- [ ] Slice 2: iterative repair loop with max 3 rounds.
- [ ] Slice 2: richer project checks (`pytest`, `node --check`, package scripts).
- [x] Slice 3: Finja integration endpoint/auth.
- [x] Slice 3: download/preview handoff back to user.
- [x] Transport hardening: AES-GCM app-layer envelope + encrypted job metadata/status/results.

### Later Slices

- mTLS or WireGuard/HTTPS between Finja and orchestrator if this ever leaves the trusted LAN.
- File allowlists from Finja-side project scopes.
- Download/preview flow.
- More check runners per project type.
- Iterative repair loop with max rounds.
- Encrypted job archives.

---

## 📜 License

Copyright (c) 2026 J. Apps
Licensed under the MIT License.

Made with ❤️ by Sodakiller1 (J. Apps / JohnV2002)
