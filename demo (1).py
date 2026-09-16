"""Executed proof of original versus restated history, silence-driven expiry and sparse correction."""
import csv
import json
from pathlib import Path
from uuid import uuid4

from .contracts import DAY, Refused
from .destination import Destination
from .engine import build
from .fixtures import BASE, fact, population
from .oracle import full_activation_members, full_members
from .store import Store, transaction


def coverage_story(workspace):
    store = Store(workspace / "coverage.sqlite")
    destination = Destination(workspace / "coverage-destination.sqlite")
    store.ingest("facts", [fact("profile", "p", "ada", 0), fact("activity", "a1", "ada", 1),
                           fact("activity", "a2", "ada", 2)])
    clock = BASE + 5 * DAY
    original = build(store, "uncovered", clock)
    destination.apply(original["bundle"])
    assertion = {"revision": 1, "covered_after": BASE + 2 * DAY, "covered_through": clock, "retracted": False}
    store.ingest_coverage("late-coverage", assertion)
    restated = build(store, "coverage-restated", clock, mode="historical")
    as_known = build(store, "coverage-as-known", clock, known=1, mode="historical")
    assert original["activity_coverage"] == as_known["activity_coverage"]
    assert store.get() == original and restated["bundle"] is None
    covered = build(store, "covered-current", clock)
    destination.apply(covered["bundle"])
    expired = build(store, "coverage-expired", clock + 1)
    destination.apply(expired["bundle"])
    assert expired["known_through"] == covered["known_through"]
    assert expired["maintenance"]["evaluated_people"] == 0 and expired["people"] == original["people"]
    assert expired["members"] == covered["members"] == [["engaged_trial", "ada"], ["quiet_trial", "ada"]]
    assert expired["activation_members"] == original["activation_members"] == [["engaged_trial", "ada"]]
    assert covered["activation_members"] == restated["activation_members"] == covered["members"]
    store.ingest_coverage("corrected-start", {**assertion, "revision": 2, "covered_after": BASE + 3 * DAY,
                                             "covered_through": BASE + 6 * DAY})
    incomplete = build(store, "corrected-incomplete", clock + 1)
    assert incomplete["activity_coverage"]["failures"] == ["incomplete_window"]
    destination.apply(incomplete["bundle"])
    store.ingest_coverage("repaired", {**assertion, "revision": 3, "covered_through": BASE + 6 * DAY})
    repaired = build(store, "repaired", clock + 1)
    destination.apply(repaired["bundle"])
    assert repaired["activation_members"] == covered["activation_members"]
    store.ingest_coverage("withdrawn", {**assertion, "revision": 4, "retracted": True})
    withdrawn = build(store, "coverage-withdrawn", clock + 1)
    destination.apply(withdrawn["bundle"])
    assert withdrawn["activation_members"] == original["activation_members"]
    assert store.get(covered["generation"]) == covered and store.get(restated["generation"]) == restated
    generations = [original, restated, as_known, covered, expired, incomplete, repaired, withdrawn]
    for generation in generations:
        assert {tuple(v) for v in generation["activation_members"]} == full_activation_members(
            store, generation["valid_at"], generation["known_through"], generation["rules"])
    assert destination.reconcile(withdrawn)["matched"]
    return {"generations": generations, "destination_receipts": destination.receipts(),
            "independent_activation_oracle_match": True, "destination_reconciliation": destination.reconcile(withdrawn)}


