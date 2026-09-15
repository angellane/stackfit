# Scoring rubric

Ten criteria, 0-5. **5 is always the favourable end.** Criteria that are naturally
"bad when high" are named so the direction stays consistent: `cost_efficiency`,
`implementation_speed`, `portability`. This makes the commonest weighted-scoring
bug - summing one criterion with the wrong sign - unrepresentable rather than
merely tested for.

Use the anchors, not an overall impression. Anchors are what make two runs on the
same repo agree, and what lets a developer dispute one score instead of the whole
table.

**Every score needs evidence** - a repo path, a documented behaviour, a measurement
from `github_probe.py`, or a fetched source. The scorer flags scores without it.

**Use the full range.** If everything scores 4, the table is decorative. Either the
research isn't finished, or the options genuinely are interchangeable - in which
case say that directly instead of manufacturing separation.

---

## architecture_fit
How naturally it fits the framework, data layer and runtime already present.

- **5** First-class for this exact stack: official framework adapter, works with the
  current runtime model unchanged, matches the data layer's conventions.
- **4** Well supported, minor glue. Official SDK for the language, no adapter.
- **3** Works on your own terms: generic REST, no idiomatic SDK, patterns invented locally.
- **2** Fights the architecture - needs a sidecar, a second data store, or a pattern
  at odds with how the app is built.
- **1** Requires restructuring the app.
- **0** Cannot run in this runtime. Prefer a disqualifier over a 0.

## implementation_speed
Time to a correct, production-ready integration. Judge the whole path - endpoints,
error handling, tests, deploy - not the quickstart, which is always fifteen minutes.

- **5** Under a day: drop-in SDK, no schema change, no new infrastructure.
- **4** One to three days: some schema work or a new endpoint, well-trodden.
- **3** About a week: new infrastructure (webhooks, jobs), state to reconcile.
- **2** Two to four weeks: multiple subsystems, backfill, staged rollout.
- **1** Over a month, or needs expertise the team lacks.
- **0** Open-ended.

## migration_ease
How little existing code and data changes. Greenfield features score 5, which
correctly means this criterion isn't doing any work in that decision.

- **5** Purely additive. **4** A handful of files, no data migration.
- **3** Schema changes across a subsystem. **2** Backfill or dual-write period.
- **1** Coordinated cutover with rollback planning. **0** Rewrite of the affected area.

## documentation_quality
Whether official docs let a competent developer finish without guesswork.

- **5** Complete, current, honest about edge cases; real examples in this language;
  webhook and failure semantics documented, not just happy paths.
- **4** Good coverage, gaps filled by community answers.
- **3** Adequate reference, thin guides. Expect trial and error.
- **2** Incomplete or drifting from actual behaviour. **1** Sparse or contradictory.
- **0** Effectively undocumented.

## sdk_quality
The client library **for this repo's language**. An excellent SDK in another
language is worth nothing here. Measure it with `github_probe.py` rather than
recalling: last publish, deprecation, archived status, types.

- **5** Official, actively maintained, idiomatic, typed, good errors.
- **4** Official and maintained; rough edges in typing or ergonomics.
- **3** Community-maintained or a thin wrapper; works, limited support.
- **2** Stale - no meaningful release in a year - or poor error surfacing.
- **1** Abandoned, or you'd write the HTTP client yourself.
- **0** Nothing usable for this language. Deprecated or archived packages belong
  here, and usually warrant a disqualifier instead.

## operational_simplicity
Ongoing burden once live. Scored too generously more often than any other criterion,
because operational cost is invisible at integration time and relentless afterwards.

- **5** Fully managed: no servers, no scaling decisions, no on-call surface.
- **4** Managed with real failure modes to monitor (webhook delivery, quotas).
- **3** Managed but still needs reconciliation jobs or state repair.
- **2** A self-hosted component to run, patch and back up.
- **1** A distributed system to operate (cluster, broker, index).
- **0** Needs dedicated operational ownership.

## cost_efficiency
Total cost at this project's realistic scale - scale matters more than rate. Include
what isn't on the pricing page: engineering time, the tier that unlocks the one
feature you need, egress. Pricing is volatile: verify in-session or label unverified.

- **5** Free or negligible here, with a sane growth curve.
- **4** Modest and predictable, scaling with value.
- **3** A noticeable line item, acceptable for what it does.
- **2** Expensive at this scale, or a cliff at the next tier.
- **1** Dominates the budget, or is unpredictable. **0** Not viable.

## scalability_headroom
Room to grow before this decision must be revisited.

- **5** Orders of magnitude of headroom. **4** Comfortable; scaling is config.
- **3** Fine for the next stage, known ceiling beyond. **2** Rework likely within a
  year of growth. **1** Near its limits already. **0** Can't meet current needs.

## ecosystem_maturity
Adoption, community answers, third-party integrations, vendor stability. Partly a
proxy for how fast someone gets unstuck at 2am, partly a bet on the vendor still
existing - neither captured by the docs score.

- **5** Industry standard; answers exist for most problems you'll hit.
- **4** Widely used, active community, stable company.
- **3** Established but niche - you'll sometimes be first.
- **2** Early: small community, rapid API changes.
- **1** Very new or shrinking, real discontinuation risk. **0** Abandoned.

## portability
How cheaply you could leave. Ask concretely: if this vendor tripled prices tomorrow,
what would switching cost?

- **5** Open standard or self-hostable; data exports cleanly; swapping is config
  (SMTP, S3-compatible storage, Postgres).
- **4** Proprietary behind a thin interface; data exports; days to swap.
- **3** Provider-shaped code in a few places; weeks to swap, data portable.
- **2** Provider concepts spread through the domain model; painful export.
- **1** Deeply embedded. **0** No export path for critical data.

---

## Weight profiles

`score_candidates.py --list-profiles` prints exact numbers. Pick from what the
developer said; otherwise `default`, and name it in the report so the assumption is
visible.

| Profile | Use when | Emphasises |
|---|---|---|
| `default` | No strong signal | Balanced, architecture fit leading |
| `ship-fast` | Prototype, deadline, validating | Speed, docs, SDK quality |
| `cost-sensitive` | Side project, bootstrapped | Cost, then ops simplicity |
| `enterprise` | Compliance, procurement, large org | Scale, portability, maturity |
| `long-haul` | Core, long-lived infrastructure | Portability, ops simplicity |

Override individual weights with `--weights '{"cost_efficiency": 25}'` when a
specific priority is stated. Say that you did, and why.

## Disqualifiers versus low scores

A hard requirement failure is a `disqualifier`, not a 1/5 - scoring it low lets a
strong showing elsewhere drag an impossible option back up the table.

Use one when the option cannot satisfy a stated requirement: no SOC 2 under
procurement, no EU residency under GDPR, no self-hosting when mandatory,
unsupported runtime, an unacceptable licence, a deprecated or archived SDK. Record
it as a short factual string - it appears in the report, so the developer sees the
option was considered and why it lost.
