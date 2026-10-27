# Metric Selection

Always consider lifecycle, meaningful operation outcome, duration, and existing
Error Contract events. Add specialized metrics only when detection or the changed
feature supports them:

| Signal | Useful metrics |
|---|---|
| Docker/service | CPU percent, memory bytes, restart count |
| Web/API | request count, outcome, duration by safe route template |
| Render/game loop | FPS and frame duration |
| Worker/queue | job outcome, duration, queue depth |
| Database | operation outcome and duration; never raw SQL |
| AI/model | request outcome and duration; never prompts by default |

Avoid high-cardinality tags such as user IDs, full URLs, arbitrary error text,
filenames outside structured Error Contract events, or dynamic query values.
Only the project's reviewed `privacy.allowed_tags` may be emitted; protocol 1.0
permits environment, version, component, operation, and outcome.

