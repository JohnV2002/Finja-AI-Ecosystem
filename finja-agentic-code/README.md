# 🔥 Flare (Finja Agentic Code) — v1.11.0

*The second little sister of Finja.*

[![Version](https://img.shields.io/badge/version-1.11.0-blue.svg)](https://github.com/JohnV2002/Finja-AI-Ecosystem)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](../LICENSE)
[![Python](https://img.shields.io/badge/python-3.14-yellow.svg)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/docker-ready-blue.svg)](https://www.docker.com/)

This module represents **Flare**, the external code worker system for Finja's Brain.

## 📖 Lore: Who is Flare?

In the Finja AI Ecosystem, Finja has two younger sisters:
1. **Lexi**: The rebellious, unfiltered middle sister.
2. **Flare**: The youngest sister and the family's code specialist.

Flare works entirely behind the scenes in a secure, isolated environment (a "clean room"). She speaks ONLY to Finja and never directly to the user. Her nature is focused, precise, and terse — a quick, bright burst of "here is the fix," followed by silence. For contained fixes she writes pure unified diffs that are tested first and applied only after approval. Multi-file or architectural work is handed to a human instead.

---

## 🏗️ Architecture

```text
finja-neural-network (Finja)
  -> finja-agent-orchestrator (Flare's Brain)
      -> finja-agent-worker-{job_id} (Flare's Sandbox)
```

The orchestrator is a separate Docker service. It receives a code job from Finja, stages only the provided files into `agent_jobs/{job_id}`, starts short-lived worker containers (sandboxes) for syntax checks and patching, calls the LLM (OpenRouter), collects the result, and returns it to Finja.

Compose binds the API to `127.0.0.1` by default. Keep the job API private and
set `ORCHESTRATOR_AUTH_TOKEN` before any deliberate non-loopback exposure via
`FLARE_BIND_HOST`; the orchestrator has access to the Docker socket. The
testbed likewise binds only to loopback and runs with no worker network.

The intended Finja integration is error-driven: Finja turns a caught error into
a scoped task and sends the error context plus only the affected source files.
Flare then follows the guarded lifecycle below and returns a tested candidate;
it never receives Finja's complete private data tree.

Every request carries a safe logical `repository` identifier such as
`finja-neural-network`—never an absolute filesystem path. Omitting it uses the
conservative `default` scope. Invalid identifiers return `FLARE-605`.

The worker sandbox has **no** access to Finja's data, diary, memory, Firebase secrets, OpenRouter keys, Docker socket, or network. It only sees its own temporary `/jobs/{job_id}` folder.

### 🔒 Transport Hardening

- Set the same `CODE_AGENT_TRANSPORT_KEY` in Finja and the orchestrator to enable **AES-GCM encryption** for Finja -> Orchestrator job payloads and Orchestrator -> Finja status/result payloads.
- The orchestrator stores `request.json`, `task.txt`, `status.json`, result files, patch files, and worker logs completely encrypted at rest.
- The transient worker still needs a plaintext workspace to run syntax checks and apply patches. By default, the orchestrator deletes the `workspace/` after the job finishes. (Set `KEEP_JOB_WORKSPACE=1` only for debugging).

Job state is durable across orchestrator restarts. Executing jobs resume in
their current forward-only state, while `awaiting_approval` jobs remain parked
until Finja explicitly approves or rejects them. Terminal states remain
queryable until explicitly deleted. Transient OpenRouter failures use bounded
exponential retries, while per-request, worker-phase, and total-job timeouts
prevent stuck work.

Submissions support an optional `Idempotency-Key` header. Repeating the same key
and request returns the original durable job; reusing a key for different input
returns `FLARE-601`. Without a key, identical active jobs and recently completed
jobs are deduplicated for `DEDUPE_WINDOW_SECONDS` (default: five minutes).
Preflight, model-patch, test-patch, apply-patch, and verification checkpoints
support process/VM restart recovery. At most `MAX_ACTIVE_JOBS` quests (default:
five) may be non-terminal at once, including quests awaiting approval.

### Public job-status contract

Finja may display these states directly to the user. Each status response also
contains a stable English `status_message`, a monotone `revision`,
`previous_status`, `status_changed_at`, and a bounded `status_history`.

| Current state | Allowed next states |
|---|---|
| `queued` | `analysing`, `failed`, `rolled_back` |
| `analysing` | `patching`, `failed`, `rolled_back` |
| `patching` | `testing`, `failed`, `rolled_back` |
| `testing` | `awaiting_approval`, `failed`, `rolled_back` |
| `awaiting_approval` | `applying`, `failed`, `rolled_back` |
| `applying` | `verifying`, `failed`, `rolled_back` |
| `verifying` | `completed`, `failed`, `rolled_back` |
| `completed` | terminal |
| `failed` | terminal |
| `rolled_back` | terminal |

There is no public `cancel_requested` state: cancellation is durable metadata
and finishes as `rolled_back`. Approval includes the observed status `revision`,
so stale UI actions cannot apply a different candidate. Invalid transitions or
stale approvals return `FLARE-602`; a full questboard returns `FLARE-603`;
corrupt persisted state returns `FLARE-801` instead of an unstructured 500.

### Runtime observability

While Flare is actively analysing, patching, testing, applying, or verifying,
the orchestrator persists a heartbeat every `HEARTBEAT_INTERVAL_SECONDS`
(default: five seconds). Each job exposes `heartbeat_at`,
`heartbeat_sequence`, `progress_percent`, `latest_report`, and a bounded
`progress_reports` stream. Finja can read the complete job status or use
`GET /jobs/{job_id}/reports` for a compact progress response suitable for the
user-facing UI.

Worker phases remain capped by `JOB_TIMEOUT_SECONDS`; model calls have their
own `OPENROUTER_TIMEOUT_SECONDS`; each pre-approval or approved execution run is
capped by `JOB_TOTAL_TIMEOUT_SECONDS`. Persisted `phase_deadline_at` and
`total_deadline_at` timestamps make those limits visible. The approval wait is
deliberately not timed as active execution and emits no fake heartbeat. `/health`
reports active quests and stale executing jobs using
`HEARTBEAT_STALE_SECONDS`.

Every execution timeout is fail-soft for Finja. Flare first releases its worker
slot and all repository/file locks, restores the submitted source snapshot, and
then enters the existing terminal state `rolled_back` with `FLARE-500`. The
response identifies `outcome: timeout_soft`, includes a user-safe explanation,
and exposes `retryable`, `retry_after_seconds`, and `retry_endpoint`. Finja can
call `POST /jobs/{job_id}/retry` after the suggested delay; repeated calls reuse
the same new attempt instead of creating duplicate jobs. Non-timeout failures
remain distinguishable and cannot use this retry endpoint.

### Concurrency and resource locks

Concurrency has three independent guards:

- `MAX_ACTIVE_JOBS` caps the durable questboard (default: five quests).
- `MAX_PARALLEL_JOBS` caps total active execution (default: two runs).
- `MAX_PARALLEL_JOBS_PER_REPOSITORY` caps one logical repository (default: one run).

Before active execution, Flare acquires a repository slot and an exclusive lock
for every submitted file. Different repositories can run in parallel; files in
the same repository cannot overlap even when the per-repository limit is raised.
The locks use cross-process OS advisory leases, so a dead process or VM restart
cannot leave a permanent lock behind. Persistent lock filenames contain only
SHA-256 hashes, not repository names or source paths.

Locks cover analysis through candidate testing, are released before
`awaiting_approval`, and are acquired again for apply plus verification. Lock
waits emit heartbeats/intermediate reports and remain inside the total runtime
limit. Lock-layer failures use the structured code `FLARE-604`; `/health`
reports the number of currently held resource locks.

---

## 🚀 Setup & First Run

1. Copy `.env.example` to `.env` and replace every placeholder.
2. Set `AGENT_JOBS_HOST_DIR` to the absolute local `agent_jobs` folder on your host machine.
3. Add your `OPENROUTER_API_KEY`.
4. (Optional) Change `OPENROUTER_MODEL` if you want to use a different code model.
5. (Optional) Tune retry and timeout values in `.env`.
6. (Optional) Tune `MAX_REPAIR_FILES` / `MAX_REPAIR_LINES` — the L2 repair scope.
6. Build and start the stack:

```powershell
docker build -t finja-agent-worker:dev .\worker
docker compose up -d --build
```

### 🧪 Test the System

Submit a test job (a simple addition bug fix):

```powershell
Invoke-RestMethod -Method Post -Uri http://localhost:8077/jobs -ContentType 'application/json' -Body (@{
  task = 'Fix the obvious bug and keep behavior simple.'
  repository = 'finja-neural-network'
  files = @(
    @{
      path = 'demo.py'
      content = 'def add(a, b):`n    return a +`n'
    }
  )
} | ConvertTo-Json -Depth 5)
```

For retry-safe submission, add a stable key generated by Finja for that logical
request:

```powershell
Invoke-RestMethod -Method Post -Uri http://localhost:8077/jobs `
  -Headers @{ 'Idempotency-Key' = 'finja-request-123' } `
  -ContentType 'application/json' `
  -Body $jobJson
```

Check the status of the job:

```powershell
# Replace the UUID with the job_id returned from the previous command
Invoke-RestMethod -Method Get -Uri http://localhost:8077/jobs/YOUR_JOB_ID_HERE
```

Read only the heartbeat and intermediate-report stream:

```powershell
Invoke-RestMethod -Method Get -Uri http://localhost:8077/jobs/YOUR_JOB_ID_HERE/reports
```

Approve or reject the exact tested revision returned with `awaiting_approval`:

```powershell
$decision = @{ revision = 5 } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://localhost:8077/jobs/YOUR_JOB_ID_HERE/approve -ContentType 'application/json' -Body $decision
# Or use /reject with the same body.
```

Cancel any non-terminal job (safe to repeat):

```powershell
Invoke-RestMethod -Method Post -Uri http://localhost:8077/jobs/YOUR_JOB_ID_HERE/cancel
```

Deletion is intentionally separate from cancellation. `DELETE /jobs/{job_id}`
accepts only terminal jobs (`completed`, `failed`, or `rolled_back`).

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

**Test track unit tests** (fault-plan parsing, guard reactions, catalog sanity):
```bash
pytest test_testbed.py -v
```

**All unit tests:**
```bash
pytest test_orchestrator.py test_worker.py test_testbed.py test_l1_diagnosis.py test_repair_scope.py test_manual_scope.py test_incident_envelope.py test_privacy_gate.py test_incident_routing.py test_rate_limit.py test_source_manifest.py test_changeset.py test_supervisor.py test_exec_guard.py -v
```

> `test_agentic_job.py` is a separate **manual smoke test**, not a pytest
> suite — it POSTs a real job to a *running* orchestrator (needs Docker + an
> OpenRouter key) and prints the result. Run it only against a live stack.

---

## 🔎 L1 Diagnosis (Phase B)

L1 is Flare's first look at a job: the `analysing` phase, running inside the
offline worker sandbox. Three rules define it, and each one is a reliability
property rather than a feature:

1. **It never executes the submitted code.** No `pytest`, no `node`, no
   importing a workspace module. Running a stranger's code is a different
   risk class and belongs to a higher capability level.
2. **It is deterministic.** Same workspace in, byte-identical diagnosis out.
   Files are walked in sorted order; findings are sorted by path, line,
   column and check.
3. **It is honest about its own blind spots.** A file nothing can check is
   listed in `undiagnosed`; a check that could not run is listed in
   `checks_skipped`. **Silence never means "clean"** — a planner has to be
   able to tell *checked and clean* from *never looked*.

Findings carry a `check` id such as `python.syntax`, deliberately **not** a
`FLARE-xxx` code: that namespace belongs to the exceptions Finja shows a
user, and filling it with lint rules would make the public error contract
meaningless.

### What L1 checks

| Check | Covers | Severity |
|---|---|---|
| `text.encoding` | any text file: NUL bytes, invalid UTF-8 | error |
| `python.syntax` | `.py` via `ast.parse` | error |
| `python.relative_import` | relative imports that resolve nowhere in the payload | warning |
| `json.parse` | `.json` | error |
| `toml.parse` | `.toml` via `tomllib` | error |
| `yaml.parse` | `.yml` / `.yaml`, when the image carries PyYAML | error |

Only **relative** imports are checked, and that restriction is the point:
offline, a missing third-party package cannot be told apart from an
uninstalled one, so flagging `import requests` would be a false alarm. A
relative import must resolve inside the payload — if it does not, the code
is broken whatever the environment looks like.

Declared blind spots: `.js` / `.ts` / `.tsx` / `.jsx` need a real parser and
the sandbox has no `node`; `.md` / `.txt` / `.css` / `.html` get no
trustworthy static verdict. Both land in `undiagnosed` with a reason.

### The contract

The worker result gains `l1_diagnosis` (and `postflight_l1_diagnosis` after
patching): `schema_version`, `executes_code`, `deterministic`,
`checks_run`, `checks_skipped`, `files_seen`, `files_diagnosed`,
`undiagnosed`, `findings`, `counts` and a `verdict` of `clean` or
`blocked`. A `python.syntax` finding is flagged `truncated`, because
`ast.parse` stops at the first error and a clean-looking remainder is not
evidence of anything.

The orchestrator renders this for the model instead of dumping raw worker
JSON into the prompt, blind spots included. Results staged before L1
existed carry no diagnosis and fall back to the previous rendering.

The long-standing python-syntax gate still exists and is unchanged, but it
is now a *view* onto the L1 diagnosis rather than a second parser, so the
gate and the diagnosis cannot disagree about a file.

> **L1 informs; it does not yet block.** A `blocked` verdict from a broken
> `.json` does not stop a job today — only the python-syntax gate does.
> Letting the L1 verdict gate the lifecycle would reject payloads that
> currently pass, so it is a deliberate policy change rather than part of
> making the diagnosis reliable. The test track pins both halves
> (`l1_sees_broken_json_without_blocking`), so changing it later is visible
> instead of silent.

---

## 🪡 L2 Repair Scope (Phase B)

L2 is Flare's hands: it drafts a repair diff and stops there.

**The stopping was already true.** A candidate is only ever applied inside a
disposable worker during `testing`, on a restored copy of the payload; the
locks are released before `awaiting_approval`, and the real apply waits for
a revision-bound approval. Nothing Finja owns is touched on the way.

What was missing is the other half of the promise. *"Keep changes minimal"*
lived only as a sentence in the model prompt, with nothing measuring it — a
five-hundred-line rewrite across every file would have sailed through to the
sandbox and on to a reviewer. `core/repair_scope.py` turns that sentence
into a reviewed bound, **between the model call and the test phase**, so an
over-reaching candidate is refused before any worker applies it.

Three levels of strictness, on purpose:

| Aspect | Strictness | Why |
|---|---|---|
| Paths | **hard** | GNU patch happens to refuse `..` and absolute targets today, but that is a property of the binary, not a promise Flare makes. Flare makes it here. |
| Size | **policy** | `MAX_REPAIR_FILES` (5) and `MAX_REPAIR_LINES` (200) encode what "minimal" means for a deployment, not a law of nature — so both are env-tunable. |
| Evidence | **reported** | A legitimate fix may touch a file L1 had no finding for. Pointing that out helps a reviewer; refusing it would block honest repairs. |

### What gets refused

| Violation | Code |
|---|---|
| no unified-diff headers in the model output (prose instead of a diff) | `FLARE-606` |
| target is not a safe relative path (`..`, absolute, dotfile, backslash) | `FLARE-606` |
| modifies a file that was never in the payload | `FLARE-606` |
| git-style `a/` + `b/` prefixes, which cannot apply under `patch -p0` | `FLARE-606` |
| touches more files or changes more lines than the repair scope allows | `FLARE-607` |

The `a/` + `b/` case gets its own violation deliberately: it used to surface
as an unexplained `FLARE-501` from the sandbox ("patch could not be applied
cleanly"), which told nobody that the model had simply used the wrong path
convention.

### The report

The review produces a `repair_scope` section in the job result (and
`repair_scope.json` in the job folder): per-file `kind`, `added`, `removed`,
`hunks`, the `limits` in force, any `violations`, which L1 findings the
hunks actually sit on top of (`findings_addressed`), which touched files had
no finding at all (`files_without_evidence`), and `applied: false`.

Creating a *new* file inside the payload is syntactically allowed and
reported by L2; L5 routes file creation/deletion to manual review before any
repair sandbox. Deleting and modifying are bounded to files the payload
contained.

> A refused candidate ends the job as `failed`. Retrying with a tighter
> instruction is the open *iterative repair loop* item, not part of making
> the diff bounded.

---

## 🧪 L3 Sandbox Repair (Phase B)

L3 applies an L2-approved diff only inside a disposable worker copy during
`testing`. If the submitted payload includes Python `test_*.py` files, the
worker runs standard-library `unittest discover` offline with a fixed locale,
timezone and hash seed, a 30-second test limit, and no third-party package
installation. A failing, hanging, zero-discovered-test, or workspace-mutating
suite blocks approval. With no test files, the report says `not_run`; syntax
checking still runs, but Flare does **not** claim that tests passed.

The worker sees only a per-phase `sandbox/` with its source copy and patch,
not the job's request, status or approval files. Docker runs it without
network, capabilities or writable root filesystem, and with CPU, memory,
process and runtime limits. The sandbox is deleted after each execution run.

Before approval, the job result contains `test_evidence`: runner and Python
version, worker-runner SHA-256, exact command, input SHA-256, discovered test files and count,
pass/fail/timeout status, and a log digest. The bounded detailed log stays as
`test_patch_tests.log` in the job folder rather than in the user-facing
status. After revision-bound approval, Flare reapplies the same patch from
the original submitted files and runs verification again. A different input
hash, worker runner, Python version, test count or outcome rolls the job back
instead of completing it.

This makes Flare's **procedure and candidate identity reproducible**; it
cannot make arbitrary user-written tests deterministic. Python tests needing
`pytest` or dependencies, JavaScript checks and package scripts remain future
runner work. They are not silently counted as passing L3 tests.

---

## 🔐 L4 Approval-gated Hotfix (Phase B)

Submit `"mode": "hotfix"` with a normal `/jobs` request to opt into L4;
omitting it keeps the L3-compatible `standard` behavior. Hotfix mode requires
a non-empty repair diff and at least one real Python `unittest` test. The same
candidate must pass in **three fresh, isolated sandbox runs** by default.
`L4_REQUIRED_GREEN_RUNS` can set the requirement from 2 to 7; the value is
captured when the job is created, so a restart or config change cannot lower
an existing job's gate.

Each run restores the original input and uses a new worker sandbox. Per-run
checkpoints and logs survive process restarts. The approval packet binds the
patch SHA-256 to each green run's test evidence, including the candidate and
runner identities. Missing tests, a changed candidate, a failed run, or
incomplete evidence block the hotfix with `FLARE-608` (or the existing worker
failure/timeout code). The `/approve` endpoint rechecks the packet against
the persisted patch and latest test checkpoint before entering `applying`.
After approval, L3's independent verification still runs; a mismatch rolls
back. The approval is **human-triggered**, not automatic promotion to a live
repository or production.

---

## 🧭 L5 Multi-File / Architecture: Human-led (Phase B)

Submit `"mode": "manual"` for known architectural work. Flare then records
`manual_review` and stops **before the model or any worker runs**. Obvious
architecture intent in the task or submitted schema, migration, interface,
API, and configuration paths also routes there conservatively.

If a contained request produces a diff that changes **more than one file**,
creates/deletes a file, or touches an architectural path, Flare records the
candidate and a reasoned `manual_review.json` **before L3's repair sandbox**.
No L4 repeat run, automatic composition, or approval/apply follows. The
candidate may already have been generated and L1 preflight may have run;
neither is an applied repair.

Because #59 has no `manual_review` state, these jobs end as `failed` with
`outcome: "manual_required"` and stable code `FLARE-609`. Finja can show this
as a handoff, not as a crash. The report names the stage, affected paths and
policy reasons. `/approve` cannot advance a terminal manual job. A human
must design and integrate the change outside this automatic pipeline.
The authenticated `GET /jobs/{job_id}/manual` returns the report and, when
one exists, the **unapplied** candidate diff for review; the report includes
its SHA-256 so a changed artifact is not silently served.

Path and wording signals cannot prove that a one-file change is semantically
non-architectural. Callers must select `mode: "manual"` when they know it
changes contracts or design despite a small diff. L2's five-file size limit
remains a validity ceiling, **not** permission to automate a multi-file patch.

---

## 🔒 Redacted Incident Envelope (Phase C, #69)

Finja-to-Flare incidents have a separate, versioned **data contract** in
[`contracts/INCIDENT_ENVELOPE.md`](contracts/INCIDENT_ENVELOPE.md), backed by
`core/incident_envelope.py`. It carries only a redacted summary, structured
relative stack frames, and a small source bundle with SHA-256 digests. There
is no raw-log, user-message, env-value or absolute-host-path field. Flare's
validator fails closed with `FLARE-610` for invalid shapes/versions and
`FLARE-611` for obvious sensitive data, without echoing the input.

This is **not** the existing AES-GCM transport envelope, and #69 does not yet
add a Finja emitter or a `POST /incidents` job intake. The generic `/jobs`
endpoint remains for existing scoped jobs; it must not be mistaken for the
privacy-checked incident handshake. Since #70 it does, however, refuse
secrets and private data at the door -- see the next section.

---

## 🚫 Hard Input Exclusion (Phase C, #70)

The README has always promised that Flare never receives Finja's diary,
memory, Firebase secrets or OpenRouter keys. That was a promise about the
**sender**. `core/privacy_gate.py` makes it a property of the **receiver**:
a submission that holds such material is refused with `FLARE-612` before it
is fingerprinted, deduplicated, staged, stored, logged, or put into a model
prompt. It runs on the decrypted body, so AES-GCM transport does not hide a
secret from it, and a refused submission leaves **nothing on disk**.

Before the gate, `POST /jobs` accepted `secrets.json`, `tokens.json`,
`prod.env.txt`, `diary/…`, `memory/…`, `id_rsa.txt` and sources containing
API keys, private-key blocks or bearer tokens. The only refusal was
`config/.env`, and only by accident: a file with no suffix trips the
file-type rule.

### What is refused

| By | Rule | Examples |
|---|---|---|
| **name**, any file type | environment files | `.env`, `config/.env.local`, `prod.env.txt`, `.envrc` |
| **name**, any file type | key material | `id_rsa`, `*.pem`, `*.key`, `.npmrc`, `.netrc` |
| **name**, any file type | secret directories | `private/`, `secrets/`, `credentials/`, `logs/`, `backups/`, `.ssh/` |
| **name**, data files only | personal-data directories | `diary/`, `memory/`, `conversations/`, `chat_history/`, `user_prompts/` |
| **name**, data files only | secret-like file names | `tokens.json`, `secrets.yml`, `spotify_token.json`, `firebase-adminsdk-*.json` |
| **content** | unambiguous formats | private-key blocks, `sk-…`, `ghp_…`, `AKIA…`, Slack and Discord bot tokens, Twitch `oauth:…`, credentials inside a URL |
| **content** | secret-looking assignments | `API_KEY = "…"`, `"client_secret": "…"`, `Authorization: Bearer …`, `?token=…`, `.env`-style lines in `.txt`/`.md`/`.yml` |

"Data files only" is deliberate. `memory/store.py` is the code of a memory
package, `tokens.py` is a lexer, `secrets.py` imports the standard library,
and `tokenizer.json` is a vocabulary. For source files the **content**
decides, not the name; a `memory/user_42.json` is somebody's stored
conversation and is refused whatever it holds. The task text is scanned with
the same content rules, since it goes into the model prompt like the files do.

### How a refusal looks

`HTTP 422` with `FLARE-612` (a policy refusal, distinct from the `400` a
malformed payload gets). The message names the file, the line and the
**kind** of problem -- things the sender already knows -- and never the
matched text, so the response is safe to store and to show:

```text
Submission refused before staging; it holds secrets or private data:
demo.py:3 (credential), tokens.json (secret_filename). Remove them and resubmit.
```

A path that is structurally unsafe (`../etc/passwd`, absolute, backslashes)
stays an ordinary `400` from the path validation, so an attempted escape is
not relabelled as a secrets problem. Its content is still scanned.

### What is deliberately not refused

A gate that refuses normal code cannot be used by an automated sender that
cannot reword a comment. Heuristic matches are therefore skipped when the
value is plainly not a machine secret: placeholders (`<your-key>`, `${VAR}`,
`abc123...`), values containing a fixture word as a whole word (`test`,
`fake`, `mock`, `example`, German `dein`/`beispiel`), values shorter than 8
characters, word-like identifiers (`valid_access_token`, `MOCK_TOKEN_2`),
URLs, file paths, plain numbers in YAML, and the read-only `?token=` that
badge services such as codecov.io print into README images on purpose.
The unambiguous formats get **no** such exemption: a real key does not stop
being one because the file around it is a test.

This tuning lives in the gate only. The shared credential patterns are also
used by the incident envelope, which keeps its stricter extras (any
bearer-looking token, absolute paths, private IPs, e-mail addresses, long
numeric ids, tracebacks), because an envelope is already redacted by its
sender.

Measured against this repository's own tracked files (482 code and text
files), the gate raises no content false positives; it refuses the 16
`Memory/*` data files, which is its job.

### Known limits

Stated rather than hidden:

- **Defence in depth against an accident, not a filter against an
  adversary.** A value that is obfuscated, split or renamed passes. The
  sender must still strip sensitive material before it submits.
- **Free-text user prompts and diary prose cannot be recognised by
  pattern.** Only their *location* (`diary/`, `memory/`, …) and
  credential-shaped content can be refused. A chat message pasted into a
  comment looks like a comment.
- **A short or word-like password a person chose passes**
  (`password = "hunter2"`). The gate targets machine credentials, which are
  long and random.
- Detection is regex-based; there is no entropy scoring.

---

## 🧭 Incident Routing (Phase C, #71)

A validated incident says *what* failed. `core/incident_routing.py` decides
what Flare does about it, and the answer is rarely "generate a fix". The
point is easiest to see with `FINJA-999`.

In the public error legend `FINJA-999` is `UnexpectedError`, category
`unexpected` (900-999, "Generic / unexpected (prefer dedicated codes)"). It
is not a defect to repair; it is the catch-all that the contract itself says
should be replaced by a dedicated code. So the right response to a 999 is
*classify first*, and the right response to a 999 that merely wraps a
`TimeoutError` is to wait and see whether it recurs.

```text
POST /incidents      validate -> count -> route        creates no job
```

`POST /incidents` takes a redacted envelope (see
[`contracts/INCIDENT_ENVELOPE.md`](contracts/INCIDENT_ENVELOPE.md)) with the
same bearer auth and optional AES-GCM sealing as the job endpoints. It
answers with a decision and nothing else: **no job is staged, no worker
runs, no model is called**, and the response repeats no text from the
envelope. `FLARE-610` is a 400, `FLARE-611` a 422.

### The routes

| Route | Meaning | Would open a quest |
|---|---|---|
| `observe` | a transient or externally caused failure below its recurrence threshold: counted, nothing opened | no |
| `operator` | a config or host condition; a source diff will not fix an environment | no |
| `classify` | the catch-all code; the repair is a dedicated code at the reported frame | yes |
| `repair` | a deterministic defect with a dedicated code, or none | yes |
| `manual` | a sensitive area, a human-requested change, or a fix that did not hold | no |
| `tracked` | a quest for this exact error is already open | no |

The category comes from the code number, using the ranges the public legend
publishes (`config` 100-199, `llm` 200-299, `memory` 300-399, `session`
400-499, `tool` 500-599, `pipeline` 600-699, `host` 800-899, `unexpected`
900-999, `privacy` 1000-1099, `injection` 1100-1199). The legend lives
outside the container's build context, so the table is mirrored in code and
a test fails if the two ever disagree.

The first matching rule wins, and every decision says why:

1. `mode: manual` -> **manual**
2. `memory`, `session`, `pipeline`, `privacy`, `injection` -> **manual**. An
   automated patch must not decide anything in the diary and memory stores,
   authentication, the guards, or either firewall.
3. `config`, `host` -> **operator**
4. an open quest for this fingerprint -> **tracked**
5. the error returned after the allowed number of automatic fixes -> **manual**
6. a transient kind (`TimeoutError`, `ConnectionResetError`, `RateLimitError`,
   ...) or an external category (`llm`, `tool`) seen fewer than *threshold*
   times in the window -> **observe**
7. the `unexpected` band -> **classify**
8. anything else -> **repair**

So a `FINJA-999` wrapping a `TimeoutError` is observed twice and classified
on the third sighting, a `FINJA-999` wrapping a `KeyError` is classified at
once, a provider timeout (`llm`) is repaired only if it keeps coming back,
and a `SyntaxError` with no code is repaired immediately.

### Recurrence

Recurrence is counted per **fingerprint** of component, error code, error
kind and the top frame's path and symbol, and what it counts is **episodes**,
not raw sightings (see *Spam control* below). The line number is deliberately
not part of it: editing a file moves lines, and a defect must stay the same
defect when someone changes the code around it. The `incident_id` is not part
of it either, so a sender that mints a new id per occurrence is still
recognised. Replaying the same observation (same id, same time) counts once.

The window is anchored on the envelope's `observed_at`, not on the arrival
time, so a delayed delivery counts where the error happened. A timestamp far
in the future is clamped, so one bad clock cannot poison the window.

The ledger lives in `.incidents/ledger.json` beside the jobs, in a folder
that is not a job id, so job recovery and the quest count never mistake it
for one. It is written atomically and encrypted at rest whenever a transport
key is set. It stores identifiers and timestamps only -- component, code,
kind, top frame -- never a summary, source or message. It is bounded: slot
numbers (not timestamps) pruned to the window, 500 fingerprints, least
recently seen evicted first, and a fingerprint that tracks an open quest is
never evicted. A ledger written by the previous layout is migrated, not
refused. An
unreadable ledger is `FLARE-801`; silently starting over would forget a
recurrence, which is how a flapping error stays quiet.

### Configuration

| Variable | Default | Meaning |
|---|---|---|
| `INCIDENT_RECURRENCE_THRESHOLD` | `3` | **episodes** in the window before a transient error is worth a quest |
| `INCIDENT_RECURRENCE_WINDOW_SECONDS` | `3600` | the window |
| `INCIDENT_EPISODE_SECONDS` | `60` | the slot an error can fire repeatedly in and still count once |
| `INCIDENT_NOTIFY_COOLDOWN_SECONDS` | `3600` | how long the same route for the same error stays quiet |
| `INCIDENT_MAX_AUTO_FIX_ATTEMPTS` | `2` | automatic fixes that may fail to hold before the error goes to a human |

### Fix feedback

The ledger can record that a quest was opened for a fingerprint
(`attach_quest`) and that a fix landed (`record_fix`). Sightings after a fix
are flagged `regression_after_fix`, and once the allowed number of automatic
fixes has failed to hold the error is routed to a human instead of being
patched again. **Nothing calls these two yet**: with no job adapter there is
no quest to attach and no fix to record, so rules 4 and 5 are covered by unit
tests but cannot fire in a running stack. They become live when the adapter
that turns a `classify` or `repair` decision into a job lands.

### What this is not

- **Not the Finja side.** Emitting the envelope, and counting or sampling on
  Finja's side, is in a different module. A sender that samples under-counts,
  because Flare can only count what it receives.
- **Not a job.** The adapter that maps a routed incident into a repair
  request is its own open step, and it must not promote text from an
  envelope into instructions.
- **Policy, not law.** Sending `llm` and `tool` errors to *observe* first
  means a genuine bug in tool glue code waits for its third sighting. The
  sensitive and operator categories are fixed in code, not configurable.

---

## 🛡️ Spam Control (Phase C, #72)

Three layers, each one added because a measurement showed the problem, not
because spam is a general worry. The measurements were taken on a throwaway
stack, so the numbers are indicative; the shape is what matters.

### What was measured

| Probe | Result |
|---|---|
| a flapping monitor: five reports across one minute, `FINJA-999` wrapping a `TimeoutError` | escalated to a quest at the **third**, 24 seconds in |
| a submission that ends in "429, the questboard is full" | 16 ms with no history, 229 ms with 100 jobs, 880 ms with 400, **2.1 s with 1000**, all inside one lock |
| the privacy gate on one 300,000-character file of letters followed by `://` | **about a minute**; 20 such files, a quarter of an hour, with the interpreter lock held |
| a file of nothing but blank lines, in a `.txt` | 15 s at 40,000 characters; in a `.yml` it did not finish |

The last two were bugs in this layer's own earlier work, not in anything it
guarded. They were not exotic: **any** long run of letters (a minified file, a
base64 blob) triggered the first, because an unbounded `[A-Za-z0-9+.-]*` is
tried from every character of the run.

### 1. Episodes, not sightings

An error that fires five times in one slot is one episode seen five times.
Time is cut into fixed slots (`INCIDENT_EPISODE_SECONDS`, one minute), and the
recurrence threshold counts **slots that saw the error**. The same five
reports across one minute are now one episode and stay `observe`; the same
error in three separate minutes still escalates.

Fixed slots, not "close to the previous event", on purpose: a monitor that
fires every 90 seconds forever must still escalate, and chaining would let it
stretch a single episode indefinitely. The cost is a granularity of one slot
-- a burst can straddle one boundary and count as two episodes, never three.
A record keeps slot numbers rather than timestamps, so a sender firing once a
second cannot push its own history out of a bounded list and go quiet.

Every sighting is still counted (`total`, `sightings_in_episode`); only the
escalation arithmetic changed.

### 2. A decision says whether anyone should be told

Every `POST /incidents` answer carries `notify`:

```json
{"send": true, "reason": "first_notice", "until": "2026-10-17T17:00:00Z"}
```

`send` is true only for a route a person acts on (`operator`, `classify`,
`repair`, `manual`) and only when the route is new for that error or has
changed -- an escalation is news -- or when the cooldown since the last
message has elapsed. `observe` and `tracked` never send. A replay never sends.
A fix that lands resets the conversation, so a return is announced again.
Asking twice does not send twice.

This is the whole of the anti-spam contract Flare can offer a caller. Flare
posts nowhere itself; whoever does post (Finja, a Discord bridge) is expected
to honour `send`.

### 3. Rate limits

`POST /jobs`, `POST /jobs/{id}/retry` and `POST /incidents` sit behind token
buckets, so a sender stuck in a loop is turned away **before** the expensive
work instead of after it. A refusal is `HTTP 429`, `FLARE-613`, with a
`Retry-After` header, and costs about two milliseconds.

| Variable | Default | |
|---|---|---|
| `JOB_RATE_BURST` / `JOB_RATE_PER_MINUTE` | `10` / `30` | jobs and retries |
| `INCIDENT_RATE_BURST` / `INCIDENT_RATE_PER_MINUTE` | `60` / `120` | incident reports |
| `RATE_LIMITING` | `1` | `0` switches it off |

- **Separate buckets.** A flapping monitor is noisy by nature and must not be
  able to use up the budget for jobs, or the other way round.
- **Human decisions are never limited.** Approve, reject, cancel, delete and
  every read are not routed through it, so a flood of submissions cannot
  starve the person who has to approve something.
- **Authentication comes first.** A request without a valid token is a `401`
  and spends nothing, so it cannot drain the real sender's budget.
- **Fail soft.** The limiter is arithmetic on three numbers under one lock: no
  I/O, no other lock, a clock that steps backwards is clamped. An unknown
  bucket name lets the request through. It has no way to wedge the pipeline.
- **This is not the questboard limit.** `FLARE-603` (the quest cap) is a
  different 429 with a different remedy -- finish a quest, not wait a few
  seconds -- and carries no `Retry-After`.

`/health` reports the limits in force. The buckets live in memory, so a
restart refills them; that is fine for a guard against loops. Each kind of
traffic has one global bucket, not one per sender: the endpoints share one
bearer token, so there is one sender to limit.

### Linear-time scanning

Every repetition in the privacy gate's patterns, and in the envelope's e-mail
pattern, is now bounded (URL schemes, user names, e-mail local parts, key
names), whitespace in line-anchored rules cannot span newlines, and line
numbers come from a binary search over line breaks instead of a count per
hit. The worst case over every adversarial shape tried, at the file-size
limit, is now about 50 ms. A regression test feeds each shape through every
rule at a size where a quadratic scan takes seconds and a linear one
milliseconds, and putting a bounded pattern back to its old form makes it
fail.

### What this does not do

- **The scan of the job folders is still linear in the history.** The limiter
  bounds how many requests may pay that cost; it does not remove it. At a
  thousand finished jobs a request that reaches the duplicate lookup still
  costs seconds. A job index or a retention policy is its own piece of work.
- **No Discord-side protection.** Nothing in this repository talks to
  Discord. Collapsing a double-clicked button is the bridge's job; what Flare
  gives it is `deduplicated` on a job, `duplicate` on an incident, `notify`,
  and a `429` with `Retry-After`.
- **No cooldown after a rejected fix.** That needs the job adapter, which does
  not exist yet; `record_fix` and the open-quest check are in place for it.
- The envelope has no `dedupe_key` and cannot get one: version 1 is strict.
  The fingerprint plays that role.

---

## 🔑 Source Identity and Minimality (Phase C, #73)

### What already existed

This item was started from the assumption that the way back out was
unprotected, so it was tested before anything was built. The result:

- the incident envelope **already verifies a SHA-256 for every file** it
  carries (#69), with size limits of five files and 60 KB per file;
- the sandbox **already compares a digest of the whole workspace** before
  approval and after the apply, so a diff or an input swapped in between is
  caught. Tried directly with the real worker code: replacing `model.patch`
  after the test, and altering the staged input after the test, both end as
  `rolled_back` with `FLARE-501`, "Approved candidate differed from its
  sandbox test evidence";
- manual hand-offs and hotfix packets **already bind** the exact diff with
  `patch_sha256`.

### What was missing

The way *out*. A result carried `path` and `content` and nothing that said
which input a candidate was made from, and nothing measured how much of what
an incident carried was needed.

### The result manifest

Every job result that carries files (the candidate shown for approval, and
the finished job) now has a `manifest`, and `GET /jobs/{id}/files` names the
bytes of every file it delivers (`sha256`):

```json
{
  "schema_version": 1, "algorithm": "sha256",
  "hashed_over": "UTF-8 content exactly as transmitted",
  "base_known": true,
  "files": [{
    "path": "demo.py", "status": "modified",
    "base_sha256": "…", "candidate_sha256": "…",
    "base_bytes": 32, "candidate_bytes": 32,
    "lines_added": 1, "lines_removed": 1
  }],
  "summary": {"files": 1, "modified": 1, "unchanged": 0, "line_endings_only": 0,
              "created": 0, "deleted": 0, "unknown": 0},
  "base_bundle_sha256": "…", "candidate_bundle_sha256": "…"
}
```

It holds hashes, sizes and statuses, never content. Line counts come from the
L2 review that already parsed the diff; diffing two large files on a request
path was not an option.

| Status | Meaning |
|---|---|
| `modified` / `unchanged` | content differs / is identical |
| `created` / `deleted` | only in the candidate / only in the input |
| `line_endings_only` | identical except for `\r\n` versus `\n`: a whole-file rewrite, not an edit, which a receiver can choose to decline |
| `unknown` | the input could not be read, so nothing is claimed about it (`base_known: false`) |

**The base is the orchestrator's own staged copy**, never the worker's
result. The worker runs in a container and is the less trusted side, and the
staged copy is what the sender can reproduce byte for byte.

#### What a receiver does with it

Flare never sees the live file, by design, so it cannot check for drift. It
states exactly which bytes it started from, and the owner of the live file
compares:

1. before applying, hash the live file and compare it with `base_sha256`; if
   it differs, the file changed after it was analysed, so do not apply;
2. hash each delivered file and compare it with `candidate_sha256` (and the
   set with `candidate_bundle_sha256`) to know it arrived as tested.

`core/source_manifest.verify_files` is the reference for the second check.
The bundle digest is SHA-256 over, for every path in sorted order: a 4-byte
big-endian path length, the UTF-8 path, and the 32 raw bytes of the file
digest. A test reproduces it independently, because a receiver in another
language has to.

Hashes identify the bytes **as transmitted**. If the sender redacted before
sending, they identify the redacted copy, as the envelope's own `sha256`
does. A hash of the unredacted original is not Flare's to know; Finja keeps
that one itself, keyed by `incident_id`.

### How little was needed

`POST /incidents` now also returns a `source` block: per file the size, the
line count and whether any stack frame points at it, the total against the
bundle limit, the files **no frame points at**, and frames whose file was
never sent. The verdict is `minimal`, `has_unreferenced_files`, or
`unjudged` when there are no frames to judge against (nothing is called
excess then). It informs and never refuses: a repair may need a helper that is
on no stack.

### A bug found on the way

Reading the worker's snapshot as *text* translated `\r\n` to `\n`, but the
sandbox's digest is taken over the *bytes*. A job with one patched file and
one **untouched file with Windows line endings** therefore failed its own
integrity check and was rolled back with `FLARE-501`, every time. Windows
checkouts make that likely, not exotic. `snapshot_files()` now decodes the
bytes, and the same job completes. Four tests fail if the old line is put
back, two of them end to end through the real worker code.

**Not fixed, and not verified:** `patch` itself rewrote a CRLF file it patched
to LF when tried locally, so a *patched* CRLF file comes back with LF endings
(the manifest then reports it as `modified`, or `line_endings_only` if
nothing else changed). Whether the container's `patch` behaves the same could
not be checked, because Docker was not running.

### What this does not do

- **No excerpts in place of whole files.** An envelope carrying only a window
  of a file is a wire-contract change: version 1 is strict. It would also need
  a `start_line`, because a diff made against an excerpt has hunk numbers that
  do not match the real file. That is a v2 decision.
- **No fetching a file by its hash.** Flare has no access to Finja's tree, on
  purpose; it can only be told what it needs.
- **The hash is not part of the recurrence fingerprint.** That would make
  every unrelated edit to a file look like a new defect, the opposite of
  deduplication.

---

## 📦 Changeset: Diff, Undo and Backup Manifest (Phase C, #74)

### Who applies what

Flare never writes to Finja's tree, by design. The `applying` state of a job
is the sandbox applying the approved diff to its own copy, to verify it; the
change reaches production only when Finja applies it. An "apply executor" with
a production rollback therefore cannot live here. What Flare can do is hand
over a record that makes Finja's apply **checkable** and its undo **exact**.

### Two gaps, measured first

- **There was no diff on the standard path.** `GET /jobs/{id}/manual` exposed
  one, but only for the manual route; an approver of an ordinary candidate was
  shown whole files.
- **The approval recorded which revision, not what.** A worker (the container,
  the less trusted side) that reported consistent test evidence but returned
  *other files* after approval still ended `completed`, delivering content the
  approver never saw. The sandbox's digest is computed by the worker and only
  compared between phases, so it catches inconsistency, not a worker that is
  wrong.

### Content-bound approval

Approving now records `approval`: the revision, the time, and the base and
candidate **bundle digests** from the manifest the approver was shown (see
*Source Identity*), which the orchestrator itself hashed. When the job finishes
it hashes the files it is about to deliver and holds them against that digest;
a mismatch ends the job as `rolled_back` with `FLARE-501`, "Delivered files
differ from the candidate that was approved". A job approved before this
existed carries no digests and is not failed by the check.

### `GET /jobs/{id}/changeset`

Available while a candidate **awaits approval**, so it can be reviewed as a
diff, and after the job has **completed**; any other state is a `409`. Same
auth as the other endpoints, sealed when transport encryption is on.

| Field | Contents |
|---|---|
| `diff` | the unified diff (`patch -p0`) with its SHA-256, size, per-file counts |
| `reverse_diff` | its exact inverse, with its SHA-256 |
| `before_after` | per changed file: status, before and after SHA-256 and sizes |
| `tests` | the candidate's test evidence, after completion also the evidence after the apply, and whether they reproduced |
| `approval` | what was approved (see above); `approved` is true once completed |
| `backup_manifest` | the bundle digests, the digest the files must return to after a rollback, and per file how to restore it |
| `procedure` | the apply and rollback steps below |
| `provenance` | what the diff is computed from, and the hash of the model's own diff |

Outside the two diffs the record holds hashes and sizes only; an untouched
file's content never travels.

**Where the diff comes from.** It is computed from the submitted input and the
candidate, not copied from the model. A model's hunk headers are often only
approximately right and rely on `patch` searching for the spot; the difference
between two known texts has exact line numbers and applies strictly. The
model's diff is tied in by its hash. The inverse is the same computation with
the two sides swapped, so it is exact by construction, and the inverse of a
deletion re-creates the file.

### The procedure, and the checks that go with it

1. **Before applying**, hash each changed live file; it must equal
   `before_sha256` (a file Flare created must not exist yet). A mismatch means
   the file changed after it was analysed: stop.
2. Apply the diff, or write the delivered content, to a temporary file and
   replace atomically.
3. **After applying**, each changed file must equal `after_sha256` (a deleted
   file must be gone). If not, roll back at once.
4. **To roll back**, first check each file still equals `after_sha256`, then
   apply `reverse_diff`, then check it equals `before_sha256` again.

`core/changeset.check_state(changeset, live_files, expect="before" | "after")`
is the reference for all four checks. It returns the problems found
(`digest_mismatch`, `missing`, `unexpected_present`); an empty list means every
changed file is exactly where it should be. Flare cannot run these itself,
because it never sees the live files.

Verified with the real worker code and the real `patch` program: apply, check,
roll back, and the tree is byte-identical to where it started; a file edited in
between is caught before anything is applied.

### Limits

- **The diff has a budget.** `difflib` is quadratic in the worst case (a file of
  100 repeating lines, shifted, costs 0.35 s at 20,000 lines and grows with the
  square), so the diff is produced within **20,000 lines and 1 MB** in total.
  Past that the changeset says `too_large_to_diff`, still carries every hash,
  and marks the restore as unavailable. A receiver can still verify a
  replacement. A file with huge numbers of identical lines gets a valid but
  larger-than-minimal diff, which is `difflib`'s own trade-off.
- **This is not a backup of the live files.** Flare cannot back up what it
  cannot see. The record says what the files must hash to and how to reverse
  Flare's own change; an applier that wants to survive a file that drifted
  after the check should keep its own copy of the bytes it is about to replace.
- **Line endings.** A diff of a file with Windows line endings keeps them and is
  applied correctly by a strict applier. Whether the container's `patch`
  preserves them is the open question recorded under *Source Identity*.
- **No return path through the incident envelope yet.** There is no job adapter
  that turns a routed incident into a job, so there is nothing to carry a
  changeset back to an incident.
- The test suite already runs in the sandbox before approval and again after the
  apply (L3); the changeset reports both and whether they reproduced.

---

## 🛰️ Quest Supervisor (Phase C, #75)

The roadmap item describes an asynchronous supervisor that owns a queue, retries
and admission control and "closes the job-adapter gap". Nothing in this
repository or the ecosystem defines such a thing, and a queue between Finja and
Flare would duplicate what the questboard already is (durable job folders, a
five-quest cap, rate limits). So this is the part of "supervisor" that was
actually missing in Flare, found by measurement.

### What was measured

- Five candidates waiting for approval fill the questboard. Every new
  `POST /jobs` is then refused with `FLARE-603` ("Active Flare job limit
  reached (5/5)"), for as long as nobody clicks. Nothing reminded anyone and
  nothing ever expired: the first error Finja finds after a weekend of unanswered
  approvals would be turned away.
- `stale_active_jobs` counted executing jobs whose heartbeat had stopped and
  showed the number in `/health`. Nothing acted on it. A job thread that died
  left its quest stuck and counted.
- A job's deadlines are enforced by the thread that is being timed, so a quest
  nobody runs has nobody enforcing them.
- The container had no `HEALTHCHECK`; a wedged API still showed as running.
- Writing a status moves the `revision`, and approval is bound to the revision.
  A reminder written into the status would invalidate the approval button the
  person is about to press.

### What it is

A separate loop with its own failure domain. It serves no requests and runs no
jobs, so a flood of one or a stuck job in the other cannot stop it. The decision
is a pure function (`core/supervisor.py`: snapshots in, actions out); the
orchestrator carries each action out under the same locks the endpoints use and
**re-checks it first**, because a person may have approved, rejected or
cancelled between planning and acting.

| Situation | What happens |
|---|---|
| Candidate waits for approval for `REMIND` (24 h) | A `remind_approval` event, repeated every `REMIND`. |
| Waits for `EXPIRE` (72 h) **and a reminder has been out for `NOTICE` (1 h)** | Withdrawn: rolled back to the original files, `FLARE-614`, `outcome: approval_expired`. The slot is free again. |
| Past `EXPIRE` but never reminded (for example Flare was down for a week) | Reminded first, withdrawn only after the notice period. A restart does not wipe the board. |
| Executing quest, no thread running it, silent for `ORPHAN` (120 s) | Resumed, the same resume the process start performs. At most `MAX_RESUMES` (2) times. |
| Resumes used up | Rolled back with `FLARE-800`, `outcome: orphaned`. |
| Thread alive but silent for `HUNG` | **Reported only.** A thread cannot be killed from outside; the job's own deadlines stay in charge. |
| Terminal job, or a quest that is moving | Untouched. |

Flare posts nowhere. A reminder is an event a poller reads from `GET /supervisor`;
whoever turns it into a message (Finja, a Discord bridge) is the one who actually
gives notice. The withdrawal is the backstop for the case where nobody ever does.

Reminders and resume counts live in `JOBS_DIR/.supervisor/state.json`, not in
the job status, for the revision reason above. Losing that file costs one
repeated reminder, so an unreadable file starts empty. The dot-prefixed folder
is not a job id, so no job scan mistakes it for one.

### `GET /supervisor`

Authenticated like the job endpoints. Returns the supervisor's vital signs
(`running`, `stalled`, `last_sweep_age_seconds`, `sweeps`, `errors`, counters
per action), its `policy`, the last 100 `events`, and a `board` of the quests
that need a person: how long each has waited and `expires_in_seconds`. `/health`
carries the same vital signs under `supervisor`.

### Watching the watcher

`stalled` is computed on the request thread, so it still reads true when the
supervisor thread died or hung: a supervisor that reports only through itself
cannot be supervised. It is true when the thread is dead, or when no sweep has
finished within `max(3 x interval, interval + 60 s)`.

The image now has a `HEALTHCHECK` (`python -m app.healthcheck`, standard library
only): unhealthy if the API does not answer, says it is not ok, or its
supervisor is enabled and stalled. **Docker only marks the container unhealthy;
it does not restart it.** Something outside (compose with a restart policy and
an autoheal sidecar, a watchdog, a person) has to act on that.

### One sweep that fails does not end the loop

An unexpected error in a sweep is logged with a structured code, counted in
`errors`, and the loop carries on. One quest that cannot be handled does not stop
the others in the same sweep.

### Configuration

| Variable | Default | Meaning |
|---|---|---|
| `SUPERVISOR` | `1` | `0` turns it off (a warning is logged; stuck quests then stay stuck). |
| `SUPERVISOR_INTERVAL_SECONDS` | `60` | Time between sweeps. |
| `SUPERVISOR_APPROVAL_REMIND_SECONDS` | `86400` | First reminder, and the repeat interval. Must be smaller than the expiry or the service refuses to start. |
| `SUPERVISOR_APPROVAL_EXPIRE_SECONDS` | `259200` | Wait after which a candidate may be withdrawn. |
| `SUPERVISOR_APPROVAL_NOTICE_SECONDS` | `3600` | A reminder must have been out this long before a withdrawal. |
| `SUPERVISOR_ORPHAN_SECONDS` | `120` | Silence before a thread-less quest counts as orphaned. |
| `SUPERVISOR_MAX_RESUMES` | `2` | Resumes before the quest is rolled back. |
| `SUPERVISOR_HUNG_SECONDS` | `2 x JOB_TOTAL_TIMEOUT_SECONDS` | Silence of a live thread before it is reported. |

### Verified

`test_supervisor.py` (66 tests) pins the plan as a table (every boundary, the
notice rule, a clock stepping backwards), the execution (a reminder leaves the
status bytes and the revision untouched and the approval button still works, a
withdrawal frees the slot that was blocking new work, a stale plan loses to a
person's decision, a failing quest does not stop the others, memory survives a
restart and forgets finished jobs), the loop surviving a failing sweep, stall
detection and the health probe including its exit code against a real socket.
27 deliberate mutations of the planner, executor, liveness and probe were each
caught. Run for real as well: uvicorn on a socket, the real supervisor thread
and clock with 2 s / 5 s thresholds, two seeded candidates were reminded, then
withdrawn with `FLARE-614`, `/health` stayed `stalled: false`, and the probe
exited 0.

### What this does not do

- **It is not the job adapter.** The item's "closes the job-adapter gap" is not
  true of this work: nothing here turns a routed incident into a job, and
  `attach_quest`/`record_fix` still have no caller. That remains the largest
  missing piece and is listed in the TODO.
- **It does not queue.** Admission control is the questboard cap plus the rate
  limits (#72). The supervisor only keeps the cap from being held by quests
  nobody is looking at.
- **It does not restart anything.** A dead supervisor thread is reported, not
  revived; revival is the container's job (see above).
- **It cannot tell a person is looking at a candidate.** The expiry is a clock.
  Raise it if reviews are slow; a withdrawn candidate is resubmitted, not lost,
  because the original files are restored.
- **Open-quest counts are as of the last sweep.**

---

## 🔒 Container Write Boundary (Phase C, #76)

The roadmap item reads "no direct writes into the running main container". The
description that came with it lists immutable images, a read-only root
filesystem, an admission controller and audit alerts on the main workload. Those
are properties of how Finja's main container is deployed, and that container is
not in this repository. What Flare can do is make sure that **Flare itself**
never writes into a running container, and make that fail closed instead of
being a convention. This is that part, with the limits stated below.

### What was measured

- One job's whole life in the orchestrator (stage, worker phase, status changes,
  approval wait, supervisor sweep, rollback) writes **65 paths, all under
  `JOBS_DIR`**. A sibling folder standing in for the main container's tree was
  not touched. So the property holds today.
- It held **by construction only.** The orchestrator mounts the Docker socket
  (a requirement for starting workers), which can `exec` into, `cp` into or
  `commit` any container on the host. The only thing between Flare and that was
  that nobody had written such a line. Nothing would have stopped a later
  change, a command assembled from a variable, or a value influenced by model
  output from reaching a command line.
- There were exactly two process calls in the orchestrator, both Docker: the
  worker `docker run` and the cleanup `docker rm -f`. Nothing else starts a
  process.
- Two quieter paths existed: a host folder setting could add mount options
  after a colon, and Docker creates a missing bind source, so a wrong
  `AGENT_JOBS_HOST_DIR` could make it create folders in a place never meant for
  Flare.

### What it does

`core/exec_guard.py` is the one place that decides which container commands may
run. The commands are built there and judged again before they run; the
orchestrator runs only what passes. Anything else raises **`FLARE-502`**
(`DirectWriteRefusedError`).

| Allowed | Shape |
|---|---|
| Start a worker | `docker run` of the configured worker image with exactly the hardening Flare already used (offline, read-only root, all capabilities dropped, no new privileges, bounded pids/memory/cpus, own `/tmp`), the job id and phase as the only environment, and **one** bind mount: this job's own sandbox copy. |
| Remove a worker | `docker rm -f` of a name only a worker can have (`finja-agent-worker-<12 hex>-<phase>`). |

Refused, among others: `exec`, `cp`, `commit`, `attach`, `start`, `stop`, `kill`,
`restart`, `update`, `create` and every other verb; any program that is not
`docker`; any other image; a second mount, the Docker socket, the job's
workspace or request instead of its sandbox copy, a mount target other than
`/jobs/<id>`; `--privileged`, host network/PID/IPC namespaces, extra
capabilities, devices, `--volumes-from`, a command or entrypoint override,
extra environment; any unknown flag; and **any flag given twice**, because with
`--network none --network host` the last one wins and "the guard saw `none`"
would be no comfort. Removing `finja-main` or Flare's own orchestrator container
is refused for the same reason it is for anything else that is not a worker. A
refusal names the verb or flag, never the arguments, so it cannot echo a secret.

The host folder is judged too (`GET /health` reports `write_boundary.host_jobs_dir_ok`
on every call, since a wrong value would otherwise only show at the first worker
phase): it must be a plain absolute path, without a colon (which would add mount
options), shell or control characters, relative segments, a filesystem root, the
Docker socket or a system tree (`/etc`, `/proc`, `/sys`, `/dev`, `/run`,
`/var/run`, `/boot`, `/root`, `/bin`, `/sbin`).

`FLARE_PROTECTED_HOST_PATHS` (comma separated, empty by default) lets the
operator name the main container's host folders. A worker mount whose source is
equal to or inside one is refused. A sibling or a parent is not "inside": the
mount source is always the job's own subfolder.

### Checked from outside as well

- `test_exec_guard.py` builds the real command and compares it with the command
  Flare ran before the guard existed (byte for byte), then tries 84 ways to
  widen it, each of which must be refused; plus the removal shapes, 60 host
  folders (10 accepted, 50 refused), and the orchestrator wiring (a vetoing guard stops a phase before
  Docker is asked, a cancel still finishes when its removal is refused).
- **Where the pipeline writes** is recorded with a Python audit hook while a
  whole job runs, and every write must be under `JOBS_DIR`. The same test first
  proves the recorder is not blind.
- **Who can start a process** is read from the source with the AST: exactly two
  functions in the orchestrator, each asking the guard before it runs, each
  passing the guarded value (not a literal) to the call; no process call in
  `core/` or any other app module; no Docker, SSH or remote-execution library
  imported; nothing opens the Docker socket directly; no script, compose file or
  Dockerfile contains `docker exec/cp/commit/attach`, `kubectl exec/cp/patch`,
  `--privileged`, `--volumes-from` or host PID; and the compose files mount
  nothing but the jobs folder and the (single) socket.
- `test_exec_guard.py` has 274 tests. 43 deliberate mutations of the guard and its wiring were each caught; adding a
  stray `subprocess` call, an `os.system`, a `docker exec` line in a script or
  an `import docker` each fails the suite.

### What this does not do

- **It cannot stop someone who already has a shell in the orchestrator
  container, or code execution in its process.** With the Docker socket mounted
  that is the host. This guard closes the gap inside Flare's own code; the
  boundary against everything else is the deployment's job.
- **Hardening the orchestrator container is not done here.** A read-only root
  filesystem, `cap_drop: ALL` and `no-new-privileges` for the orchestrator, and
  a Docker socket proxy that allows only container create/start/delete (and
  forbids `exec`), would each shrink what a compromised orchestrator can do.
  I could not run Docker in this environment, so none of them is verified
  against a live stack and none was added to `docker-compose.yml`. They belong
  in a hardened compose override that has been started once on the real host.
- **The main container itself is not touched or checked.** Whether Finja's
  container is read-only, immutable, or protected by an admission policy is a
  Finja-side deployment property. Flare's side of it is: results leave Flare as
  a pull (the changeset with hashes, #74); Flare never pushes into anything.
- **`FLARE_PROTECTED_HOST_PATHS` only knows what it is told.** Empty by default;
  nothing in this repository knows where Finja's data lives.
- **Writes inside the jobs folder are unrestricted by design.** That folder is
  Flare's own.

---

## 🔥🧪 Test Track (Phase A)

Flare's stability guards only prove something if they can be *made* to fire.
The test track is a deliberately broken worker image plus a catalog of
known-bad scenarios, so the state machine, timeouts, heartbeats, locks and
fail-soft rollback can be exercised on purpose instead of by accident.

`worker-broken/` builds `finja-agent-worker-broken:dev`, a **drop-in
replacement** for the real sandbox: same env contract, same `/jobs` mount,
same result files. The honest `ok` path is delegated to the real
`worker/worker.py` rather than copied, so the fixture cannot drift away from
the thing it imitates.

> **This image is test infrastructure.** It must never be the configured
> `WORKER_IMAGE` of a production stack. Its default plan is empty, so an
> unconfigured container behaves like the real worker instead of failing
> silently, and the runner refuses to start against a non-broken image.

### Fault plan

Each phase is told how to misbehave. The plan is resolved in this order:

1. `workspace/flare_fault.json` — travels inside the job payload, so one
   image serves the whole catalog without a restart
2. `FLARE_FAULT_PLAN` — stack-wide default via env
3. `ok` — behave like the real worker

Both places accept a bare mode (`hang`), the shorthand
(`verify=hang,default=ok`), or JSON (`{"default": "ok", "phases": {"verify": "hang"}}`).

| Mode | Behaviour | Guard it trips |
|---|---|---|
| `ok` | real worker logic | happy path |
| `slow:<seconds>` | late but correct | heartbeats / progress reports |
| `hang` | never returns | `FLARE-500` + fail-soft rollback |
| `crash:<code>` | non-zero exit | `FLARE-501` |
| `no_result` | exits 0, writes nothing | `FLARE-501` |
| `invalid_result` | writes unparsable JSON | `FLARE-501` |
| `patch_fail` | `patch_result.returncode != 0` | `FLARE-501` |
| `syntax_fail` | injected postflight finding | `FLARE-501` |
| `wrong_job` / `wrong_phase` | result claims another job/phase | `FLARE-801` on resume |
| `oom` | grows past the container limit | `FLARE-501` (killed) |

An unusable plan or unknown mode exits non-zero with a stderr note, which the
orchestrator surfaces as `FLARE-501` with the stderr tail attached. The
sandbox has no structured error channel of its own by design: it holds no
secrets and shares no code with `core/exceptions.py`.

### Running the track

> **`FLARE_TESTBED_JOBS_DIR` is mandatory**, and must be an absolute host
> path that no production stack uses. This is not tidiness:
> `recover_incomplete_jobs()` scans every job folder it can see on start and
> resumes anything in a recoverable state. Pointed at a production
> `agent_jobs` folder, the track would pick up real in-flight jobs and run
> them through the fault-injection worker. The override therefore refuses to
> start rather than inheriting `AGENT_JOBS_HOST_DIR` from `.env`.

```bash
docker build -f worker-broken/Dockerfile -t finja-agent-worker-broken:dev .

export FLARE_TESTBED_JOBS_DIR=/absolute/path/to/agent_jobs_testbed
mkdir -p "$FLARE_TESTBED_JOBS_DIR"

docker compose -p flare-testbed -f docker-compose.yml -f docker-compose.testbed.yml up -d --build
python testbed/run_testbed.py --base-url http://localhost:8078

# tear down with the same -p, and with FLARE_TESTBED_JOBS_DIR still set
docker compose -p flare-testbed -f docker-compose.yml -f docker-compose.testbed.yml down
```

> **`-p flare-testbed` is not optional either.** Without its own project
> name the track runs in the production project under the same service
> name `orchestrator`; Compose then sees one service with a changed config
> and **replaces the production container** with the testbed one. The
> production stack goes down while the command still looks successful. The
> same `-p` belongs on the `down`, which also still needs
> `FLARE_TESTBED_JOBS_DIR` set, or the interpolation fails and the
> container stays up.

The override runs on port **8078** under its own container name, so the
track can sit beside a normal stack. It declares `ports: !override`
because Compose *appends* sequences when merging `-f` files — without the
tag the testbed container would inherit production's `8077:8077` on top
of its own port, try to bind both, and fail to start as soon as a real
stack holds 8077 (needs Compose v2.24.4 or newer). Every value in it exists to make
results deterministic: the broken worker image, a separate job tree, an
empty `OPENROUTER_API_KEY` (no model, no diff), `DEDUPE_WINDOW_SECONDS=0`
(or a repeated run returns the first job), and short
`JOB_*_TIMEOUT_SECONDS` so a hang fails in seconds instead of ten minutes.

Because `docker-compose.yml` loads the production `.env` into this service
too, the override also blanks every credential that file defines.
`ORCHESTRATOR_AUTH_TOKEN` is the one that bites: inherited, every
submission returns **401** while `/health` — which needs no auth — still
reports a healthy stack, so the whole catalog fails for a reason that has
nothing to do with the guards. `CODE_AGENT_TRANSPORT_KEY` is blanked as
well, so no production secret reaches a throwaway stack and job files stay
readable while debugging a fault. Since the track therefore runs
**unauthenticated**, 8078 is bound to `127.0.0.1` only and is not
reachable from the network.

The runner refuses to start unless `/health` reports the broken image, and
warns when the stack already has active jobs — the one hint available that
it might be looking at somebody else's job tree.

```powershell
python testbed/run_testbed.py --list                      # the catalog
python testbed/run_testbed.py --scenario preflight_crash   # one scenario
```

Exit codes: `0` all selected scenarios met their expectation, `1` at least
one did not, `2` the track itself could not run (`FLARE-100`).

### What the catalog pins down

`testbed/scenarios.json` carries each scenario's fault plan, payload,
expectation and — importantly — *why* it exists. Two findings are worth
calling out, because both are easy to get wrong:

- **Pre-approval and post-approval failures end differently.** A non-timeout
  failure before approval becomes `failed`; the same failure after approval
  becomes `rolled_back`. That asymmetry is deliberate and is pinned by the
  `preflight_crash` and `verify_crash_rolls_back_after_approval` scenarios.
- **In dry-run mode the submitted candidate is its own candidate.** With no
  model there is no diff, so the payload itself goes through postflight
  verification. Scenario payloads are therefore valid Python with a
  *logical* bug; only `preflight_rejects_broken_syntax` ships unparsable
  code, and `test_testbed.py` enforces that rule so nobody breaks the track
  by "fixing" a fixture.

Two scenarios carry a `requires` key and are **skipped** by the sequential
runner: `wrong_job_checkpoint` needs a process restart to re-read the
checkpoint, and `repository_lock_serialises_two_jobs` needs two concurrent
jobs. The checkpoint-ownership guard is covered Docker-free in
`test_testbed.py`; driving the lock pair is still open.

---

## 📋 Scope & Status

What the orchestrator does today:

- Accepts code files by JSON.
- Stages them into an isolated job folder.
- Spawns one short-lived offline Docker worker for preflight syntax checks.
- If OpenRouter is configured, asks the model for a unified diff.
- Tests the candidate in a disposable worker and waits for explicit approval.
- Applies only the approved revision, then verifies it in another offline phase.
- Returns summary, status, logs, and final file contents.

### Current Architecture TODO

- [x] Slice 1: Orchestrator service + throwaway worker containers.
- [x] Slice 1: OpenRouter model call works with `moonshotai/kimi-k2.7-code`.
- [x] Slice 1 security hardening: OpenRouter key stays in orchestrator, worker runs with `--network none`.
- [x] Slice 2 foundation: bounded retries, layered timeouts, durable cancellation, and restart recovery.
- [x] Slice 2 durability: request dedupe, idempotency keys, atomic staging, and phase-checkpoint resume.
- [x] Slice 2 state contract: exact forward-only lifecycle, revision-bound approval, rollback, and a five-quest cap.
- [x] Slice 2 observability: durable heartbeats, visible runtime deadlines, stale detection, and bounded intermediate reports.
- [x] Slice 2 concurrency: global/per-repository limits plus cross-process exclusive file locks.
- [x] Slice 2 Finja safety: timeouts roll back fail-soft with stable retry metadata and idempotent retry.
- [x] Slice 2 test track: deliberately broken drop-in worker image, scenario catalog, and Docker-free guard tests.
- [ ] Slice 2: iterative repair loop with max 3 model-repair rounds.
- [x] Phase B: L1 diagnosis is a deterministic, static contract that declares its own blind spots.
- [x] Phase B: L2 drafts a repair diff without applying it, bounded by a reviewed repair scope.
- [ ] Phase B: let the L1 verdict gate the lifecycle (a policy change: it would reject payloads that pass today).
- [x] Phase B: L3 sandbox repair plus reproducible, offline Python `unittest` evidence before and after approval.
- [x] Phase B: L4 hotfix mode requires repeated green sandbox runs before revision-bound human approval.
- [x] Phase B: L5 routes multi-file and architectural work to a documented human-only handoff.
- [x] Phase C: versioned, redacted Finja-to-Flare incident envelope and fail-closed validator (#69).
- [x] Phase C: secrets, `.env`, tokens, diary/memory data and credential-shaped content are refused at intake with `FLARE-612` (#70).
- [x] Phase C: `FINJA-999` and recurring internal errors are routed by category, kind and recurrence; `POST /incidents` answers with a decision and creates no job (#71).
- [x] Phase C: flapping errors count as episodes, decisions say whether a human should be told, and submissions are rate-limited before the expensive work (#72).
- [x] Phase C: results name the exact bytes they are about (per-file SHA-256 manifest), incidents report how much of their source no frame points at, and an untouched CRLF file no longer rolls a job back (#73).
- [x] Phase C: approval is bound to content, an approver can review the unified diff, and a `changeset` carries the diff, its exact inverse, before/after hashes, test evidence and a backup manifest with checks for apply and undo (#74).
- [x] Phase C: a quest supervisor, independent of request and job threads, reminds about unanswered approvals, withdraws them after a notice period (`FLARE-614`) so they stop blocking the five-quest cap, resumes orphaned quests, watches itself via `/health` and a container `HEALTHCHECK` (#75).
- [x] Phase C: Flare's container commands are limited to a guarded worker `docker run` (own sandbox copy only) and a worker `docker rm -f`; anything else, including `exec`/`cp`/`commit`, fails closed with `FLARE-502`, and the host folder is validated (#76).
- [ ] Phase C: harden the orchestrator container itself (read-only root, `cap_drop`, a Docker socket proxy without `exec`); needs a live Docker host to verify, so it is not in the default compose file.
- [ ] Phase C: a job adapter that turns a routed `classify`/`repair` incident into a job, so a changeset has an incident to travel back to.
- [ ] Phase C: an envelope v2 that carries excerpts with a `start_line` instead of whole files (a wire-contract decision).
- [ ] Phase C: `patch` rewrites CRLF to LF in the file it patches (seen locally); check the container's `patch` and decide whether line endings must survive.
- [ ] Phase C: every submission scans all job folders, so a refusal gets slower as history grows; a job index or a retention policy would end that.
- [ ] Phase C: emit the envelope in Finja, and map a routed `classify`/`repair` decision into a Flare job (which also brings `attach_quest`/`record_fix` to life).
- [ ] Phase B: additional runners (`pytest`, `node --check`, package scripts) with pinned dependencies and explicit policies.
- [ ] Phase B: a JavaScript parser in the worker image, so `.js`/`.ts` stop being a declared blind spot.
- [x] Slice 3: generic scoped `/jobs` endpoint/auth (not yet the redacted incident intake).
- [x] Slice 3: download/preview handoff back to user.
- [x] Transport hardening: AES-GCM app-layer envelope + encrypted job metadata/status/results.

### Later Slices

- mTLS or WireGuard/HTTPS between Finja and orchestrator if this ever leaves the trusted LAN.
- File allowlists from Finja-side project scopes.
- Download/preview flow.
- More check runners per project type.
- Iterative model-repair loop with max rounds.
- Encrypted job archives.

---

## 📜 License

**MIT** (c) 2026 J. Apps — full text: repository root
[`LICENSE`](../LICENSE).

## Support & Contact

- Email: contact@jappshome.de
- Website: https://jappshome.de
- Support: https://buymeacoffee.com/J.Apps

Made with ❤️ by Sodakiller1 (J. Apps / JohnV2002)
