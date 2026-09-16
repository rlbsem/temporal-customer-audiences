# Temporal model and maintenance algorithm

## Two coordinates, one explicit rule version

Every answer is identified by business time **T**, knowledge commit **K**, rule configuration and implementation fingerprint. T is a whole UTC second. K is a monotone, locally assigned successful ingestion-batch sequence. Receipt timestamps are recorded for operators; they are not an alternate ordering or a promise of source completeness.

Facts have `(source, fact_id, revision)` identity, a stable `person_id`, an effective time, a finite value and a retraction flag. Supported sources are normalized profile transitions and product activity. Upstream identity and authority resolution are assumed; the input source label is not authenticated enterprise provenance.

The visible revision of a logical fact is its highest source revision among rows received by K. Crucially, this selection happens **before** filtering effective time by T. If revision 2 moves a profile transition into the future, revision 1 cannot remain active merely because it has an earlier timestamp. A retraction removes the logical fact at that knowledge cutoff; lower revisions arriving later cannot resurrect it. An earlier K still reproduces the earlier visible revision.

Profile state at T is the value of the latest effective visible profile transition at or before T. Distinct conflicting values at the same latest time produce an explicit `ambiguous` state and exclude both audiences. A missing profile also excludes them. Retraction of a later transition may reveal an older transition; this is correction semantics, not person deletion or privacy erasure.

## Finite rules

| Audience | Rule |
|---|---|
| `engaged_trial` | Profile is trial and at least two distinct visible qualifying activity facts fall in `(T − 7 days, T]` |
| `quiet_trial` | Profile is trial and zero visible qualifying activity facts fall in `(T − 3 days, T]` |

Window sizes and minimum event count are validated configuration values. The SQL query structure and supported rules are fixed, not an arbitrary segmentation language. A day is 86,400 seconds, not a local-calendar day. UTC offsets are normalized at input; naive times, fractional seconds and fractional offsets are refused.

The left boundary is exclusive and the right boundary inclusive. An event effective at `e` first participates at `T=e` and leaves a W-second window at `T=e+W`. An event can therefore age out with no new ingestion. These two audiences are not mutually exclusive: recent silence can coexist with meaningful activity earlier in the seven-day window.

“No observed activity” is intentionally narrower than “no activity.” Delivery gaps can change that conclusion later. This project does not invent a completeness watermark from the largest event timestamp. A separate synthetic assertion now conditions export, as described below; production source completeness remains unverified.

## Minimal coverage model and export eligibility

There is exactly one assertion stream for the entire normalized activity source. `Store.ingest_coverage(batch_id, assertion)` admits `{revision, covered_after, covered_through, retracted}` into the same knowledge-commit sequence as customer facts. The assertion means the source claims complete delivery for the contiguous interval `(covered_after, covered_through]`, across all people. It is trusted synthetic input, not a measurement, source authentication or an inference from event timestamps. It does not certify profile authority or consent.

At K, choose the highest admitted assertion revision **before** examining its interval. Each revision replaces the entire assertion. An incomplete replacement or a retraction cannot fall back to an older fitting interval; out-of-order lower revisions cannot restore it. There is no union of disjoint intervals, partition registry or inferred future coverage. Duplicate deliveries, conflicting revisions and immutable records follow the fact ledger's admission principles.

Quiet export requires both computed quiet membership and a non-retracted assertion satisfying:

```text
covered_after <= T - quiet_window  AND  T <= covered_through
```

This deliberately strict policy tolerates **zero uncovered lag** at the observation window's right edge. A separate freshness TTL would add no proof: once coverage is behind T, the gate already fails. The left boundary must also be covered; a recent watermark alone is insufficient. At whole-second resolution, eligibility at fixed K can begin at `covered_after + quiet_window` and expires at `covered_through + 1`. If the interval is shorter than the rule window, it can never qualify. Source assertion timestamps are business-time coordinates; ingestion K determines when an assertion is available. Later knowledge may establish coverage for an earlier T in a historical restatement. No claim is made about real vendor delivery or the truth of these assertions.

`people[*].membership` and generation `members` remain computed observed-fact audiences. `activation_members` is the coverage-conditioned set used by current destination bundles and reconciliation. For historical generations it records hypothetical eligibility only: the generation still cannot export. `engaged_trial` is unaffected by this absence-only gate.

Every generation stores `activity_coverage`: required interval, selected revision/interval/retraction and original admission K (or null), failure conditions, evaluation T/K, eligibility and `next_due`. The gate is evaluated once on **every publication**, separately from person feature invalidation. Coverage arrival or clock passage can therefore change export eligibility while reusing every customer decision at its original evaluation coordinates. Customer timers remain in `people[*].features.next_due`; scheduling must also consider `activity_coverage.next_due`. There is no background publisher, so a stored projection changes only when a new current generation is built and delivered.

