# Architecture Decision Records

An ADR is a short document recording one significant technical decision: what was
decided, why, what else was considered, and what it commits the team to. The
audience is a developer eighteen months from now asking "why is this in our stack,
and can we change it?"

Offer one after a recommendation is accepted. The evaluation already produced
everything an ADR needs, so it costs almost nothing to write and answers a question
that otherwise gets re-litigated from scratch.

## Conventions

- File `docs/adr/NNNN-short-title.md`, numbered sequentially, kebab-case title.
  Match the repo's existing convention if there is one - check for a `docs/adr`,
  `docs/decisions` or `architecture/` directory first.
- One decision per record.
- Immutable once accepted. A later decision supersedes it with a new record rather
  than editing history; the superseded record gets a status line pointing forward.
- Short. One page. If it runs longer, the detail belongs in the linked evaluation.

## Template

```markdown
# NNNN. {Decision in a short imperative phrase}

- **Status:** Accepted
- **Date:** YYYY-MM-DD
- **Deciders:** {names or team}
- **Supersedes / Superseded by:** {ADR reference, or omit}

## Context

What made a decision necessary: the requirement, the constraints that narrowed the
field, and the relevant state of the system at the time. Include the facts that
were true when deciding - stack, scale, team size, deployment model - because those
are what a future reader needs to judge whether the reasoning still holds.

Keep this factual. No advocacy yet.

## Decision

What was chosen, stated plainly in one or two sentences.

## Rationale

Why this option, tied to the context above. Three to five points. Each should be a
reason that would actually change if the context changed - not generic praise of
the vendor.

## Alternatives considered

For each serious alternative: what it was, and the specific reason it lost. One or
two sentences each.

Include options rejected on hard requirements, with the requirement named. Recording
that an option was considered and why it failed is the single most valuable part of
an ADR, because it stops the same suggestion being re-raised every six months.

## Consequences

**Accepted costs.** Recurring spend, operational surface, new failure modes, what
the team now has to know.

**Lock-in.** What leaving would cost: which data is portable, which code is
provider-shaped, rough time to exit.

**Follow-on work.** What this decision now requires - infrastructure, monitoring,
runbooks.

## Revisit when

The conditions that should trigger reopening this: a scale threshold, a pricing
change, a requirement the current choice can't meet, a dependency becoming
unmaintained. Be specific enough to be checkable.
```

## Worked example

```markdown
# 0007. Use Stripe Billing for subscriptions

- **Status:** Accepted
- **Date:** 2026-03-14
- **Deciders:** Platform team

## Context

We need recurring subscriptions with monthly and annual tiers, self-serve upgrades
and downgrades, and proration. Customers are currently US and UK only, with EU
expansion likely within a year.

The application is Next.js 14 on Vercel, Postgres via Prisma, authentication
through Auth.js. Deployment is serverless: no persistent workers, and no job runner
is currently in place. Team is three engineers with no prior billing experience.

## Decision

Use Stripe Billing, with subscription state mirrored into our own `Subscription`
table and updated via webhooks.

## Rationale

- Serverless-compatible: webhook handlers fit our existing `app/api/` route
  structure, with no long-running process required.
- The Node SDK is typed and actively maintained, matching our TypeScript codebase.
- Proration and upgrade/downgrade flows are handled by the provider; building these
  ourselves was estimated at several weeks and is a frequent source of billing bugs.
- Our team's lack of billing experience makes documentation quality decisive, and
  Stripe's is the strongest of the options reviewed.

## Alternatives considered

- **Paddle** - merchant of record, which would remove our EU VAT obligation on
  expansion. Rejected for now because that obligation is hypothetical, the rate is
  higher, and we would hold less control over the checkout experience. This is the
  closest alternative and should be revisited before EU launch.
- **Lemon Squeezy** - similar MoR benefits, simpler API, but a smaller ecosystem and
  less headroom for the usage-based pricing on our roadmap.
- **Building on raw payment intents** - rejected: the subscription state machine,
  proration and dunning are the bulk of the work, and getting them wrong charges
  customers incorrectly.

## Consequences

**Accepted costs.** Per-transaction fees on all revenue. A webhook endpoint with
signature verification and idempotency handling. Subscription state duplicated
between Stripe and our database, which must be reconciled.

We have no job runner, so the reconciliation job for missed webhook events needs
Vercel Cron or a hosted job service - a follow-on decision this one creates.

**Lock-in.** Customer and subscription records export via API. Payment method
tokens do not transfer without a vendor-assisted migration taking several weeks.
Practical exit cost: moderate, and it rises with customer count.

**Follow-on work.** Reconciliation job; monitoring on webhook failures; dunning
flow for failed payments; test-mode fixtures in CI.

## Revisit when

- EU revenue becomes material and VAT handling costs more than the MoR rate premium.
- Usage-based pricing moves from roadmap to requirement.
- Payment processing fees exceed roughly 2% of revenue at a scale where negotiated
  rates or an alternative processor would be worth the migration.
```

## Notes on writing these well

The temptation is to write the ADR as a justification. Resist it. The record is
more useful when it admits what was uncertain, names the option that nearly won,
and states the conditions under which the decision would be wrong. A team reading
an honest ADR can act on it; a team reading marketing copy learns nothing and
re-runs the whole evaluation.
