---
name: stackfit
description: Recommends third-party services, APIs and SDKs for the specific repository in front of you rather than in the abstract. Reads the codebase's frameworks, data layer, deployment target and existing vendors, measures SDK health and finds real implementations on GitHub, scores candidates on a weighted rubric, and reports blast radius, effort, risks and an integration plan. Use this whenever someone asks which service, provider, SDK or API to use for a feature - auth, payments, subscriptions, billing, file storage, email, push notifications, search, analytics, realtime, queues, vector or AI infrastructure - or asks to compare providers ("Stripe vs Paddle", "is Clerk worth it"), asks "what should I use for X", weighs build versus buy, asks what switching providers would cost, or wants an Architecture Decision Record for a technology choice. Use it even when the request sounds casual, like "how should I add billing to this app".
license: MIT
---

# StackFit

Developers rarely need to know the best payments API in general. They need to know
what to do in the repository open in front of them, given what it already uses,
where it deploys, and how much time they have. Generic advice is free everywhere;
the value here is entirely in the specificity.

So the order is fixed: **read the repo, then form an opinion.** An opinion formed
first and justified afterwards is a guess, and a scoring table wrapped around a
guess just makes it look rigorous.

## Three failure modes to design against

1. **Generic recommendation** - would read identically for a different codebase.
   Fix: every claim traces to a path, a dependency, or a measured fact.
2. **False precision** - a score of 87.3, a price recalled from training data.
   Fix: verify volatile facts or label them unverified.
3. **Ignoring hidden work** - the SDK call is ten lines; the webhook endpoint,
   idempotency, reconciliation job and migration are the actual project.

## Workflow

Script paths below are relative to this skill's directory; the repository being
analysed is the argument. The working directory is normally the developer's
project, so use the skill's own path for the script and `.` for the target.
Substitute the real path for `$SKILL_DIR`.

### 1. Match depth to the question

- **Quick call** ("which email API?", "is Clerk overkill?") - analyse the stack,
  answer in a few paragraphs with one runner-up. No scoring table.
- **Full evaluation** ("help me pick a payments provider") - the whole workflow.
- **Migration** ("Firebase to Supabase, how bad?") - read
  `references/migration-analysis.md` instead; the effort profile is different.

Ask a question only when the answer changes the ranking. "Seat-based or usage-based
billing?" changes the winner; "what's your timeline?" usually doesn't and can be
inferred from the repo. Never open with a questionnaire.

### 2. Read the repository

```bash
python3 "$SKILL_DIR/scripts/analyze_stack.py" . --format text
```

Deterministic, offline, never reads real `.env` files. In a monorepo, target the
specific package - a root scan mixes stacks and produces a muddled picture.

Then **confirm by opening actual files.** The analyzer sees that Prisma is
installed; it cannot see that it's used in one file and raw SQL everywhere else, or
that the "auth" in the manifest is a half-finished prototype. Two well-chosen files
change recommendations more than any amount of dependency listing.

Four findings eliminate candidates outright:

- **Runtime model.** Serverless and edge hosts cannot run persistent workers or
  hold websockets. Options assuming a long-lived process are disqualified, not
  merely penalised.
- **Existing vendors.** A platform already in the stack starts ahead - one fewer
  vendor, bill, SDK and auth model.
- **Data layer.** Decides how painful new tables are and whether a provider's
  schema expectations fit.
- **Webhook and job capability.** Missing infrastructure is usually the largest
  cost line in the whole integration.

### 3. Frame the decision

Name the two or three things that actually decide this case - usually the runtime
constraint, the existing vendor, and one product requirement (global payouts,
HIPAA, self-hosting, EU residency). A hard requirement is a filter, not a criterion:
options failing it get excluded with a reason, not scored 2/5.

### 4. Shortlist

Three to five candidates. More means the research wasn't narrowed, and a long
undifferentiated list hands the decision back to the developer.

Always weigh two options that get forgotten:

- **The vendor already in the stack.** Before recommending a specialist for auth,
  storage, search or realtime, check whether the platform already present handles
  it adequately. Often it does. When the specialist is genuinely better, say what
  specifically is better - "more powerful" is not a reason to add a vendor.
