# Adapter Acceptance Requirements

Every language-native Analytics Contract adapter must prove these behaviors.

## Disabled and offline behavior

- With `analytics.enabled=false`, the adapter performs no endpoint discovery,
  queue allocation, timer setup, worker-thread startup, or network activity.
- With analytics enabled but the collector unavailable, application behavior,
  output, and exit status remain unchanged.
- The adapter uses short timeouts, a bounded queue, and no synchronous retry loop.
  Queue overflow follows the configured drop policy without blocking the app.

## Privacy and validation

- The producer validates the complete event before enqueueing or transport.
- Invalid or unsafe events never enter the queue and never reach the network.
- The collector runs the same event and tag validation before persistence.
- Neither side accepts source, stack traces, prompts, secrets, personal data,
  absolute paths, raw SQL, or unreviewed high-cardinality tags.

## Delivery identity

- A retry of one delivery keeps its original `event_id`.
- The collector deduplicates repeated delivery of that ID.
- Separate occurrences use separate event IDs, even when they share the same
  privacy-safe `error.fingerprint`; each occurrence remains countable.

## Integration

- Configuration follows the host project's native configuration system.
- Startup and shutdown follow the host runtime's lifecycle conventions.
- Adapter failures never enter Error Contract reporting recursively.
