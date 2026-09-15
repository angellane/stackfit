<!-- Loaded on demand for one domain. Shared guidance that applies to every
domain (existing-platform check, build vs buy) lives in SKILL.md. -->

# Background jobs and queues

**Landscape.** Language-native with a broker (Celery, Sidekiq, BullMQ, RQ,
Dramatiq - usually Redis or RabbitMQ); database-backed (Graphile Worker,
Solid Queue, `pg-boss`); serverless-friendly hosted (Inngest, Trigger.dev, QStash,
Defer); cloud primitives (SQS + Lambda, Cloud Tasks, EventBridge); durable
execution (Temporal, Restate).

**What usually decides it.**
- Runtime model again. A serverless app cannot run a persistent worker; it needs
  either a hosted job service or a cloud primitive with a scheduler.
- Whether Redis is already present - if so, the native library is usually the
  shortest path.
- Durability requirements. Long multi-step workflows that must survive restarts
  are what durable execution engines exist for; using one for "send an email
  asynchronously" is overkill.

**Hidden requirements.** Retry and backoff policy; dead-letter handling and
someone looking at it; idempotent job bodies, since at-least-once delivery means
jobs will run twice; visibility into failures; local development story; graceful
shutdown mid-job.