- **Building it.** Build when the problem is bounded and the operational surface is
  small: presigned S3 uploads, Postgres full-text search, a notifications table,
  flags in a config table. Buy when it hides a state machine or a compliance
  surface: billing, auth, deliverability, payments. The test isn't difficulty, it's
  how many edge cases carry real consequences when handled wrong.

Read `references/domains/<domain>.md` for that domain's landscape, deciding factors
and hidden requirements. Playbooks exist for `auth`, `payments`, `storage`, `email`,
`sms`, `notifications`, `search`, `analytics`, `realtime`, `ai`, `jobs`, `database`,
`cms`, `feature-flags` and `observability`.

**This skill is not limited to those.** The workflow applies to any feature a
developer wants to add - e-signature, maps, video, i18n, PDF generation, anything.
When no playbook exists, derive the same four things yourself before shortlisting:
what the realistic candidates are, which one or two factors actually decide it, what
the domain quietly drags in (new infrastructure, a schema change, a compliance
surface, an ongoing sync obligation), and which facts are volatile enough to need
verifying. Say plainly that you worked without a playbook, so the developer knows
the landscape came from reasoning rather than a curated list.

### 5. Measure what can be measured

```bash
python3 "$SKILL_DIR/scripts/github_probe.py" probe stripe @paddle/paddle-js
python3 "$SKILL_DIR/scripts/github_probe.py" find "nextjs stripe subscription" --language TypeScript
```

`probe` turns `sdk_quality` and `ecosystem_maturity` into measurements: whether the
package is deprecated, when it was last published, whether the repo is archived, how
recently it was pushed. A deprecated or archived SDK is decisive and easy to miss
from memory. `find` surfaces real implementations worth reading for integration
patterns - examples, not endorsements, since popular starter repos are often
outdated or built for a different stack.

The probe reads package registries first and treats GitHub as enrichment, because
the GitHub API allows 60 requests/hour unauthenticated and shared IPs exhaust that
fast. Set `GITHUB_TOKEN`, or have `gh` logged in, for 5000/hour. When the quota is
gone it returns registry data and says so - carry that limitation into the report
rather than presenting partial data as complete.

Stars measure popularity, not maintenance or fit. An official vendor SDK with 400
stars is often better maintained than a community wrapper with 4000.

### 6. Verify anything that moves

Architecture facts are stable (Stripe is webhook-driven; Postgres has full-text
search). Pricing, free-tier limits, rate limits, SDK versions and regional
availability are volatile.

For volatile facts: fetch the vendor page and cite it, or label the claim -
*"roughly 2.9% + 30c per training data, verify before committing."* An unlabelled
stale price is worse than none, because it gets budgeted against. If web access
isn't available, say so once and label everything volatile.

### 7. Score

Build a candidates file (`score_candidates.py --template`) using the anchored
definitions in `references/scoring-rubric.md` - anchors are what make two runs
agree. All ten criteria are oriented so 5 is favourable, so cost, effort and
lock-in are scored as `cost_efficiency`, `implementation_speed`, `portability`.

```bash
python3 "$SKILL_DIR/scripts/score_candidates.py" /tmp/candidates.json --profile default --format markdown
```

Profiles: `default`, `ship-fast`, `cost-sensitive`, `enterprise`, `long-haul`. Use
what the developer signalled; otherwise `default`, and name the profile, since the
weighting is an assumption they can override.

Three checks keep the answer honest. Carry their results into the report rather
than quietly dropping them:

- **Margin** under five points is a tie. Say so and give a concrete tiebreaker.
- **Sensitivity** - if the winner changes under other profiles, state the
  condition: "Stripe if flexibility matters more, Paddle if you don't want to
  handle sales tax."
- **Evidence audit** - scores with no reason, facts never verified. Fix, don't ship.

If the scoring contradicts your instinct, work out which is wrong. Never adjust
scores so a preferred option wins; change the recommendation instead, or admit the
criteria don't capture what matters here.

### 8. Work out what it touches

```bash
python3 "$SKILL_DIR/scripts/impact_scan.py" . --domain payments   # --list-domains
python3 "$SKILL_DIR/scripts/impact_scan.py" . --domain "e-signature for contracts"
```

