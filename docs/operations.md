# Reproduce and inspect

## Complete verification

Create a Python 3.12 virtual environment from the extracted repository root. Activate with `.venv\Scripts\Activate.ps1` in PowerShell or `source .venv/bin/activate` in bash. Then:

```bash
python -m pip install -r requirements.lock
python -m pip install --no-deps --no-build-isolation -e .
python scripts/verify.py
```

The runtime uses the standard library. Test/build versions are pinned, not claimed as the newest releases. Verification checks installed/source parity, dependency consistency, lint, tests and the complete demo. It creates unique disposable directories under ignored `work/` and never resets another run's database. It regenerates evidence under `docs/evidence`.

`python scripts/demo.py` runs only the asserted temporal story. Generated lineage IDs, receipt times and scratch paths vary. Semantic outcomes and test assertions are reproducible; cross-run files are not promised to have identical bytes.

## Inspect the two time coordinates

This is a local library/CLI harness. The following creates synthetic inputs and shows the original-versus-restated distinction:

```python
from temporal_audiences.store import Store
from temporal_audiences.engine import build
from temporal_audiences.fixtures import BASE, fact
from temporal_audiences.contracts import DAY

store = Store("work/example/audiences.sqlite")
k1 = store.ingest("initial", [
    fact("profile", "profile-ada", "ada", 0),
    fact("activity", "use-1", "ada", 1),
])
original = build(store, "original", BASE + 3 * DAY, known=k1)
store.ingest("late", [fact("activity", "use-2", "ada", 2)])
restated = build(store, "restated", BASE + 3 * DAY, mode="historical")
assert original["members"] != restated["members"]
assert restated["bundle"] is None
assert store.get()["generation"] == original["generation"]
```

Publish a new **current** generation explicitly to apply new knowledge to current membership. Advance its clock explicitly to process scheduled boundaries even without ingestion. There is no background daemon: a real deployment must call this operation at the required cadence or next due boundary. Take the minimum non-null boundary across customer `features.next_due` and generation `activity_coverage.next_due`. Delayed scheduling delays publication, not the query's definition; the destination does not expire itself.

## Inspect computed quiet versus export eligibility

`members` is the observed-fact audience; use `activation_members` for the synthetic export projection. Historical `activation_members` describes hypothetical eligibility and is never an export bundle. Coverage is required only for quiet. For example, following the earlier snippet:

```python
quiet = build(store, "quiet", BASE + 5 * DAY)
assert ["quiet_trial", "ada"] in quiet["members"]
assert ["quiet_trial", "ada"] not in quiet["activation_members"]
store.ingest_coverage("explicit-synthetic-coverage", {
    "revision": 1,
    "covered_after": BASE + 2 * DAY,
    "covered_through": BASE + 5 * DAY,
    "retracted": False,
})
covered = build(store, "covered", BASE + 5 * DAY)
expired = build(store, "coverage-expired", BASE + 5 * DAY + 1)
assert ["quiet_trial", "ada"] in covered["activation_members"]
assert ["quiet_trial", "ada"] not in expired["activation_members"]
assert covered["people"] == expired["people"]
```

An assertion covers the whole synthetic activity source, not just Ada. Admit it only as an explicit test input; do not derive it from the newest event timestamp. The highest revision replaces the complete interval at its admission K. To withdraw it, admit a higher revision with `retracted=True`. Batch IDs share the customer ledger namespace. Preserve the exact assertion for retries. The gate uses the supplied business clock and requires coverage through that clock, with no lag allowance.

Existing version-1.0 generations remain readable. A new current generation compares against their previously exported `members`, removes uncovered quiet entries, and records the new `activation_members`. Do not manually reinterpret old receipts or rewrite old generation files.

Use stable run keys for exact build requests. A retry with the same resolved clock, knowledge cutoff, rule configuration and implementation returns the existing generation without reactivating it. Reusing the key for different inputs conflicts. When new data has arrived, omitting `known` resolves to a different head; supply the original cutoff for an exact retry rather than silently changing its meaning.

## Read the proof

- `temporal-proof.json`: complete generations, profile states, event counts, fact/revision references, evaluation coordinates, due boundaries, correction deltas and destination receipts. `coverage_safety` contains the separate eight-generation coverage/expiry/correction story.
- `timeline.csv`: compact business-time/knowledge-time comparison. Day numbers are offsets from 2026-01-01 UTC, not calendar day-of-month.
- `verification.json`: exact local environment, test counts, installation mode and source hashes.
- `inspection.json`: public portfolio commits and observed existing-repository CI job metadata used before selection. It is not CI evidence for this new project.

The demonstration intentionally injects a phantom destination member at the end to show drift. That discrepancy remains in its generated report. It is not a failed temporal computation and is not silently repaired to make the ending look clean.

## Respond to failures

| Failure | Correct response |
|---|---|
| Fact revision conflict | Correct the upstream identifier/revision; do not overwrite the immutable row |
| Person-owner change | Resolve identity outside this engine; do not silently move a fact between dependency sets |
| Ambiguous profile at the same time | Inspect both cited facts and admit a proper correction/retraction |
| Current publication requests past time/knowledge | Run a historical computation; it cannot export or replace the active generation |
| Changed rule/code | Expect a full recomputation; retain the previous generation for comparison |
| Destination missing a parent | Deliver committed current bundles in parent order; historical generation IDs may appear between them |
| Destination drift | Inspect missing/extra members and stop applying subsequent deltas until a reviewed repair/rebaseline is performed |
| Missing, stale or incomplete coverage | Inspect `activity_coverage.failures` and its selected assertion; quiet stays computed but cannot export until a new current evaluation satisfies the full interval |

Automatic drift repair, privacy erasure and operational retries are deliberately outside this local proof. Retractions are business-data corrections and preserve history; they are not deletion of personal information.

## Before publishing

Review the overlap decision, generated safety counterexamples and limitations. Run verification from the extracted archive. Review the MIT license, then publish to a new repository yourself and observe both CI jobs before claiming hosted success. No remote repository, paid service or fabricated commit history was created by this build.
