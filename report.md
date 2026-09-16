# Executed temporal audience proof

| Business question | Observed result |
|---|---|
| What did we believe on day 3 before late activity arrived? | Ada was not in the engaged-trial audience at knowledge commit 1 |
| What does the corrected day-3 history say? | At knowledge commit 2, Ada qualifies; the original generation remains unchanged |
| Does historical recomputation change the destination? | No: historical generations have no export bundle and do not move the active pointer |
| What if no new data arrives? | At day 5, computed quiet-trial begins but export is suppressed without coverage; at day 8, engagement expires |
| What if an activity is retracted? | Restated day-3 engagement is withdrawn; prior published history is retained |
| What if a future profile change is already known? | Its effective-time boundary removes membership without another ingestion |
| Does a sparse correction require reevaluating everyone? | 1 of 120 people reevaluated; result equals independent full evaluation |
| Can an older audience delta resurrect membership? | Out-of-order delivery is refused |
| Is destination drift visible? | An injected phantom member appears as an explicit extra record |

## Executed coverage counterexample

The separate `coverage_safety` scenario retains eight complete generations and destination receipts:

| Input or boundary | Computed membership | Eligible for synthetic export |
|---|---|---|
| Day 5, no coverage assertion | Engaged and quiet | Engaged only |
| Late assertion covers (day 2, day 5] | Unchanged | Historical restatement says both; original stays unchanged and historical cannot export |
| Current publication at day 5 | Unchanged | Both |
| Clock advances one second, same K, zero customer reevaluations | Unchanged | Quiet removed; engaged retained |
| Revision 2 moves coverage start to day 3 | Unchanged | Quiet remains blocked: observation window has a gap |
| Revision 3 repairs interval | Unchanged | Both |
| Revision 4 retracts assertion | Unchanged | Quiet removed again |

All eight projections match independent full evaluation; the destination reconciles after ordered delivery.
Coverage is a supplied synthetic assertion about the whole activity source, not inferred from event timestamps.
It must cover the entire quiet window through T, with no lag tolerance or extrapolation.

[Detailed facts, decisions and deltas](temporal-proof.json) · [Timeline table](timeline.csv)

Both rules concern observed synthetic facts. Quiet does not prove absence of real-world activity. The gate demonstrates behavior conditional on explicit synthetic coverage, not real-source completeness or permission to contact. Feature recomputation is selective; immutable generation assembly still copies the full population. No distributed throughput or production scale is claimed.
