<!-- Loaded on demand for one domain. Shared guidance that applies to every
domain (existing-platform check, build vs buy) lives in SKILL.md. -->

# Product analytics

**Landscape.** Product analytics (PostHog, Mixpanel, Amplitude); customer data
platforms that route events elsewhere (Segment, RudderStack); privacy-focused web
analytics (Plausible, Fathom); warehouse-native approaches.

**What usually decides it.**
- Privacy and regulatory posture. EU data residency, consent requirements and
  cookie policy frequently decide this before features do.
- Whether the team will actually use it. An expensive tool nobody opens is worse
  than a simple one someone checks weekly.
- Self-hosting need - only a few options support it.
- Bundled features (session replay, feature flags, experiments) can replace
  another vendor, which is a real saving worth surfacing.

**Hidden requirements.** A consistent event naming scheme decided up front, because
renaming events later breaks historical analysis; identity stitching between
anonymous and logged-in users; consent gating; a server-side path for events that
ad blockers would drop client-side; bundle-size impact of client SDKs.
