<!-- Loaded on demand for one domain. Shared guidance that applies to every
domain (existing-platform check, build vs buy) lives in SKILL.md. -->

# Feature flags and experimentation

**Landscape.** Dedicated platforms (LaunchDarkly, Statsig, Flagsmith, Unleash,
ConfigCat); bundled into product analytics (PostHog, Amplitude); self-hosted
(Unleash, Flagsmith); or a config table in your own database.

**What usually decides it.**
- **Flags or experiments?** Simple on/off rollout is a config problem and a
  database table plus a cached read often solves it properly. Statistically valid
  A/B testing with metric pipelines is a different product, and building it is a
  bad trade.
- Client-side or server-side evaluation. Client-side means a network call or SDK
  bundle on page load and flag values visible to users; server-side keeps them
  private but needs evaluation at every entry point.
- Whether analytics already ships flags. If the repo already has PostHog or
  Amplitude, using their flags avoids a second vendor and gives flag-to-metric
  attribution for free.
- Who flips the flags. If non-engineers need to, a dashboard is the requirement.

**Hidden requirements.** A sane default when the flag service is unreachable, or an
outage takes the app with it. Local development without network dependence. Flag
cleanup discipline - stale flags become permanent dead branches and are the main
long-term cost. Consistent bucketing so a user doesn't flip between variants.
Latency budget if flags are evaluated on the request path.

**Portability** is usually high: flags are booleans behind your own helper. Keep
evaluation behind a thin interface and switching is cheap.
