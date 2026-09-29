# {Feature}: integration recommendation

> Fill every `{...}`. Delete any section that would be padding for the question
> asked - a short report that is all substance beats a complete one with filler.
> Guidance lines like this one come out of the finished document.

**Recommendation:** {Option} · **Effort:** {range} developer-days · **Confidence:** {high | medium | low, and why}

**SDK health:** {package} {version}, last release {date} - {status from github_probe.py, or "not measured" and why}

{If that status is anything but `active`, this line is the first risk the reader
sees - say what it means for the decision here, not only in the risks table.}

{One paragraph: the decision and the single most important reason it fits this
repository. Name something concrete - the framework, the runtime, an existing
vendor. If this paragraph would read the same for any codebase, rewrite it.}

---

## Your stack, as detected

| | |
|---|---|
| **Language / framework** | {from analyze_stack.py} |
| **Data layer** | {database and ORM} |
| **Deployment** | {target, and runtime model - this constrains the options} |
| **Existing vendors** | {what's already paid for and integrated} |
| **Relevant gaps** | {missing webhook surface, job runner, migrations, tests} |

{One or two sentences on what in this stack drove the decision. If a hard
constraint eliminated options outright, say so here rather than burying it.}

---

## Options considered

{Table from `score_candidates.py --format markdown`, including the margin and
sensitivity notes it emits. Keep the sensitivity line - a winner that only wins
under one weight profile is a preference, and the reader is entitled to know.}

{If any option was excluded on a hard requirement or a dead SDK (archived,
deprecated, dormant), list it with the reason named. Showing the work prevents the
same suggestion being re-raised later, and these reasons go into the decision note.}

---

## Why {winner} over {runner-up}

{Three to five bullets. Each tied to something concrete: a file, a dependency, a
constraint, a documented behaviour. Cut any bullet that is generic vendor praise.}

{Then, in one or two sentences, the strongest argument for the runner-up - the
circumstance in which it would be the better call. If you can't articulate one,
either the shortlist was too weak or the analysis is one-sided.}

---

## What this touches

**Files** ({n} likely, from the impact scan)
{Grouped by intent, not a flat path list. Say what changes and why.}

**Schema**
{Tables, columns, relations, indexes - especially the provider-ID lookup index that
every webhook handler hits. Migration mechanism matching the repo's tooling.}

**Dependencies**
{Packages, with the reason for each. Flag native deps, version constraints,
bundle-size cost for client SDKs.}

**Environment**
| Variable | Purpose | Needed in |
|---|---|---|
| {NAME} | {what it does} | {server / client / CI} |

**Outside the request path**
{Workers, cron jobs and queued tasks that do paid work per user and need the same
access check as the routes - named by file. Omit only if you looked and found none.}

**Missing infrastructure**
{Each gap priced as its own piece of work, not folded into the integration.}

---

## Integration plan

**Phase 1 - {name}** · {effort}
{What gets done. Done means: {concrete, verifiable condition}.}

**Phase 2 - {name}** · {effort}
{...}

{Each phase should end somewhere shippable, so the work can pause or change hands.
Verification must be concrete - "trigger a test webhook and confirm the row
updates", not "test the integration".}

---

## Risks and watch-outs

| Risk | Impact | Mitigation |
|---|---|---|
| {specific to this repo and this choice} | {what actually happens} | {what to do} |

**Lock-in.** {What leaving costs: which data is portable, which code is
provider-shaped, roughly how long an exit takes. Developers can accept lock-in
knowingly - they just shouldn't discover it later.}

---

## What would change this recommendation

- {Condition} → {different answer, and why}
- {Scale threshold, requirement change, pricing change, team change}

{The most useful section a year later: it tells the team when to revisit rather
than leaving the decision to calcify or be reopened at random.}

---

{If any figure here is unverified, say so plainly - which ones, and where to check.
An unlabelled stale price is worse than no price, because it gets budgeted against.}

Decision recorded: `{path to the decision note}` (Proposed - flips to Accepted when you confirm)