Correction and retraction may change a new generation's safety conclusion. Earlier generations retain their original assertion and conclusion. Coverage and customer data are read within the same publication transaction and K. Separate admission calls are separate knowledge commits; supplying a coverage assertion before its promised activity is actually admitted is a false upstream assertion that this synthetic gate cannot verify.

## Admission and atomicity

Each ingestion batch validates strict fields/types, refuses duplicate revisions within the batch, and commits all accepted revisions plus its knowledge sequence together. An identical batch ID/body returns its original sequence. An existing fact revision with changed content conflicts and rejects the entire batch. Repeated identical facts in a different batch do not create duplicate activity; their original knowledge sequence remains.

A logical fact cannot move to a different person. This protects the dependency assumption behind person-local incremental maintenance. Identity correction would require a separate reviewed input model, not a silent owner change.

Facts, coverage revisions, batch receipts and completed generations have append-only triggers. They are ordinary local database protections; an administrator owning the files can bypass them. There is no tamper-resistant ledger or independent attestation claim.

## Incremental invalidation

For a current generation, the engine forms the union of:

1. People with any newly admitted fact revision since the previous knowledge cutoff.
2. People whose persisted `next_due` boundary is at or before the requested new clock.

It recomputes those people from their complete visible history, not from a bounded event-arrival lookback. A revision arbitrarily far back in business time still invalidates its subject. Future profile/activity times and active event expiries determine the next boundary. Large clock jumps recompute once from the final T rather than replaying every intervening timer.

The dependency set is conservative: a correction to an irrelevant fact or a future noise event can cause an unnecessary reevaluation. No minimality claim is made. A rule or implementation change invalidates the whole population. Initial and historical computations are full evaluations.

Unchanged people reuse their previous decision and evidence. Their `evaluated_at` and `evaluated_known_through` retain the original evaluation coordinates; they are not relabeled as freshly queried. The containing generation records its current T/K and reuse counts. Until a relevant arrival or stored boundary occurs, person-local features, evidence and membership remain unchanged. Randomized tests independently check that claim for counts, profile state, supporting facts and next boundary, not only the final Boolean membership.

The generation is assembled and published in one SQLite write transaction. It captures a consistent ledger head and serializes with ingestion. Only a current generation may advance the active pointer, and it requires latest knowledge and a nondecreasing business clock. Historical generations may use earlier T/K, retain their own results, and produce no destination bundle.

Selective feature computation does not make the entire algorithm O(changes). The current implementation assembles and stores a full immutable population snapshot. Historical revision retention and per-person queries also have costs. This bounded project prioritizes a checkable dependency algorithm over a distributed optimization claim.

## Independent oracle

The production evaluator uses SQLite window queries in `features.sql`. The Python oracle reads admitted rows and independently selects revisions, profile transitions, observed windows, supporting facts and future boundaries. It does not import the feature SQL, call the production evaluator or reuse cached generation state.

Four seeded randomized histories exercise late/future times, revisions, retractions, conflicting profile transitions and clock advances. At every current publication, the tests compare both membership and full features with the oracle. Two additional seeded histories mix coverage revisions, customer corrections and clock steps, comparing export eligibility with `full_activation_members`, which independently selects coverage and evaluates the interval without importing the production gate. Historical samples compare knowledge-bounded results separately. Both implementations still share the written domain contract; this is not independent business-owner adjudication.

## Current deltas and historical restatement

Current publication compares the new `activation_members` set with the preceding active export set. Only additions and removals enter the export bundle. It includes lineage, current/parent generation, T/K, rule hash, before/after export membership hashes and a content seal. Reasons point to the deciding condition; complete supporting fact and coverage references stay in the generation. Quiet removals caused by the gate report its failed conditions, and their decision time is the gate evaluation time even when customer features were reused. Quiet additions report the observed-fact condition; the stored coverage decision explains eligibility. General causal trigger chains and automatic original/restated pairing are not implemented.

For a stored generation from version 1.0 without `activation_members`, its `members` set is the previous export set. The first new publication removes uncovered quiet entries from that prior projection; old generations remain unchanged. Consumers of new generation files must use `activation_members` for export and `members` for computed audiences. The ordered destination bundle shape remains unchanged.

Historical recomputation never changes current membership or creates an export. Original and restated generations are separate artifacts. Changing implementation code does not magically re-execute a historical binary: old generations retain their original implementation hash, while a new historical recomputation uses the selected rules and currently installed code. To reproduce an earlier implementation, use its corresponding source revision.

The synthetic destination stores only segment/person IDs and generation receipts. It applies a whole bundle transactionally, validates parent generation and actual before-state, verifies the after-state, and refuses changed retry payloads, missing predecessors, old deltas and observed drift. A retry at the current generation checks actual state rather than trusting only a receipt. Reconciliation reads state and membership in one database snapshot.

This destination proves that audience corrections produce coherent membership deltas. It does not implement network delivery, retry scheduling, a real reverse-ETL connector, consent checks or campaign execution; those would duplicate existing portfolio machinery or require vendor-specific contracts.
