# Impact analysis

Turning `impact_scan.py` output into something a developer can act on. The scanner
finds candidate files and checks infrastructure; it cannot tell you what the schema
should look like or what order to do the work in. That's this step.

The goal is a section the developer reads and thinks *"yes, that's my codebase"*.
Specificity is the whole point: "around a dozen files" could describe any project,
while "`prisma/schema.prisma` needs a Subscription model and
`app/api/webhooks/stripe/route.ts` doesn't exist yet" could only describe theirs.

## 1. Convert touchpoints into named changes

For each role the scan reports, say what changes and why. Read the files before
describing them - the scanner matches patterns, and patterns produce false
positives. A file listed under "entitlement checks" because it contains the word
`isPro` may be an unrelated stub.

Group by intent rather than listing paths:

> **Data model** - `prisma/schema.prisma`: add `Subscription` (userId, providerCustomerId,
> providerSubscriptionId, status, currentPeriodEnd, priceId) and a relation from `User`.
>
> **Session** - `lib/session.ts`: the session currently carries only user identity;
> plan status needs to be available wherever access is checked, either on the session
> or via a cached lookup.
>
> **New surface** - `app/api/webhooks/stripe/route.ts`: does not exist. Needs raw-body
> access for signature verification, which differs from the JSON body parsing used by
> the existing routes in `app/api/`.

When the feature decides who gets access (billing, plans, auth, quotas), give work
outside the request path its own group. Routes are where access is checked;
workers, cron jobs and queue consumers are where money is spent:

> **Background work** - `server/monitor/rules.ts`: polls a third-party API on a
> schedule for every user with rules configured. Nothing here checks subscription
> status, so a user who cancels loses the dashboard but keeps costing API calls.
> Skip users without an active subscription, and stop their schedules when the
> `customer.subscription.deleted` webhook arrives.

That group becomes its own item in the integration plan, placed before rollout.

Note things that *don't* need to change too, when a developer might reasonably fear
they do. "Your existing auth stays as-is; the provider's customer record links by
user ID" prevents an imagined rewrite.

## 2. Schema changes

State tables, columns and their purpose - not just "a subscriptions table". Include:

- **Foreign keys** to existing entities, with the exact existing table named.
- **Uniqueness and indexes** driven by lookup patterns, especially the
  provider-ID-to-local-record lookup that every webhook handler performs on every
  event. This one is routinely forgotten and causes the first production slowdown.
- **Nullability** during rollout: new columns on existing tables usually need to be
  nullable initially, backfilled, then constrained.
- **Migration mechanism** matching the repo's tooling. If `impact_scan.py` reports
  no migration tooling, that gap is part of this work.

Write the migration in the repo's own idiom when it's short enough to be useful -
a Prisma model block, a Django migration, an Alembic revision.

## 3. Dependencies

List packages with the reason each is needed, and flag anything that isn't obvious:

- Native or binary dependencies that affect the build or container image.
- Packages needing a specific runtime version - check against `engines` or the
  language version in the manifest.
- Client-side SDKs and their bundle-size cost.
- Peer dependency conflicts with what's installed. If a version conflict is likely,
  say so rather than letting the developer find out at install time.

## 4. Environment and secrets

Name each variable, what it's for, and where it has to exist. Compare against the
env keys the scan found so the diff is explicit.

| Variable | Purpose | Needed in |
|---|---|---|
| `STRIPE_SECRET_KEY` | Server-side API calls | server runtime, CI (test key) |
| `STRIPE_WEBHOOK_SECRET` | Verify webhook signatures | server runtime |
| `NEXT_PUBLIC_STRIPE_KEY` | Client-side checkout | client bundle - publishable only |

Two points worth stating explicitly, because both cause real incidents: which keys
are publishable versus secret (anything client-side is public, whatever the name
suggests), and that test and live credentials are different sets requiring separate
handling in CI and preview environments.

If the repo has an env template, updating it is part of the work.

## 5. Missing infrastructure

Where the scan reports a gap, price it as its own piece of work rather than
folding it into the integration. These are the line items that make estimates
credible:

- **No webhook surface** - a new endpoint, raw-body handling, signature verification,
  and a way to replay events during development (tunnel or CLI forwarding).
- **No job runner** - anything needing retries, scheduled reconciliation or
  fan-out. On serverless this means choosing a hosted job service or cloud
  scheduler, which is a second vendor decision inside the first.
- **No migration tooling** - adopt it now or apply schema changes by hand, which
  doesn't survive a second environment.
- **No tests** - for stateful integrations, recommend at least covering the
  webhook handler and the state transitions, since those fail silently in
  production and are tedious to debug after the fact.

## 6. Ordering the work

Order phases so each ends somewhere shippable. A plan that only works once every
step is finished gives the developer no way to stop, review, or hand off.

A reliable shape for most integrations:

1. **Foundations** - dependency installed, credentials wired, connectivity proven
   with one trivial call. Ends with evidence the account and keys work, which
   surfaces access problems before any code depends on them.
2. **Data model** - schema and migration applied, no behaviour yet. Reversible.
3. **Core path** - the main flow end to end, happy path only, behind a flag or
   restricted to test mode.
4. **Edge and failure handling** - webhooks, retries, idempotency, error states.
   Usually the largest phase; if it looks small, something has been missed.
5. **Rollout** - production credentials, monitoring, gradual enablement, and the
   reconciliation job that catches what the webhooks dropped.

For each phase give the rough effort, what "done" means, and how to verify it.
Verification should be concrete: "trigger a test webhook with the provider CLI and
confirm the subscription row updates", not "test the integration".

## 7. Risks

Name risks specific to this repo and this choice, with a mitigation for each.
Generic risk lists are ignorable; the useful ones come from what the analysis
actually found.

Worth checking every time: what happens if a webhook is missed or arrives out of
order; what the user sees when the provider is down; whether a failed payment or
expired token silently revokes access; whether the local development path works
without production credentials; and what the rollback looks like once real data
exists in the provider's system, which is usually harder than the rollout.

## Calibrating effort

The scanner's band assumes a developer already familiar with the codebase, working
without interruption, and counts surface area rather than product complexity.
Adjust it - and say what you adjusted - when:

- **Unfamiliar codebase or team member** - roughly double for onboarding.
- **The feature is product-complex** - tiered plans with proration and trials is
  several times the work of a single subscription price, and no file scan can see
  that difference.
- **Coordination is needed** - design, copy, legal review, procurement. Often the
  real schedule driver, and invisible to any code analysis.
- **The repo is in poor shape** - no tests, tangled state, inconsistent patterns.
  Integration work inherits that.

Give a range, say what it assumes, and never present a single number. A single
number will be quoted to a stakeholder as a commitment.
