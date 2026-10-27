# Analytics Contract Protocol 1.0

Every event uses the versioned envelope in `schemas/event.schema.json`. Projects
send batches of up to 100 events to `POST /v1/events`. The collector exposes
structured metric queries at `POST /v1/query`; a later AI adapter translates
human questions into those deterministic queries.

Contract releases, event schemas, and HTTP APIs are versioned independently:

- Package/Contract SemVer describes this tool and its rules.
- `schema_version` describes the event envelope.
- `/v1` and `api_major` describe the collector API.

A patch release may tighten validation without renaming `/v1`. In event schema
1.0, unknown top-level and error fields are rejected. Reviewed additions use the
bounded `extensions` object with `x_` keys. Breaking envelope changes require a
new event schema and, where transport compatibility breaks, a new API major.
Collectors advertise supported event schema versions through `/v1/health`.

Minimum envelope fields:

```json
{
  "schema_version": "1.0",
  "event_id": "delivery-occurrence-id",
  "timestamp": "2026-10-20T12:00:00Z",
  "project_id": "finja-chat",
  "module": "twitch-auth",
  "event_name": "token.refresh",
  "kind": "timing",
  "outcome": "success",
  "duration_ms": 381,
  "tags": {"environment": "production"}
}
```

An Error Contract event adds:

```json
{
  "kind": "error",
  "outcome": "failure",
  "error": {
    "code": "FINJA-406",
    "fingerprint": "finja-406-token-refresh",
    "affected_file": "auth/token_refresh.py",
    "line": 84
  }
}
```

`affected_file` is always relative to the project root. Source contents and stack
traces are not part of protocol 1.0. A retry keeps the same `event_id`, allowing
collector idempotency. A genuinely new occurrence gets a fresh `event_id` while
the stable privacy-safe `error.fingerprint` groups equivalent failures.

