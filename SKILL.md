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

Commands are written as `python3`. If that fails - on Windows it is often a Store
stub that prints nothing or opens a prompt - retry with `python`, then `py -3`,
and use whichever works for the rest of the session. Write scratch files such as
`candidates.json` to the system temp directory (`$TMPDIR`, `%TEMP%`), never `/tmp`
on Windows and never into the developer's repository. If a script still won't run,
say which one and why in the report; don't silently skip its output.

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

**Look for decisions already made.** Check `docs/decisions/`, `docs/adr/`,
`decisions/` and `architecture/` for a record covering this area. If one exists,
start from it: state what was decided and why, and reopen it only when one of its
"revisit when" conditions now holds or the developer asks to. Re-deriving a settled
choice from scratch can land on the other answer for no reason the team would accept.

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

### 5. Check every SDK is alive - before comparing anything

```bash
python3 "$SKILL_DIR/scripts/github_probe.py" probe stripe @paddle/paddle-js
python3 "$SKILL_DIR/scripts/github_probe.py" find "nextjs stripe subscription" --language TypeScript
```

This is the check most comparisons skip, and the one that causes the most rework:
a well-reasoned recommendation for a library that hasn't shipped a release in two
years. Recall can't answer it; the probe can. Run it on every shortlisted SDK,
including the vendor already in the stack, and on the one you recommend even in a
quick call.

Treat the status as a gate, not just a score input:

- **archived / deprecated** - excluded, with the status as the reason.
- **dormant** (no activity for two years) - excluded unless nothing better exists;
  if it survives, that is the headline risk, stated in the report's opening lines.
- **stale / slowing** - scored down, and named next to the option in the table.

If the winner's SDK is anything other than `active`, say so in the first lines of
the answer, not in the risks table. `find` surfaces real implementations worth
reading for integration patterns - examples, not endorsements, since popular
starter repos are often outdated or built for a different stack.

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
python3 "$SKILL_DIR/scripts/score_candidates.py" "$TMPDIR/candidates.json" --profile default --format markdown
```

Profiles: `default`, `ship-fast`, `cost-sensitive`, `enterprise`, `long-haul`. Use
what the developer signalled; otherwise `default`, and name the profile, since the
weighting is an assumption they can override.

Three checks keep the answer honest. Carry their results into the report rather
than quietly dropping them:

- **Margin** under five points is a tie. Say so and give a concrete tiebreaker.
  Always report the margin as the number the scorer printed ("12.4 points"),
  never as an adjective like "clear". If you describe the top two as
  interchangeable or near-identical, that is a tie whatever the number says -
  call it one. If scoring didn't run, write "not scored" and why, rather than
  asserting a margin you didn't measure.
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

**Look outside the request path.** When the feature decides who gets access -
billing, plans, auth, quotas - find the background workers, cron jobs and queued
tasks that do paid work per user: third-party API calls, LLM usage, polling,
outbound messages. Each needs the same access check as the routes, or users who
stopped paying keep costing money. Name those files and give them their own step
in the integration plan; a checkout-only plan misses them.

### 9. Record the decision

The last step of a full evaluation or migration analysis: write a short decision
note into the repo, so the next session starts from the decision instead of
re-running it. Use the repo's existing decisions directory if step 2 found one,
otherwise `docs/decisions/YYYY-MM-DD-<topic>.md`, in the short-note format from
`references/adr-template.md`: the call, the date, who made it, why, **every
rejected option with the specific reason it lost**, and when to revisit. The
rejected options are what stop the question coming back.

Mark it `Proposed` - the developer hasn't accepted anything yet - and name the
developer from `git config user.name` unless they said otherwise. Tell them the path
in one line and that it flips to `Accepted` when they confirm. For quick calls,
offer the note instead of writing it.

## Report structure

Full evaluations use `assets/report-template.md`. Sections, in order: recommendation,
SDK health and headline numbers; detected stack; options table with margin and
sensitivity; why the winner over the runner-up; what it touches; integration plan;
risks including lock-in; what would change this recommendation.

That last section is the most useful one a year later, and it becomes the note's
"revisit when". Drop any section that would be padding for the question asked.

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

Recommending before reading the repo. Recommending an SDK nobody probed. Eight options with no ranking. Pricing from
memory stated as current. An architecture the deployment target can't run - a
persistent worker on Vercel, a websocket server on static hosting. Ignoring a vendor
already in the manifest. Scoring everything 4/5 so nothing separates. Treating the
weighted score as the decision rather than as shown reasoning.

## Follow-ups

Offer at most one, when it fits: a **full ADR** (`references/adr-template.md`) if
the team keeps them; **migration analysis** for "should we move from X to Y";
starting **phase one** of the integration plan; or, if the repo has a `CLAUDE.md` or
`AGENTS.md` that doesn't mention the decisions directory, a one-line pointer so
future agents read the notes before touching that area.

## Files

| Path | Read when |
|---|---|
| `references/scoring-rubric.md` | Before scoring - anchored 0-5 definitions |
| `references/domains/<domain>.md` | While shortlisting, for that domain only |
| `references/impact-analysis.md` | Turning scan output into a plan |
| `references/migration-analysis.md` | Provider-to-provider migrations |
| `references/adr-template.md` | Writing the decision note, or a full ADR |
| `assets/report-template.md` | Writing a full report |

| Script | Purpose |
|---|---|
| `analyze_stack.py` | Stack, vendors, deployment, capabilities, constraints |
| `github_probe.py` | SDK health from registries and GitHub; find real integrations |
| `score_candidates.py` | Weighted scoring, margin, sensitivity, evidence audit |
| `impact_scan.py` | Touchpoints, infrastructure readiness, effort band |

All are standard-library Python 3.8+ and read-only; the decision note is the only
file the skill writes. The first, third and fourth are
offline and deterministic; `github_probe.py` is the only one making network calls,
and degrades to partial results rather than failing. Run `--help` on any of them. If
a script fails, read the repo directly and say so - the logic matters more than the
tooling.
