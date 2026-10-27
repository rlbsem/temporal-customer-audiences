# Executed audience operations evidence

The new operating layer preserves the original two-time evaluator. These records describe synthetic execution against local PostgreSQL, SQLite, an independently stored HTTP receiver and Chromium. They are not marketing-platform acceptance or customer results.

`run02` is the current source-matching capture. The first Windows capture, `run01`, remains byte-for-byte archived: its dependency-lock fingerprint used CRLF checkout bytes and failed the separate Linux current-source gate. [The compatibility observation](source-checkout-compatibility.json) establishes that only newline representation differed. Dependencies and business behavior were unchanged. A fresh complete run with canonical source bytes replaces that record as the current gate; the checker still requires exact hashes and has no newline exception.

- [Executed scenario and source/receiver snapshot](run02/acceptance.json): exact expected/observed values for 36 assertions; admitted batches, publication versions, permission revisions, frozen intents, independent effects, business records and request outcomes.
- [Execution and regression record](run02/verification.json): source hashes, source revision, environment, named test cases, independently verified receipts and original-file preservation.
- [Browser and screenshot provenance](run02/browser/browser.json): 109 assertions, 50 responsive states, 20 automated accessibility states, source/image hashes and actual browser version. Initially clipped contrast checks are scrolled into view and rechecked; unresolved findings fail capture.
- [Artifact SHA-256 inventory](run02/artifact-integrity.json): every file in this fresh execution set, excluding the inventory itself.
- [Original-file preservation inventory](original-files.json): 24 original engine, test and archived-evidence files bound to base main `01f3a180402695689aad115a25db1261ad0c824e`. Original Git blob bytes are retained. Historical records were not regenerated or edited.
- [Fresh original-engine proof](run02/original-demo/report.md): an additional execution of the existing demonstration, stored separately from its historical evidence.
- [Native and container CI record](ci-execution.json): actual successful source-checkpoint jobs, with prior failed container attempts preserved by URL and findings. Final-head status remains visible in the pull request.
- [Wheel asset verification](wheel-verification.json): actual wheel build, archive checks and SQL/UI asset fingerprints. This is packaging verification, separate from the source-based runtime acceptance.

The independent raw-source oracle compares **164 historical decision rows and 20 current eligibility rows**, with zero differences. Atlas and Nova retain different identities for local person `100`. Current membership is person × audience, not a count of unique customers; historical confirmed effects are not current active destination membership.

The scenario deliberately leaves blocked, uncertain and exhausted histories visible. It verifies three bounded POST reservations, unknown-readback exhaustion without an unsafe POST, a genuine worker exit after receiver commit, historical reconciliation after permission withdrawal, protective removals, and a receiver sequence fence that prevents old delivery from resurrecting membership.

## Inspect the actual console

![Original/restated audience decisions and current permission](run02/browser/operations-desktop.png)

[Delivery and recovery desktop capture](run02/browser/delivery-desktop.png) · [Mobile source-and-controls capture](run02/browser/operations-mobile.png)

The screenshots come directly from the real running console. They contain no fabricated overlays or manually changed outcomes. The read-only receipt control queries both the receiver receipt and its separate persisted business record; it does not authorize a new action.

## Recheck

```bash
python scripts/check_operations.py
```

This checks the captured source bytes, historical preservation, journal/payload hashes, independently stored effects and records, oracle results, browser assertions, resolved accessibility findings, screenshot dimensions/hashes, local documentation links and absence of private credential fields in the public JSON. For a new actual execution use the [full verification procedure](../../activation-assurance.md#reproduce-and-inspect), always writing to new paths.

Docker is not installed on the local Windows execution host. The separate Linux Compose lane passed startup, live read-only verification, the 109-assertion browser check and post-teardown project-resource absence checks. Current CI results are visible in the draft pull request; local execution alone is not evidence that Docker ran.

## Boundaries

No native vendor API, prospect communication, paid service or production deployment is exercised. The controlled business clock represents January 2026; execution timestamps record when these synthetic checks actually ran. Logical database separation shares one PostgreSQL server, so this is not hardware disaster recovery. Scoped Python capabilities are not production authentication or tenant RLS. The operational bridge fully replays each brand into a disposable SQLite cache; the original selective-maintenance evidence remains separate.