The domain argument takes free text and resolves it, so a feature description works
as well as a keyword. Anything unrecognised falls back to a generic integration
profile rather than failing - it still finds credential handling, existing API
clients, config and data models, which is most of what any integration touches.

Reports touchpoint files by role, infrastructure readiness, and an effort band with
its inputs shown. Treat the band as a floor for someone who already knows the
codebase. Turn it into specifics with `references/impact-analysis.md`: schema,
dependencies, env vars, ordered phases. "Roughly twelve files" is weak;
"`prisma/schema.prisma` needs a Subscription model and
`app/api/webhooks/stripe/route.ts` doesn't exist yet" is what makes it credible.

## Report structure

Full evaluations use `assets/report-template.md`. Sections, in order: recommendation
and headline numbers; detected stack; options table with margin and sensitivity; why
the winner over the runner-up; what it touches; integration plan; risks including
lock-in; what would change this recommendation.

That last section is the most useful one a year later - it tells the team when to
revisit rather than re-litigating from scratch. Drop any section that would be
padding for the question asked.

## Output economy

Developers read this output; every wasted line costs them attention and costs the
recommendation clarity. Aim for density, not brevity for its own sake.

- **Lead with the decision.** No preamble, no restating the question. The first
  line is the answer.
- **Don't narrate the process.** Show findings, not "I ran the analyzer, then
  searched GitHub". Tool output is evidence, not content to summarise.
- **Never state a fact twice.** If it's in the stack table, don't repeat it in prose.
- **Tables for comparison, prose for reasoning.** Prose listing parallel attributes
  should have been a table.
- **Cut any sentence true of any repo.** Generic vendor praise, boilerplate caveats
  and restatements of what the developer just told you are the main waffle sources.
- **No closing summary.** The recommendation was the first line; repeating it adds
  nothing.
- Rough budgets: quick call under 250 words, full report under 900. Exceeding them
  is fine when the content is dense - but check that it is.

## Judgment rules

**Ground every claim** in a path, dependency, measurement, fetched source, or a
labelled assumption.

**Recommend one thing.** Present the ranking, commit to an answer. Declare genuine
ties, then give the tiebreaker.

**Respect what works.** Suggesting a rewrite of functional code because another
provider scores marginally higher is bad advice; migration cost lands on people who
did nothing wrong.

**Name the lock-in.** What leaving costs: which data is portable, which code is
provider-shaped, roughly how long an exit takes. Developers can accept lock-in
knowingly; they shouldn't discover it later.

**Numbers carry their basis.** Effort bands say who they assume. Prices carry a
source or a label. Scores carry evidence.

## Anti-patterns

Recommending before reading the repo. Eight options with no ranking. Pricing from
memory stated as current. An architecture the deployment target can't run - a
persistent worker on Vercel, a websocket server on static hosting. Ignoring a vendor
already in the manifest. Scoring everything 4/5 so nothing separates. Treating the
weighted score as the decision rather than as shown reasoning.

## Follow-ups

Offer at most one, when it fits: an **ADR** (`references/adr-template.md`) after a
decision; **migration analysis** for "should we move from X to Y"; or starting
**phase one** of the integration plan.

## Files

| Path | Read when |
|---|---|
| `references/scoring-rubric.md` | Before scoring - anchored 0-5 definitions |
| `references/domains/<domain>.md` | While shortlisting, for that domain only |
| `references/impact-analysis.md` | Turning scan output into a plan |
| `references/migration-analysis.md` | Provider-to-provider migrations |
| `references/adr-template.md` | Writing an ADR |
| `assets/report-template.md` | Writing a full report |

| Script | Purpose |
|---|---|
| `analyze_stack.py` | Stack, vendors, deployment, capabilities, constraints |
| `github_probe.py` | SDK health from registries and GitHub; find real integrations |
| `score_candidates.py` | Weighted scoring, margin, sensitivity, evidence audit |
| `impact_scan.py` | Touchpoints, infrastructure readiness, effort band |

All are standard-library Python 3.8+ and read-only. The first, third and fourth are
offline and deterministic; `github_probe.py` is the only one making network calls,
and degrades to partial results rather than failing. Run `--help` on any of them. If
a script fails, read the repo directly and say so - the logic matters more than the
tooling.
