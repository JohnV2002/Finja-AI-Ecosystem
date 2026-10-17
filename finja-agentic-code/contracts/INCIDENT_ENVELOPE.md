# Finja → Flare: redacted incident envelope v1

This is the Phase C data contract for reporting one Finja error to Flare. Here
**redacted** means privacy-minimized, not merely a revised schema. The
authoritative model and validator are in `core/incident_envelope.py`. A frozen
JSON Schema lives in `contracts/incident-envelope-v1.schema.json` and is
checked against the model in CI. Regenerate or inspect it with:

```bash
python -c "import json; from core.incident_envelope import IncidentEnvelope; print(json.dumps(IncidentEnvelope.model_json_schema(), indent=2))"
```

The Pydantic schema describes the wire shape. The validator additionally
checks UTC timestamps, relative paths, source hashes, bundle size and obvious
privacy leaks. A sender must satisfy **both**. This is not the existing
AES-GCM transport envelope: encryption protects data in transit and at rest;
redaction limits what data is sent in the first place.

## Example

```json
{
  "envelope_version": 1,
  "incident_id": "123e4567-e89b-42d3-a456-426614174000",
  "observed_at": "2026-10-17T15:00:00Z",
  "origin": "finja",
  "component": "finja-chat",
  "repository": "finja-neural-network",
  "mode": "standard",
  "error_kind": "SyntaxError",
  "error_code": null,
  "summary": "A submitted module failed Python syntax checking.",
  "frames": [{"path": "demo.py", "line": 1, "symbol": "run"}],
  "files": [{
    "path": "demo.py",
    "content": "x = 1\n",
    "sha256": "9e26bf369911c45c243c684147b23fc9e1dcfcf257d299a1c632016a6fcd33f4"
  }],
  "redaction": {
    "policy": "finja-flare-redaction-v1",
    "source_minimized": true,
    "sensitive_values_removed": true
  }
}
```

`incident_id` is a stable UUIDv4 for this logical incident. `observed_at` is
UTC RFC3339 with `Z`. `component` and `repository` are logical identifiers,
never hostnames or filesystem paths. `mode` is one of `standard`, `hotfix` or
`manual`; it is a routing hint, not permission to bypass L5. `error_kind` is a
short technical class name; `error_code` is an optional structured code.
`summary` is a short, redacted observation, **not** raw user input or model
instructions. `frames` hold at most eight relative source locations, never a
raw traceback. `files` hold one to five explicitly chosen source files, each
at most 60,000 UTF-8 bytes and at most 120,000 UTF-8 bytes in total. Each
SHA-256 is computed over the UTF-8 content **after** redaction.
Paths under `private/`, `secrets/`, credentials, user-data, logs or backups
are refused even if their file extension looks like source code.

Unknown fields and unsupported envelope versions are rejected with
`FLARE-610`. Obvious credentials, private keys, absolute host paths, private
LAN addresses, email addresses, long account IDs and credential-bearing URLs
are rejected with `FLARE-611`. These codes never echo the rejected value.

## Sender rules

1. Select only the relevant source files and repo-relative frames. Do not
   include raw logs, tracebacks, chat messages, diary/memory entries, env files,
   tokens or account data. There is deliberately no field for them.
2. Remove sensitive literals before computing file hashes. A literal such as
   `"<redacted>"` is permitted, but redaction may make code untestable; in
   that case send no automatic repair request and use human review.
3. Validate locally with `validate_incident_envelope()` before transmission.
   Flare must validate again on receipt. The boolean redaction attestation is
   required but never treated as proof by itself.
4. Treat `summary` and source content as untrusted data. A future job adapter
   must not promote text from an error message into privileged instructions.

Pattern checks cannot prove arbitrary source is free of personal data or
novel secret formats. When redaction is uncertain, do not send the envelope.

## Evolution and current boundary

`sha256` is the digest of the UTF-8 content as transmitted. If the sender
redacted first, it identifies the redacted copy; a hash of the unredacted
original is not something Flare can know, so the sender keeps that one itself,
keyed by `incident_id`, to check for drift before applying anything. Since
#73 the `POST /incidents` answer also carries a `source` block saying how
much of the bundle no stack frame points at; it informs and never refuses.
Results Flare hands back name the bytes they are about with a per-file
manifest (see the README), and its `base_sha256` for a file is the digest
this envelope declared for it.

Version 1 is strict: adding, renaming or reinterpreting fields requires an
explicit v2 contract. Carrying an excerpt of a file instead of the whole file
is such a change; it would also need a `start_line`, because a diff made
against an excerpt has hunk numbers that do not match the real file. Finja-side emission is **not** part of this repository,
and the existing generic `/jobs` API must not be mistaken for a redacted
incident intake.

Since #71, Flare has one incident endpoint: `POST /incidents`. It validates
the envelope with this contract (`FLARE-610` → HTTP 400, `FLARE-611` → HTTP
422), counts the sighting, and answers with a routing **decision**: observe,
operator, classify, repair, manual or tracked. It is a dry run in the sense
that matters: **it creates no job**, stages nothing, runs no worker and
calls no model. Turning a `classify` or `repair` decision into a job is a
separate step that must map the envelope without turning incident
observations into model instructions. The decision itself repeats none of
the envelope's text.

Recurrence is counted per fingerprint of `component`, `error_code`,
`error_kind` and the top frame (path and symbol, never the line). It is not
counted per `incident_id`, so a sender that mints a fresh id for every
occurrence still gets its recurrences recognised. Each occurrence should
therefore be sent; a sender that samples will under-count.

What is counted is **episodes**: an error that fires repeatedly inside one
short slot (`INCIDENT_EPISODE_SECONDS`, one minute) is one episode seen
several times, so a retry storm does not escalate itself. The answer also
carries a `notify` block saying whether a person should be told, with its own
cooldown. Envelope v1 has no `dedupe_key` and cannot get one without a v2
contract; the fingerprint takes that role. The incident endpoint is
rate-limited (`FLARE-613`, `Retry-After`) with a wider budget than jobs.
