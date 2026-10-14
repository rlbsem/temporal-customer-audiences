# Temporal Customer Audiences — release and verification

## What the engine proves

The engine maintains membership across **effective time and knowledge time**, preserves original versus restated decisions, and invalidates results when facts change or time alone crosses a rule boundary. Tested cases include late arrivals, retractions, time corrections, no-ingestion expiry and historical backfills checked against an independent evaluator.

## Implementation and observed results

Python plus SQLite window queries implement two finite person-local rules. An immutable revision ledger supports knowledge-bounded reads. Current generations reuse unaffected decisions, recompute changed/due people and emit membership deltas. Historical generations are separate and have no export bundle. A second SQLite database simulates a destination's membership set and ordered receipts.

**Final packaged-install validation: 58 tests passed, zero failures, errors or skips.** The full demo ran after the tests. The sparse-correction experiment reevaluated **1 of 120 people** and matched full evaluation. Generation assembly still copies the entire population; this result does not imply end-to-end constant work or production throughput.

The [generated report](evidence/report.md) provides the 30-second story. [Detailed proof](evidence/temporal-proof.json) retains original/restated generations, fact references, counts, timers, deltas and an injected destination-drift finding. [Verification](evidence/verification.json) records the tested environment and source hashes. [Timeline CSV](evidence/timeline.csv) provides a compact comparison.

## Review corrections

Review expanded the oracle beyond Boolean membership, enforced explanation metadata at the destination, made destination reconciliation use one read snapshot, and corrected a timestamp edge case exposed by a failing fractional-offset test. [Validation](validation.md) records the counterexamples, corrections and remaining limitations.

The subsequent narrow enhancement pass implemented a coverage-conditioned export gate, preserved computed audience semantics, and extended the independent oracle. The eight-generation coverage demonstration shows quiet suppressed without coverage, enabled by late explicit coverage, removed one second beyond coverage without customer reevaluation, and affected by coverage corrections/retractions while prior generations remain unchanged. Engagement remains eligible throughout. A pre-gate stored-generation test verifies ordered removal on upgrade.

**What is materially stronger now?** Missing observations alone no longer cause an absence-based synthetic activation. The repository proves that coverage-dependent eligibility can change with time or knowledge independently of computed membership, without rewriting history or confusing reused customer evidence with freshly evaluated safety evidence. A general before/after causal explanation system was deliberately deferred; existing explanations require manual comparison beyond the explicit coverage conditions.

## Deliberate omissions and factual boundary

There is no identity resolver, consent engine, AI model, approval platform, campaign sender, broker, cloud warehouse imitation or vendor connector. Those either duplicate existing proofs or add no value to the temporal question. The runtime has no third-party dependencies; development tools are locked.

All records and destination behavior are synthetic. Quiet means no qualifying event was observed, not that source coverage is complete. An explicit interval assertion now controls quiet export, but its truth and real-source completeness are not independently proven. There is no extrapolation beyond coverage or uncovered lag tolerance. This is not privacy erasure: retractions preserve audit history. Rules are finite and person-local with one source-wide gate, the clock is explicitly supplied, and no background scheduler or distributed service is claimed.

The implementation was executed locally on Windows; the published build also passed [GitHub Actions verification](https://github.com/rlbsem/temporal-customer-audiences/actions/runs/38501648354). Neither result establishes deployment to Salesforce, Data Cloud or Snowflake, production customer use, or measured commercial outcomes.

## Reproduction and current verification

Follow [local operating instructions](operations.md) to install the Python 3.12 dependencies and run `python scripts/verify.py`. Review the [generated result](evidence/report.md), [source and runtime hashes](evidence/verification.json), and the [successful hosted workflow](https://github.com/rlbsem/temporal-customer-audiences/actions/runs/38501648354).

The implemented local scope is complete. General segmentation languages, production integrations and distributed scheduling are separate extensions, not capabilities claimed here.
