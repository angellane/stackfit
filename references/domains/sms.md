<!-- Loaded on demand for one domain. Shared guidance that applies to every
domain (existing-platform check, build vs buy) lives in SKILL.md. -->

# SMS and voice

**Landscape.** Programmable messaging (Twilio, Vonage, MessageBird, Plivo,
Telnyx, Amazon SNS/Pinpoint); verification-specific (Twilio Verify, Firebase Phone
Auth); regional providers, which matter a great deal for deliverability and price.

**What usually decides it.**
- **Destination countries.** Coverage, per-message price and regulatory rules vary
  enormously by country, and a global comparison is close to meaningless without
  knowing where messages go. This is usually the whole decision.
- Use case: one-time passcodes, alerts, or two-way conversation. Verification APIs
  handle code generation, expiry and retry so you don't reimplement them.
- Sender identity requirements - alphanumeric sender IDs, short codes, 10DLC
  registration in the US - which carry lead time measured in weeks, not days.

**Hidden requirements.** Phone number validation and E.164 normalisation before
storage. Opt-out handling, which is a legal requirement in most jurisdictions.
Delivery status callbacks, so a webhook endpoint. Rate limiting to contain both
cost and abuse - SMS is the classic target for toll fraud, and an unprotected
verification endpoint can generate a very large bill quickly. A development path
that doesn't send real messages.

**Cost shape.** Per-message with wide geographic variance, so model against actual
destination mix rather than a headline rate.
