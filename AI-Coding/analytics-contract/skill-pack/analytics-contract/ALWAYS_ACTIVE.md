# Analytics Contract — ALWAYS ACTIVE

When creating or substantially changing runtime code, resolve Analytics Contract
alongside Error Contract:

```text
analytics-contract detect .
analytics-contract init .      # only when analytics_contract.json is missing
analytics-contract plan .
```

- Default is `analytics.enabled=false`.
- The application must always run without an analytics backend. Disabled means
  zero discovery, queues, timers, background workers, and network calls.
- Add only relevant instrumentation for the detected project and changed feature.
- Validate before enqueue or transport; the collector validates again.
- Error metrics reuse Error Contract events and include only structured error code,
  privacy-safe fingerprint, project-relative affected file, and optional line.
- Retries reuse `event_id`; separate occurrences use fresh IDs even when their
  `error.fingerprint` is identical.
- Never send source, stack traces, prompts, secrets, personal data, absolute paths,
  or raw SQL by default.
- Endpoint and authentication are runtime configuration, never committed values.
- There is no legacy-debt baseline: the contract is the target state. Migrate old
  code deliberately; make new and changed code compliant immediately.

