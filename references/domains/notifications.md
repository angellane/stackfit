<!-- Loaded on demand for one domain. Shared guidance that applies to every
domain (existing-platform check, build vs buy) lives in SKILL.md. -->

# Notifications

**Landscape.** Push infrastructure (FCM, APNs, Expo for React Native, OneSignal);
multi-channel orchestration (Knock, Courier, Novu); in-app feeds (Knock,
Magicbell); realtime-platform features for in-app delivery.

**What usually decides it.**
- Channel count. One channel rarely justifies an orchestration layer; three or more
  channels with per-user preferences usually does.
- Whether users need preference control and digesting. Building preference
  matrices, quiet hours and batching is more work than it sounds.
- Mobile presence - native push means platform credentials and store requirements
  regardless of vendor.

**Hidden requirements.** Device token storage and lifecycle (tokens expire and
rotate); per-user, per-channel preference storage; a fan-out mechanism, which needs
a job runner; deduplication; deep links; and the product question of what a
notification should say, which is usually the actual bottleneck.
