# Fifth flagship decision: build a narrowly bounded temporal audience engine

## Inspection and remaining gap

The four public repositories were downloaded at their current commits before selection. Source, tests, architecture, generated evidence and workflow definitions were inspected. GitHub's Actions API reported successful current-commit jobs for all four; [inspection.json](evidence/inspection.json) records exact commits, job URLs and observation time. This review observed status metadata, not fresh execution or downloaded CI logs/artifacts. The hiring context below is supplied by Richard, not independently verified recruiter information.

| Existing project | Specific inspected evidence | What it does not establish |
|---|---|---|
| Analytics truth | `fct_sessions.sql` rebuilds affected sessions from complete history; `dim_player.sql` restates first-seen cohorts | Retraction-aware audience membership at both a business-time and knowledge-time coordinate; clock-driven invalidation without new ingestion |
| Governed truth | PostgreSQL customer state, source sequences, consent, jobs, approvals and append-only audit | Temporal audience computation and preservation of earlier membership decisions after facts are corrected |
| Agent quality | Structured decisions, behavioral comparison, immutable release evidence and routed rollback | Deterministic temporal query maintenance |
| Migration truth | Snapshot/change transfer, independent semantic reconciliation and evidence-bound cutover | Audience entry/exit history under late facts, rolling-window expiry and historical recomputation |

The distinction is deliberately narrower than “customer data.” Most ingestion, governance and delivery mechanics are already covered. A new project qualifies only if its executable center is **two-time audience semantics and incremental maintenance as time advances**.

## Four genuinely different candidates

**A — Temporal customer audiences.** Who belongs at business time T given knowledge available at K, how do late corrections change that answer, and what must be recomputed when no new events arrive?

**B — MarTech configuration assurance.** Can a dependency graph of workflow/configuration objects be promoted without dangling references, incompatible contracts or environment drift? Dependency planning is new, but much of the surrounding promotion/gating/recovery story is already demonstrated.

**C — Revenue integrity.** Can commercial, fulfillment, billing and ledger records be reconciled into an explainable variance bridge? Cross-ledger conservation and financial classification are new; current role alignment is weaker and domain-policy assumptions could dominate a synthetic implementation.

**D — Causal experiment integrity (independently derived).** Can randomized marketing interventions produce defensible incremental-effect estimates despite noncompliance, delayed outcomes and allocation defects? This adds causal identification and experimental validity, not another behavioral telemetry pipeline. It fits Richard's paid-media background but is less central to the current architecture/orchestration interviews.

## Comparison

These are qualitative judgments, not measured hiring probabilities. “Overlap” describes risk, so lower is preferable. There is no mechanically summed score.

| Criterion | A: temporal audiences | B: configuration | C: revenue integrity | D: causal experiments |
|---|---|---|---|---|
| Portfolio complementarity | Strong if two-time semantics are central | Moderate | Strong | Strong |
| Current-role usefulness | Strong: customer context and data lifecycle | Strong: platform lifecycle | Moderate | Moderate |
| Senior technical hiring signal | Strong temporal/data reasoning | Strong only with genuine dependency semantics | Strong financial integration reasoning | Strong measurement reasoning |
| Engineering depth | Time boundaries, revisions, negative evidence, invalidation | Dependency planning and partial application | Cross-system conservation and classification | Assignment, estimands and bias controls |
| Executable evidence potential | Strong: independent oracle and boundary counterexamples | Strong but much repeats existing proofs | Strong if financial assumptions are explicit | Strong with simulation; weaker on real treatment impact |
| Overlap risk | Moderate; high if expanded into a generic CDP | High around release/control machinery | Moderate around reconciliation | Low |
| Interview defensibility | Strong with precise finite rules | Moderate without real platform adapters | Moderate without independent accounting review | Strong technically, less aligned to role ownership |
| Long-term value | Strong across customer/data roles | Strong for platform administration | Strong for PE/integration positioning | Strong for growth/measurement roles |
| Distinctiveness | Strong two-time and timer-driven demonstration | Moderate within this portfolio | Strong | Strong |
| New proof unavailable elsewhere | Original versus restated membership; silent expiry; selective recomputation | Configuration graph semantics | Financial variance classification | Causal identification |

**Ranking for this portfolio now: A, D, B, C. Only A clears both the new-proof and current-role relevance thresholds for immediate construction.** D is a credible future direction, not dismissed as weak; its hiring relevance is currently lower. B's role relevance cannot overcome its overlap without a deeper real configuration problem. C is not given artificial preference for being distinctive. BMO's advanced case-study process does not drive the choice; the current Extreme Networks and Neon One themes do.

## Scope chosen before implementation

Build `temporal-customer-audiences`: authoritative person IDs and normalized profile facts are inputs. Two finite rules exercise positive activity and absence of observed activity. Preserve immutable as-known generations, compute historical restatements separately, and maintain current membership from changed subjects plus scheduled time boundaries. A small synthetic destination applies membership deltas so corrections can be checked end to end.

The decisive overlap test is executable: **advance the clock without ingesting a row and obtain the correct exits/entries; then deliver a late correction, restate a past audience without rewriting its original generation or exporting that historical result, and prove incremental results equal an independent full evaluation.** None of the existing four demonstrates that combination.

Python, SQLite window queries and a separately coded Python oracle are enough. SQLite supplies reproducible relational state and atomic generations; it is not a claimed distributed warehouse. No identity resolver, consent engine, messaging executor, AI agent, cloud imitation, dbt wrapper, broker or approval platform is built. Destination sequencing is supporting verification of audience deltas, not another durable integration product.

The fifth project must remain subordinate to these boundaries. More source types, vendors and architecture boxes would dilute its reason to exist.
