# Migration analysis

For "should we move from X to Y" questions. A migration is not an integration: the
system already works, real data exists, users are depending on it, and the upside
is usually smaller and less certain than it looks from inside the frustration that
prompted the question.

Start sceptical. The first useful thing to establish is whether the migration
should happen at all.

## 1. Establish the actual motivation

Ask what's driving it, because the answer changes everything downstream:

- **Cost** - get the current bill and the projected one. Migrations have a real
  engineering cost; a migration that pays back in eleven years is a hobby. Also
  check whether the current vendor negotiates, which is far cheaper than moving.
- **A missing capability** - confirm it's genuinely missing rather than unfound,
  and that the target actually has it. This is worth five minutes of verification
  before any planning.
- **Reliability or support** - quantify it. "Feels flaky" and "three incidents
  last quarter with no status page" justify different amounts of work.
- **Lock-in anxiety** - often better answered by adding an abstraction layer than
  by migrating. Migrating to escape lock-in usually creates new lock-in.
- **Preference or novelty** - a legitimate reason for a side project and a poor one
  for a system with users. Say this kindly but plainly.

If the motivation doesn't survive scrutiny, say so. "Stay where you are and here's
what to do about the actual problem" is a valid, and often the correct, answer.

## 2. Map the coupling

Run the stack analysis, then scan for the outgoing provider specifically:

```bash
python3 scripts/analyze_stack.py . --format text
python3 scripts/impact_scan.py . --domain <domain>
grep -rn "provider-name" --include=* -l .   # adapt per provider and language
```

Classify what you find, because the categories carry very different costs:

- **Call sites** - direct SDK usage. Mechanical, countable, low risk.
- **Data in the provider** - user records, files, subscription state. The hard
  part, and the part that determines feasibility.
- **Provider-shaped concepts in your domain model** - their IDs stored in your
  tables, their state machine mirrored in your logic, their webhooks driving your
  flows. This is the expensive coupling and the reason migrations overrun.
- **Operational dependencies** - dashboards support uses, alerts, runbooks,
  finance reconciliation. Routinely forgotten until the switch-off.

## 3. Assess data portability

The decisive question, and worth answering before anything else:

- Can the data be exported at all, in full, in a usable format?
- Is anything structurally non-portable? Password hashes with an unexportable
  algorithm, OAuth identity mappings, payment method tokens (usually transferable
  between processors only via a vendor-assisted process - it exists, and it takes
  weeks of lead time), file URLs already public.
- Do IDs need to be preserved, or can a mapping table carry them?
- What's the volume, and how long does the export and import actually take?

If critical data cannot move, the migration is either off the table or becomes a
long dual-run. Establish this early - it's the finding that saves the most wasted
planning.

## 4. Choose a strategy

| Strategy | How it works | Fits when | Cost |
|---|---|---|---|
| Big-bang cutover | Freeze, migrate, switch | Small data, tolerable downtime | Lowest effort, highest risk |
| Parallel run | Write to both, read from old, then flip | Data must stay consistent, no downtime allowed | Highest effort, lowest risk |
| Strangler | New traffic to the new provider, old drains naturally | Per-entity state like subscriptions | Moderate; long tail of two systems |
| Lazy migration | Migrate each record on first access | Records are independent, e.g. user credentials | Low effort; very long tail |
| Abstraction first | Introduce an interface, swap behind it | Many call sites, or the decision may reverse | Extra step, much safer |

For anything with users and money attached, parallel run or strangler are usually
the defensible choices. Recommend the cheapest strategy the risk profile allows,
and state the risk you're accepting.

## 5. Sequence it

Order so each step is independently reversible, and put the riskiest reversible
step early:

1. Abstraction layer behind the current provider, no behaviour change. Shippable
   on its own and valuable even if the migration stalls here.
2. New provider integrated behind the same interface, dark, exercised by tests.
3. Historical data migrated to the new provider, verified by reconciliation.
4. Traffic shifted incrementally, with a documented rollback at each step.
5. Old provider drained, then read paths removed.
6. Decommission: cancel the account, delete credentials, remove the dependency,
   update runbooks.

Step 6 gets skipped constantly, which is how teams end up paying for both.

## 6. Risk assessment

Give an overall rating with the reasoning visible.

- **Low** - additive or easily reversible, no data migration, few call sites.
- **Medium** - data migration with a verifiable export/import, rollback exists but
  costs something, contained coupling.
- **High** - non-portable data, auth or payments involved, wide coupling into the
  domain model, or rollback impossible after cutover.

Always state the point of no return explicitly: the moment after which rolling back
means data loss. Teams need to know which step that is before they start, not
during.

Also state what happens if the migration is abandoned halfway, because sometimes it
is. An abstraction-first plan degrades gracefully; a half-finished dual-write
leaves a mess. That difference is worth designing for.

## 7. What to deliver

- Whether to migrate at all, answered directly.
- The coupling map, with counts and real paths.
- Data portability findings, including anything that cannot move.
- The recommended strategy and why the cheaper ones were ruled out.
- Ordered phases with rollback points and the point of no return.
- Effort range, with the assumption stated - and note separately that migrations
  overrun more than greenfield work, because the surprises live in data nobody has
  looked at in years.
- A risk rating with its reasoning.

Offer an ADR afterwards. Migrations are exactly the decision future teams ask about.
