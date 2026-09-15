<!-- Loaded on demand for one domain. Shared guidance that applies to every
domain (existing-platform check, build vs buy) lives in SKILL.md. -->

# Error tracking, logging and APM

**Landscape.** Error tracking (Sentry, Bugsnag, Rollbar); full-platform APM
(Datadog, New Relic, Honeycomb, Grafana Cloud); log platforms (Better Stack, Axiom,
Loki); host-provided basics (Vercel, Fly, Railway logs).

**What usually decides it.**
- **What actually breaks.** Application exceptions want error tracking; latency and
  resource questions want APM; they are different products and buying the wrong one
  is common. Start from the failure you can't currently diagnose.
- Volume-based pricing. Log and trace platforms bill on ingest, so a chatty
  application can produce a surprising bill. Sampling and retention policy are
  architectural decisions, not settings to leave at defaults.
- Whether the host already provides enough. For a small app, platform logs plus
  error tracking often cover everything, and a full APM is premature.
- OpenTelemetry support if vendor independence matters - instrumenting once against
  OTel keeps portability high.

**Hidden requirements.** Release and environment tagging, or errors can't be tied to
deploys. Source maps uploaded at build time, or stack traces are unreadable. PII
scrubbing before events leave the app. Alert routing to someone who will act -
alerts nobody owns get muted, and the tool then costs money and provides nothing.
Sampling to control cost.

**Portability.** High with OpenTelemetry instrumentation, low with vendor-specific
SDKs scattered through the code. This is a choice you make, not a vendor property.
