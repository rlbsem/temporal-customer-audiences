# Validation, skeptical review and limits

## Executed scope

The implementation ran locally with Python 3.12 and real SQLite tables/transactions. Software tests, SQL evaluation, independent Python evaluation, complete temporal generations and a separate synthetic destination database were executed. Exact environment versions, test totals and source hashes are in [verification.json](evidence/verification.json); individual cases are in [tests.xml](evidence/tests.xml).

The demo uses one fictional person to explain the two time coordinates and a separate 120-person dataset to measure feature reevaluation scope. No test skips unavailable infrastructure, and no model, network vendor, cloud service, real customer record or production traffic is involved.

The four previously published repositories' successful CI job statuses were observed through GitHub's API at their current commits, as recorded in [inspection.json](evidence/inspection.json). Their logs/artifacts were not downloaded for this review. This fifth repository has a supplied Windows/Ubuntu workflow but no observed hosted execution yet. Existing README claims were not substituted for inspection of workflow status.

## Core falsification tests

| Claim | Counterexample tested |
|---|---|
| Original and corrected history coexist | Late activity changes a historical answer at the same T but later K; the earlier generation and earlier-K answer remain unchanged |
| Arrivals are not the only trigger | No-ingestion clock advance causes a quiet-audience entry and engagement exit |
| Window edges are exact | Tests immediately before, at and after the left-exclusive expiry boundary |
| Revision selection is ordered correctly | A higher revision moves a profile into the future; filtering T first must not revive the older revision |
| Retractions cannot be undone by stale delivery | A lower source revision arrives after a higher retraction |
| Conflicting state is visible | Simultaneous contradictory profile values produce ambiguous state until an explicit correction |
| Dependency reuse is sound | Four seeded histories, each with 32 current publications, compare SQL/cached membership, feature counts, evidence and next boundary with full independent Python evaluation |
| Historical computation cannot activate | Historical generation leaves the current pointer unchanged and has no destination contract |
| Sparse changes do not reevaluate all subjects | One corrected subject out of 120 is recomputed; the full oracle agrees |
| Publication is not partially visible | Injected feature-evaluation failure preserves the active generation; concurrent identical build keys return one generation |
| Destination deltas do not resurrect old membership | Missing-parent and older bundles are rejected; before/after hashes bind actual state |
| Receipts do not conceal drift | Injected phantom membership is detected before new application and on retry |
| Contracts preserve provenance | Invalid types, conflicting fact revisions, duplicate operations and invalid decision coordinates are refused |
| Missing observations alone cannot activate quiet | No coverage, a one-second left gap, a one-second stale right edge and future-only coverage all suppress export while computed quiet remains true |
| Coverage is knowledge-bounded revision evidence | Late assertion restates safety at the same T; old K and saved generations remain unchanged; incomplete higher revisions and retractions never fall back to older coverage |
| Source expiry invalidates export without customer arrivals | Exact coverage entry/expiry edges change destination state with zero customer reevaluations and unchanged K; engagement remains eligible |
| Gate maintenance matches independent computation | Two seeded mixed histories compare every current and historical activation projection with an independent full evaluator and reconcile each delivered current bundle |
| Existing stored generations upgrade coherently | A pre-gate generation's exported quiet entry is removed on the first uncovered new publication without altering the old generation |

## Review-driven corrections and strengthened checks

The first complete suite passed 39 cases. Skeptical review then strengthened the proof rather than treating Boolean membership agreement as sufficient:

1. **Membership equality could hide incorrect counts or stale explanations.** The separate oracle was expanded to compute full features, supporting fact revisions and next time boundaries. Randomized histories now compare those with the incremental engine, including reused decisions.
2. **A synthetic destination could accept malformed explanation metadata while applying a valid membership change.** It now validates reason shape and rejects decision times later than the bundle's business time; targeted negative tests cover both.
3. **Timestamp normalization could silently accept an exotic fractional offset.** A targeted test failed against permissive parsing. The public timestamp helper now accepts only an explicit whole-second ISO format with Z or minute-resolution offsets, validates the date, and refuses fractional semantics.
4. **Destination reconciliation used separate read snapshots for membership and generation.** It now reads both inside one transaction so the report observes a coherent destination state.

These are bounded code review and executable checks, not a security certification or external audit.

## Narrow hostile-review enhancement pass