def run(workspace, output):
    workspace, output = Path(workspace) / uuid4().hex, Path(output)
    output.mkdir(parents=True, exist_ok=True)
    store = Store(workspace / "audiences.sqlite")
    destination = Destination(workspace / "destination.sqlite")
    known1 = store.ingest("initial", [fact("profile", "profile-ada", "ada", 0), fact("activity", "use-1", "ada", 1)])
    original = build(store, "original", BASE + 3 * DAY)
    destination.apply(original["bundle"])
    known2 = store.ingest("late", [fact("activity", "use-2", "ada", 2)])
    restated = build(store, "restated", BASE + 3 * DAY, mode="historical")
    as_known = build(store, "as-known", BASE + 3 * DAY, known=known1, mode="historical")
    assert original["members"] == as_known["members"] and original["members"] != restated["members"]
    assert store.get()["generation"] == original["generation"] and restated["bundle"] is None
    corrected = build(store, "corrected-current", BASE + 3 * DAY)
    destination.apply(corrected["bundle"])
    # No ingestion occurs across either of these transitions.
    silence = build(store, "silence", BASE + 5 * DAY)
    destination.apply(silence["bundle"])
    expired = build(store, "expired", BASE + 8 * DAY)
    destination.apply(expired["bundle"])
    assert silence["known_through"] == expired["known_through"] == known2
    assert ["quiet_trial", "ada"] in silence["members"] and ["engaged_trial", "ada"] not in expired["members"]
    # A correction withdraws a previously observed activity fact. Historical generations remain intact.
    store.ingest("retraction", [fact("activity", "use-2", "ada", 2, revision=2, retracted=True)])
    withdrawn = build(store, "withdrawn-history", BASE + 3 * DAY, mode="historical")
    assert ["engaged_trial", "ada"] not in withdrawn["members"]
    assert store.get(restated["generation"])["members"] == restated["members"]
    # Future effective profile change is already known; the clock, not new ingestion, triggers its exit.
    store.ingest("scheduled-close", [fact("profile", "close-ada", "ada", 10, "closed")])
    scheduled = build(store, "schedule", BASE + 9 * DAY)
    destination.apply(scheduled["bundle"])
    closed = build(store, "close", BASE + 10 * DAY)
    destination.apply(closed["bundle"])
    assert closed["members"] == [] and destination.reconcile(closed)["matched"]
    out_of_order = None
    try:
        destination.apply(corrected["bundle"])
    except Refused as exc:
        out_of_order = str(exc)
    assert out_of_order == "out_of_order_delta"
    with transaction(destination.path) as c:
        c.execute("INSERT INTO members VALUES ('engaged_trial','phantom')")
    drift = destination.reconcile(closed)
    assert not drift["matched"] and drift["extra"] == [["engaged_trial", "phantom"]]
    runs = [original, restated, as_known, corrected, silence, expired, withdrawn, scheduled, closed]
    for item in runs:
        assert {tuple(v) for v in item["members"]} == full_members(store, item["valid_at"], item["known_through"], item["rules"])
        assert {tuple(v) for v in item["activation_members"]} == full_activation_members(
            store, item["valid_at"], item["known_through"], item["rules"])
    sparse_store = Store(workspace / "sparse.sqlite")
    sparse_store.ingest("population", population())
    sparse_before = build(sparse_store, "before", BASE + 3 * DAY)
    sparse_store.ingest("one-correction", [fact("activity", "use-b-1", "person0001", 2, revision=2, retracted=True)])
    sparse_after = build(sparse_store, "after", BASE + 3 * DAY)
    assert sparse_after["maintenance"]["evaluated_people"] == 1
    assert {tuple(v) for v in sparse_after["members"]} == full_members(sparse_store, BASE + 3 * DAY,
                                                                     sparse_store.head(), sparse_after["rules"])
    proof = {"scope": "synthetic local temporal data computation; no campaign sends or vendor connections",
             "timeline": runs, "out_of_order_delta_refusal": out_of_order, "destination_drift": drift,
             "coverage_safety": coverage_story(workspace),
             "destination_receipts": destination.receipts(),
             "sparse_correction": {"before": sparse_before, "after": sparse_after,
                                   "independent_full_oracle_match": True}, "all_timeline_oracle_checks_passed": True}
    (output / "temporal-proof.json").write_text(json.dumps(proof, indent=2) + "\n", encoding="utf-8")
    with (output / "timeline.csv").open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["scenario", "mode", "business_day", "knowledge_commit", "computed_memberships",
                         "activation_eligible_memberships", "evaluated_people"])
        for label, row in zip(["original", "restated", "as-known", "corrected-current", "silence", "expired", "retracted-history", "scheduled", "closed"], runs):
            writer.writerow([label, row["mode"], (row["valid_at"] - BASE) // DAY, row["known_through"],
                             ";".join(v[0] + ":" + v[1] for v in row["members"]),
                             ";".join(v[0] + ":" + v[1] for v in row["activation_members"]), row["maintenance"]["evaluated_people"]])
    (output / "report.md").write_text("""# Executed temporal audience proof

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
""", encoding="utf-8")
    return proof
