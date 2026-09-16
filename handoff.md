# Finished fifth-project handoff

**Decision: a fifth flagship is justified only with a narrow temporal-computation focus. Built: `temporal-customer-audiences`.**

The four current public repositories were inspected before implementation, including source, tests, generated evidence and current-commit CI status. The [decision record](decision.md) compares temporal audiences, configuration assurance, revenue integrity and an independently derived causal-experiment platform across all ten requested criteria. The selected project adds the strongest combination of new executable proof and relevance to the user-supplied Extreme Networks/Neon One role themes. It is not optimized for BMO's already advanced process.

## The new reason to inspect this repository

The existing portfolio already supports analytical truth, authoritative state, agent-quality decisions and safe migration. This project proves a different capability:

**Maintain audience membership across effective time and knowledge time, preserve original versus restated decisions, and correctly invalidate results when either facts change or time alone changes the answer.**

The proof includes late arrivals, higher-revision retractions, corrections that move effective dates, conflicting profile facts, no-ingestion expiry, future scheduled profile transitions and a historical backfill that cannot become an activation. Incremental results, counts, supporting facts and due boundaries are checked against an independently coded full evaluator.

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

The new implementation was executed locally on Windows. Its Windows/Ubuntu CI configuration is provided but unobserved remotely. The successful hosted jobs observed for the previous four repositories do not establish CI success for this fifth repository. No Salesforce/Data Cloud/Snowflake deployment, production customer use or business outcome is claimed.

## Publication steps

1. Extract the finished archive and read the README's original-versus-restated example and overlap decision.
2. Create a Python 3.12 environment, install `requirements.lock`, install the project with `python -m pip install --no-deps --no-build-isolation -e .`, and run `python scripts/verify.py`.
3. Inspect the generated counterexamples, source and MIT license. Publish to a new repository yourself; this build did not create or push a remote repository.
4. Observe both CI jobs before making a hosted-CI claim. Keep source completeness, privacy/consent and production deployment outside the demonstrated claim boundary.

The local scope is complete. No scaffold or deferred implementation is presented as finished; broader segmentation languages, operational adapters and production infrastructure are separate extensions.