The completed 41-test baseline was rerun successfully before editing. Review covered the README, architecture, validation, generated evidence, all package source and all tests. Effective-time/knowledge ordering, revision selection before T filtering, retractions, future transitions, timer reuse, historical isolation and ordered destination reconciliation had no reproduced correctness defect in this pass. This is a bounded review finding, not a proof that defects cannot exist.

**Candidate A was implemented.** Before this pass, an observed-absence result was also exported, with a documented completeness limitation. It is now retained as computed membership but excluded from the synthetic export unless an explicit, revisioned assertion covers the whole observation window. Missing or withdrawn assertions and either interval gap fail closed for quiet only. Positive engagement still exports. Assertion correction and clock-only expiry can change eligibility independently of cached person features. The independent oracle and an eight-generation executed coverage story verify those effects.

The policy is strict interval coverage through T, with zero uncovered lag. A separate TTL, source registry or ingestion/governance framework would not strengthen this bounded proof. Assertions concern one whole synthetic activity source; their truth cannot be independently established by this engine.

**Candidate B was deferred.** Existing reasons, features and revision references permit manual comparison, but they do not directly encode the full causal trigger chain for every transition or explicitly pair original and restated generations. The new gate retains the evidence and failing conditions needed to audit its own eligibility changes; it is not presented as a general delta-explanation system. Completing and falsifying candidate A took priority over adding that second mechanism.

The final packaged-install verification records **58 passed, 0 failures, 0 errors, 0 skipped**, plus lint, dependency checks and the complete regenerated demo. All original 41 test cases remain; one destination expectation now compares against explicit `activation_members`, since raw `members` intentionally keeps observed-fact semantics. Exact source fingerprints and environment are in the generated verification record. Hosted CI remains unobserved.

## Portfolio overlap test

**What does this prove that the existing four do not already prove well?**

It proves that a materialized audience can preserve an original as-known answer and a separately corrected historical answer; update correctly when the clock advances without arrivals; handle retractions and revision ordering before effective-time filtering; and recompute only invalidated people while remaining equivalent to full evaluation, including explanations and timers.

The proof is visible in generated generations and tests, not a vendor substitution. Existing telemetry already handles late events and immutable publication, so those features alone would not justify this repository. Existing migration/control/agent projects already establish substantial reconciliation, authority and release behavior; the small destination is supporting evidence, not the project's thesis.

## Limitations

- Profile facts and stable person IDs are trusted normalized inputs. There is no identity resolution, source authentication, consent decision or authorization to communicate.
- The two rules are person-local and finite. Account/group dependencies, arbitrary joins, aggregate thresholds, a rule-authoring UI and a general incremental-query compiler are not implemented. Adding cross-person dependencies requires redesigning the invalidation model.
- Absence is absence of observed qualifying facts. An outage can still produce computed quiet, but missing/insufficient assertion coverage prevents synthetic export. A false supplied assertion can still allow an unsafe result; real source completeness and production audience safety are not proven. Assertions do not authenticate a source, validate partition coverage, or authorize communication.
- Knowledge is an ingestion commit sequence. It does not represent when a source first knew a fact, and multiple facts in one batch become visible together.
- Current publication requires monotone business time; historical recomputation is separate. No automatic background scheduler or real-time delivery SLA is implemented.
- Coverage must be checked on publication and delivered through ordered deltas; an already stored destination projection does not expire itself while the publisher is stopped. Scheduling must include both customer and source coverage boundaries.
- Feature computation is selective, but immutable generation assembly/storage is full-population. The engine is single-host, holds a SQLite write transaction while computing and retains all historical revisions. There is no load/scale benchmark or distributed warehouse deployment.
- Append-only history intentionally retains retracted facts. It is not a privacy-erasure implementation; use only the supplied synthetic data unless separate data-retention and deletion controls are designed.
- Old generations retain code fingerprints, but historical recomputation executes current code. Reproducing an old implementation requires its corresponding source checkout; code hashes are not archived executable environments.
- The destination is a local membership set with an intentionally strong transactional contract. Network retries, vendor rate limits, differing destination capabilities and automatic reconciliation repair are not exercised.
- Local filesystem/process ownership is the administrative boundary. Hashes detect ordinary corruption; they are not signatures against a malicious local administrator.
- CI for this repository is configured but unobserved. Linux execution, hosted warehouse execution, Salesforce/Data Cloud/Snowflake integration, production use, security certification and business outcomes are not claimed.
