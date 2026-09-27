<!-- Loaded on demand for one domain. Shared guidance that applies to every
domain (existing-platform check, build vs buy) lives in SKILL.md. -->

# Payments, subscriptions and billing

**Landscape.** Direct processors (Stripe, Braintree, Adyen, Square, Razorpay);
merchants of record that handle sales tax and VAT for you (Paddle, Lemon Squeezy,
FastSpring); billing layers on top of a processor (Chargebee, Recurly, Orb,
Metronome, Lago); regional processors, which matter more than global comparisons
suggest depending on where customers are.

**What usually decides it.**
- **Merchant of record or not.** This is the first fork and dominates everything
  else. An MoR handles global sales tax, VAT and remittance in exchange for a
  higher rate and less control. For a small team selling internationally, offloading
  tax compliance is often worth more than the rate difference. Establish this
  before comparing features.
- **Fees at the actual price point.** Compare cost per transaction at the
  product's real price, not headline percentages. Fixed per-transaction fees
  dominate at low prices: on a 10/month plan, 5% + 0.50 is 1.00 (10%) against
  0.64 for 2.9% + 0.30 plus 0.5% tax add-on - a premium of ~56%, not "2%". State
  the per-payment and per-year difference with the arithmetic shown.
- **Billing model.** Flat-rate subscriptions are easy everywhere. Usage-based,
  seat-based with proration, hybrid, or complex metering separates the field fast.
- **Payout geography and supported methods.** Where the business is incorporated
  and how customers pay (cards vs SEPA vs local methods) rules options in or out.
- **Existing platform.** If the repo already uses a platform with billing built in,
  weigh integration savings seriously.

**Hidden requirements - this is where billing projects actually go.** A webhook
endpoint with signature verification; idempotent event handling, because providers
retry and events arrive out of order; subscription state mirrored locally so the
app doesn't call the API on every request; a reconciliation job for missed webhooks,
which *will* happen; the customer-to-user mapping; proration, upgrade/downgrade and
cancellation flows; dunning for failed payments; invoice and receipt access;
refunds; a test-mode path in CI.

Whatever the effort estimate for "add payments", the webhook and state-machine work
is usually larger than the SDK integration. Say so explicitly.

**Serverless caution.** Webhook handlers are fine on serverless, but the
reconciliation job and dunning retries need scheduling. If `analyze_stack.py`
reports serverless with no job runner, that gap belongs in the recommendation.

**EU VAT terminology.** VAT MOSS was replaced by OSS (One Stop Shop) on 1 July
2021; don't use the old name. OSS covers cross-border B2C sales to other EU states.
Sales to customers in the seller's own country pay domestic VAT through the normal
return, not OSS. B2B sales to VAT-registered EU businesses are generally reverse
charged. An MoR removes all three from the seller's plate; a direct processor with
a tax add-on calculates the tax but leaves registration and filing to the seller.

**Verify.** Percentage and fixed fees, payout schedules and country support, which
features are gated to higher tiers, tax-handling scope.
