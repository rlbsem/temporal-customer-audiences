# Architecture decision: temporal audience correctness

## Problem boundary

Audience membership changes when evidence arrives late, an accepted revision is retracted, a profile effective date changes, or the clock advances without new ingestion. Current-state-only tables cannot answer what was believed at knowledge time K about business time T.

## Design alternatives and decision

- Current-membership-only materialization loses original knowledge-bounded decisions after correction.
- Full recomputation is a useful correctness oracle but does not demonstrate selective invalidation and time-triggered maintenance.
- A generic activation platform would add unrelated integration and permission complexity rather than testing the difficult temporal invariants.

**Selected approach:** finite, person-local audience rules with immutable generations, original and restated history, retraction-aware revisions, clock-driven expiry, coverage-conditioned export and an independent full evaluator. Identity, contact consent and destination campaign execution remain separate governed responsibilities.

## Scope chosen before implementation

Build `temporal-customer-audiences`: authoritative person IDs and normalized profile facts are inputs. Two finite rules exercise positive activity and absence of observed activity. Preserve immutable as-known generations, compute historical restatements separately, and maintain current membership from changed subjects plus scheduled time boundaries. A small synthetic destination applies membership deltas so corrections can be checked end to end.

The decisive overlap test is executable: **advance the clock without ingesting a row and obtain the correct exits/entries; then deliver a late correction, restate a past audience without rewriting its original generation or exporting that historical result, and prove incremental results equal an independent full evaluation.** None of the existing four demonstrates that combination.

Python, SQLite window queries and a separately coded Python oracle are enough. SQLite supplies reproducible relational state and atomic generations; it is not a claimed distributed warehouse. No identity resolver, consent engine, messaging executor, AI agent, cloud imitation, dbt wrapper, broker or approval platform is built. Destination sequencing is supporting verification of audience deltas, not another durable integration product.

The fifth project must remain subordinate to these boundaries. More source types, vendors and architecture boxes would dilute its reason to exist.
