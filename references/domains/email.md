<!-- Loaded on demand for one domain. Shared guidance that applies to every
domain (existing-platform check, build vs buy) lives in SKILL.md. -->

# Transactional email

**Landscape.** API-first (Resend, Postmark, SendGrid, Mailgun, Amazon SES,
Loops); SMTP relays, which anything can use.

**What usually decides it.**
- Transactional versus marketing. Providers optimise for one; mixing them on a
  single domain reputation is a deliverability mistake.
- Deliverability reputation - the main thing you're buying. Cheapest-per-email is
  a poor optimisation if receipts land in spam.
- Templating approach: provider-hosted templates versus templates in your repo.
  In-repo templates version and review with the code, which most teams prefer.
- SES is dramatically cheaper at volume and meaningfully more setup and operational
  work; that trade is usually the decision when volume is high.

**Hidden requirements.** SPF, DKIM and DMARC configuration on the sending domain -
the part that actually determines success; a separate subdomain for sending;
bounce and complaint handling (required, not optional, at volume); unsubscribe
handling where applicable; a local development path that doesn't send real mail;
idempotency so a retry doesn't send twice.

**Portability is high** if you send through an abstraction; near-total lock-in if
templates live in the provider's dashboard. That's a design choice you can advise
on rather than a fixed property of the vendor.

**Verify.** Volume tiers, dedicated IP requirements, region support.
