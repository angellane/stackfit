# StackFit

A [Claude Skill](https://docs.claude.com/en/docs/agents-and-tools/agent-skills/overview)
that answers "which service should I use for this feature?" — for *your* repository,
not in the abstract.

Ask it to add subscriptions and it reads your codebase first: framework, ORM,
deployment target, the vendors you already pay for, whether you can even receive a
webhook. Then it shortlists real candidates, scores them on a weighted rubric,
tells you what the integration will touch, and commits to an answer.

```
You: I need to add subscription billing to this app.

→ Reads the repo: Next.js 14 on Vercel, Prisma + Postgres, Auth.js, Resend, no job runner
→ Flags the constraint: serverless with no worker — reconciliation needs a scheduler
→ Shortlists 3 candidates plus "extend what you already have"
→ Scores them, checks the result survives different priorities
→ Reports: 14 files touched, 1 new table, 3 env vars, webhook endpoint missing
→ Recommends one, and says what would change its mind
```

## Why this exists

"What's the best payments API?" has a generic answer you can find anywhere.
"What's the best payments API *for this codebase*" has a specific one, and it
depends on things only the repository knows — that you're on a serverless host that
can't run a worker, that you already pay for a platform covering half the feature,
that your `users` table would collide with the provider's identity model.

This skill encodes the reasoning an experienced engineer applies to that question,
and grounds it in static analysis rather than recall.

## What it covers

Any feature you want to add — not a fixed menu. Curated playbooks (landscape,
deciding factors, hidden requirements) ship for:

`auth` · `payments` · `storage` · `email` · `sms` · `notifications` · `search` ·
`analytics` · `realtime` · `ai` · `jobs` · `database` · `cms` · `feature-flags` ·
`observability`

The impact scanner adds `i18n`, `documents` (PDF/e-signature), `maps` and `video`,
and takes free text rather than keywords — `--domain "e-signature for contracts"`
resolves to `documents`, `--domain "add stripe billing"` to `payments`. Anything
unrecognised falls back to a generic integration profile instead of failing, since
it still finds credential handling, existing API clients, config and data models,
which is most of what any integration touches.

The reasoning is domain-agnostic throughout: reading the repo, framing the decision,
weighing the existing vendor and build-versus-buy, scoring, and blast radius apply
to a maps API exactly as they do to billing.

## What makes the output trustworthy

Recommendation engines fail in predictable ways. Each of these is designed against:

| Failure | Mitigation |
|---|---|
| Generic advice dressed up as analysis | Every claim traces to a file path, dependency or constraint found by the analyzer |
| Confident, stale pricing | Volatile facts must be verified in-session or labelled unverified; the scorer audits for it |
| Fake precision — "87.3/100" | Margin check declares ties; sensitivity check reports when the winner depends on priorities |
| Scores as unfalsifiable vibes | Anchored 0–5 definitions per criterion, and an audit that flags scores with no evidence |
| Underestimating the real work | Effort bands come from an actual touchpoint scan, with missing infrastructure priced separately |
| Two tools disagreeing | The impact scanner reads manifests as well as paths, so it agrees with the stack analyzer |
| Recommending a dead SDK | Package registries and GitHub are probed for deprecation, archival and last-publish date |

The scoring engine is built to argue back. If the top two options are within five
points it says so rather than pretending a decimal decided it. If the winner changes
under a different weight profile, it reports that too.

## Install

**Claude Code** — clone into your skills directory:

```bash
# available in every project
git clone https://github.com/YOUR_USERNAME/stackfit.git \
  ~/.claude/skills/stackfit

# or just this project
git clone https://github.com/YOUR_USERNAME/stackfit.git \
  .claude/skills/stackfit
```

**Claude.ai / API** — package it and upload:

```bash
zip -r stackfit.skill . -x '.git/*' 'tests/*' 'evals/*' '__pycache__/*'
```

Then just describe the feature you want to add. The skill triggers on questions
about choosing services, comparing providers, build-versus-buy, migrations, and
Architecture Decision Records.

## Usage

Natural language, in a repository:

```
"Add subscriptions to this app"
"Stripe or Paddle for this codebase?"
"Should I use Clerk here or keep Auth.js?"
"What would moving from Firebase to Supabase cost us?"
"Write an ADR for the payments decision"
```

The scripts also run standalone:

```bash
python3 scripts/analyze_stack.py .                        # what is this repo built on
python3 scripts/impact_scan.py . --domain payments        # what would billing touch
python3 scripts/github_probe.py probe stripe paddle-sdk   # is the SDK actually alive
python3 scripts/github_probe.py find "nextjs stripe subscription" --language TypeScript
python3 scripts/score_candidates.py candidates.json --format markdown
```

### Example: stack analysis

```
$ python3 scripts/analyze_stack.py .

DETECTED STACK
  auth:          NextAuth / Auth.js
  database:      PostgreSQL
  email:         Resend
  framework:     Next.js
  orm:           Prisma

DEPLOYMENT
  targets: Vercel
  runtime model: serverless

CAPABILITIES
  can_receive_webhooks     yes
  has_background_jobs      no
  has_migrations           yes

EXISTING VENDORS (prefer extending these before adding new ones)
  NextAuth / Auth.js, Resend, Sentry

CONSTRAINTS TO CARRY INTO THE RECOMMENDATION
  - Serverless/edge deployment with no job runner: anything needing retries,
    long-running work, or scheduled reconciliation needs a hosted queue
    (or provider-managed jobs) rather than an in-process worker.
```

That last block is the point. It's the reason the recommendation differs from the
one a search engine gives you.

### Example: scoring

```
#   candidate                     score  status
1   Stripe Billing                 88.0
2   Lemon Squeezy                  75.6
3   Paddle                         74.8

MARGIN: 12.4 points over the runner-up.
SENSITIVITY: winner holds under every weight profile.

EVIDENCE AUDIT
  - Lemon Squeezy: 1 unverified fact(s) - pricing. Pricing and quota figures
    move; label these as unverified in the report or check the vendor page.
```

### Example: SDK health

Stars are a popularity contest. What actually matters is whether the package is
alive — and that's measurable:

```
$ python3 scripts/github_probe.py probe stripe @paddle/paddle-js

package                   status      stars     version     last activity
stripe                    active      -         22.6.2      2026-09-09
@paddle/paddle-js         active      -         1.6.5       2026-08-25

stripe (stripe/stripe-node)
  active: last activity 5 days ago
  suggested anchors: sdk_quality 4-5, ecosystem_maturity 3-4 (ships type definitions)
  ! GitHub rate limit exhausted, resets at 17:34 UTC. Set GITHUB_TOKEN for 5000/hour.
```

Registries are read first because they're the only source that reports
**deprecation**, and because GitHub allows just 60 requests/hour unauthenticated —
a limit shared IPs blow through constantly. When that quota is gone the probe
returns registry data and says so, rather than failing or quietly presenting
partial data as complete. Set `GITHUB_TOKEN`, or have `gh` logged in, for 5000/hour.

`find` locates real implementations to read for integration patterns:

```
$ python3 scripts/github_probe.py find "nextjs stripe subscription" --language TypeScript
```

## Token economy

A skill that wastes context is a skill that gets less room to think. Two things are
optimised: what Claude loads, and what you read.

**What Claude loads.** Domain playbooks are split one file per domain, so a payments
question loads the payments playbook rather than all eleven:

| | Before | After |
|---|---|---|
| Always resident (description) | ~222 | ~222 |
| On trigger (`SKILL.md`) | ~3,773 | ~3,309 |
| Domain lookup | ~4,556 (all of them) | ~604 (one) |
| **Typical full evaluation** | **~10,600** | **~5,800** |

Roughly a 45% reduction, while adding the GitHub probe — [progressive
disclosure](https://docs.claude.com/en/docs/agents-and-tools/agent-skills/overview)
doing the work it's designed for.

**What you read.** `SKILL.md` carries explicit output rules: lead with the decision,
never narrate which scripts ran, never state a fact twice, tables for comparison and
prose only for reasoning, cut any sentence that would be true of any repo, and no
closing summary restating the recommendation. Rough budgets are 250 words for a
quick call and 900 for a full report. The goal is density — not brevity that drops
the reasoning you needed.

## How it works

```
stackfit/
├── SKILL.md                  # workflow, report contract, judgment rules
├── scripts/
│   ├── analyze_stack.py      # languages, frameworks, data layer, vendors, runtime
│   ├── github_probe.py       # SDK health from registries + GitHub; find integrations
│   ├── score_candidates.py   # weighted scoring + margin, sensitivity, evidence audit
│   └── impact_scan.py        # touchpoints, infrastructure readiness, effort band
├── references/
│   ├── scoring-rubric.md     # anchored 0-5 definitions for all ten criteria
│   ├── domains/              # 15 per-domain playbooks, loaded one at a time
│   ├── impact-analysis.md    # scan output → schema, deps, env, phased plan
│   ├── migration-analysis.md # provider-to-provider migration assessment
│   └── adr-template.md       # ADR format and worked example
├── assets/report-template.md
└── tests/test_scripts.py     # 80 tests
```

Claude loads `SKILL.md` when the skill triggers and pulls in reference files only
as needed — [progressive disclosure](https://docs.claude.com/en/docs/agents-and-tools/agent-skills/overview),
which keeps the always-on cost to the description alone.

### Scoring criteria

Ten criteria, each 0–5, all oriented so **5 is always the favourable end** — cost,
effort and lock-in are scored as `cost_efficiency`, `implementation_speed` and
`portability`. This removes the commonest bug in weighted scoring, where one
criterion is summed with the wrong sign and silently inverts the ranking.

`architecture_fit` · `implementation_speed` · `migration_ease` ·
`documentation_quality` · `sdk_quality` · `operational_simplicity` ·
`cost_efficiency` · `scalability_headroom` · `ecosystem_maturity` · `portability`

Five weight profiles ship with it: `default`, `ship-fast`, `cost-sensitive`,
`enterprise`, `long-haul`. Individual weights can be overridden.

## Design decisions

**Standard library only.** No dependencies to install, nothing to break in someone
else's environment, works offline. Python 3.8+.

**Deterministic.** Same repository in, byte-identical JSON out. Tested explicitly —
a recommendation engine that gives different answers on reruns can't be trusted or
diffed.

**Read-only and secret-safe.** Nothing writes to your repo. Real `.env` files are
never read; only `.env.example`-style templates, and only key *names*. There's a
test asserting no secret value can reach the output.

**Hard requirements exclude rather than score.** An option that can't meet a
constraint gets a disqualifier, not a 1/5 — otherwise a strong showing elsewhere
drags an impossible option back up the table.

**The scripts inform the judgment, they don't replace it.** Static analysis can see
that Prisma is installed; it can't see that it's used in one file and raw SQL
everywhere else. `SKILL.md` instructs Claude to confirm by reading actual files, and
to fall back to manual analysis if a script fails.

## Testing

```bash
python3 -m unittest discover -s tests -v
```

80 tests covering stack detection across JavaScript and Python fixtures, scoring
arithmetic against hand-checked values, validation and error paths, CLI exit codes,
determinism, secret safety, and skill-format integrity (frontmatter limits,
`SKILL.md` length, referenced files existing).

The suite is mutation-tested — deliberately breaking the `node_modules` exclusion
or a weight value makes it fail, which is the property that makes a green run mean
something.

## Roadmap

- Cost modelling from repo-derived usage signals rather than flat estimates
- Pluggable domain playbooks so teams can encode their own vendor policy
- `--json` output consumable by CI, to flag when a decision's revisit conditions are met

## License

MIT — see [LICENSE](LICENSE).
