import random
import sqlite3

import pytest

from temporal_audiences.contracts import DAY, DEFAULT_RULES, Refused, canonical, digest, member_hash
from temporal_audiences.destination import Destination
from temporal_audiences.engine import build
from temporal_audiences.fixtures import BASE, fact, population
from temporal_audiences.oracle import full_activation_members
from temporal_audiences.store import transaction


def assertion(revision=1, after=BASE, through=BASE + 5 * DAY, retracted=False):
    return {"revision": revision, "covered_after": after, "covered_through": through, "retracted": retracted}


def check_oracle(store, generation):
    assert {tuple(v) for v in generation["activation_members"]} == full_activation_members(
        store, generation["valid_at"], generation["known_through"], generation["rules"])


def test_missing_coverage_suppresses_only_absence_activation(store, tmp_path):
    store.ingest("seed", [fact("profile", "p", "ada", 0), fact("activity", "a1", "ada", 1),
                          fact("activity", "a2", "ada", 2)])
    result = build(store, "quiet-and-engaged", BASE + 5 * DAY)
    assert result["members"] == [["engaged_trial", "ada"], ["quiet_trial", "ada"]]
    assert result["activation_members"] == [["engaged_trial", "ada"]]
    assert result["activity_coverage"]["failures"] == ["missing_coverage"]
    target = Destination(tmp_path / "destination.sqlite")
    target.apply(result["bundle"])
    assert target.members() == {("engaged_trial", "ada")} and target.reconcile(result)["matched"]
    check_oracle(store, result)


@pytest.mark.parametrize("after,through,failure", [
    (BASE + 1, BASE + 3 * DAY, "incomplete_window"),
    (BASE, BASE + 3 * DAY - 1, "coverage_behind_clock"),
    (BASE + 3 * DAY, BASE + 4 * DAY, "incomplete_window"),
])
def test_incomplete_or_stale_assertion_cannot_activate_quiet(store, after, through, failure):
    store.ingest("profile", [fact("profile", "p", "ada", 0)])
    store.ingest_coverage("coverage", assertion(after=after, through=through))
    result = build(store, "unsafe", BASE + 3 * DAY)
    assert result["members"] == [["quiet_trial", "ada"]] and result["activation_members"] == []
    assert result["activity_coverage"]["failures"] == [failure] and result["bundle"]["changes"] == []
    check_oracle(store, result)


def test_clock_crosses_coverage_boundaries_with_reused_customer_decisions(store, tmp_path):
    store.ingest("profile", [fact("profile", "p", "ada", 0)])
    store.ingest_coverage("coverage", assertion())
    target = Destination(tmp_path / "destination.sqlite")
    first = None
    for i, (clock, eligible, due) in enumerate([
        (BASE + 3 * DAY - 1, False, BASE + 3 * DAY),
        (BASE + 3 * DAY, True, BASE + 5 * DAY + 1),
        (BASE + 3 * DAY + 1, True, BASE + 5 * DAY + 1),
        (BASE + 5 * DAY - 1, True, BASE + 5 * DAY + 1),
        (BASE + 5 * DAY, True, BASE + 5 * DAY + 1),
        (BASE + 5 * DAY + 1, False, None),
    ]):
        generation = build(store, f"clock-{i}", clock)
        gate = generation["activity_coverage"]
        assert gate["eligible"] is eligible and gate["next_due"] == due
        assert gate["evaluated_at"] == clock and generation["known_through"] == 2
        assert generation["members"] == [["quiet_trial", "ada"]]
        if first:
            assert generation["people"] == first["people"]
            assert generation["maintenance"]["evaluated_people"] == 0
        first = first or generation
        target.apply(generation["bundle"])
        assert target.reconcile(generation)["matched"]
        assert target.members() == ({("quiet_trial", "ada")} if eligible else set())
        check_oracle(store, generation)
    assert generation["bundle"]["changes"] == [{"segment": "quiet_trial", "person_id": "ada", "op": "remove",
            "reason": "coverage:coverage_behind_clock", "decision_evaluated_at": BASE + 5 * DAY + 1}]
    assert target.apply(generation["bundle"]) == "duplicate"


def test_late_coverage_and_corrections_restate_safety_without_mutating_history(store, tmp_path):
    store.ingest("profile", [fact("profile", "p", "ada", 0)])
    original = build(store, "original", BASE + 3 * DAY)
    target = Destination(tmp_path / "destination.sqlite")
    target.apply(original["bundle"])
    k2 = store.ingest_coverage("late", assertion())
    historical = build(store, "restated", BASE + 3 * DAY, mode="historical")
    as_known = build(store, "as-known", BASE + 3 * DAY, known=1, mode="historical")
    assert historical["activation_members"] == [["quiet_trial", "ada"]] and historical["bundle"] is None
    assert as_known["activity_coverage"] == original["activity_coverage"] and store.get() == original
    current = build(store, "current", BASE + 3 * DAY)
    target.apply(current["bundle"])
    assert current["maintenance"]["evaluated_people"] == 0
    # Higher revision moves the covered interval forward: never fall back to the old, fitting interval.
    store.ingest_coverage("corrected", assertion(3, after=BASE + DAY))
    corrected = build(store, "corrected", BASE + 3 * DAY)
    target.apply(corrected["bundle"])
    assert corrected["activation_members"] == [] and target.reconcile(corrected)["matched"]
    store.ingest_coverage("older-delivery", assertion(2))
    lower = build(store, "lower", BASE + 3 * DAY)
    assert lower["activity_coverage"]["evidence"]["revision"] == 3 and lower["activation_members"] == []
    target.apply(lower["bundle"])
    old_k = build(store, "old-k", BASE + 3 * DAY, known=k2, mode="historical")
    assert old_k["activity_coverage"] == historical["activity_coverage"]
    for saved in (original, historical, current):
        assert store.get(saved["generation"]) == saved
    for generation in (original, historical, as_known, current, corrected, lower, old_k):
        check_oracle(store, generation)
    with pytest.raises(Refused, match="out_of_order"):
        target.apply(current["bundle"])


def test_retracted_coverage_cannot_be_resurrected_by_lower_revision(store):
    store.ingest("profile", [fact("profile", "p", "ada", 0)])
    k = store.ingest_coverage("valid", assertion())
    prior = build(store, "prior", BASE + 3 * DAY)
    store.ingest_coverage("withdraw", assertion(3, retracted=True))
    store.ingest_coverage("late-old", assertion(2))
    after = build(store, "after", BASE + 3 * DAY)
    assert after["activity_coverage"]["failures"] == ["retracted_coverage"]
    assert after["activity_coverage"]["next_due"] is None and after["activation_members"] == []
    old = build(store, "old", BASE + 3 * DAY, known=k, mode="historical")
    assert old["activation_members"] == prior["activation_members"] == [["quiet_trial", "ada"]]
    check_oracle(store, after)


def test_rule_change_rechecks_whole_required_interval(store):
    store.ingest("profile", [fact("profile", "p", "ada", 0)])
    store.ingest_coverage("valid", assertion())
    before = build(store, "three-days", BASE + 3 * DAY)
    after = build(store, "four-days", BASE + 3 * DAY, rules={**DEFAULT_RULES, "quiet_window": 4 * DAY})
    assert before["activation_members"] == [["quiet_trial", "ada"]] and after["activation_members"] == []
    assert after["activity_coverage"]["failures"] == ["incomplete_window"]
    check_oracle(store, after)


def test_coverage_admission_is_idempotent_atomic_and_immutable(store):
    row = assertion()
    assert store.ingest_coverage("coverage", row) == store.ingest_coverage("coverage", row) == 1
    store.ingest_coverage("repeat", row)
    with transaction(store.path, False) as c:
        assert c.execute("SELECT COUNT(*) FROM coverage").fetchone()[0] == 1
    with pytest.raises(Refused, match="revision_conflict"):
        store.ingest_coverage("bad", {**row, "covered_after": BASE + 1})
    assert store.head() == 2
    with pytest.raises(Refused, match="batch_identity_conflict"):
        store.ingest("coverage", [fact("profile", "p", "ada", 0)])
    store.ingest("profile", [fact("profile", "p", "ada", 0)])
    with pytest.raises(Refused, match="batch_identity_conflict"):
        store.ingest_coverage("profile", row)
    with transaction(store.path) as c:
        for sql in ("UPDATE coverage SET covered_through=0", "DELETE FROM coverage"):
            with pytest.raises(sqlite3.IntegrityError, match="immutable coverage"):
                c.execute(sql)


def test_pre_gate_generation_is_restricted_on_upgrade_without_rewriting_it(store, tmp_path):
    store.ingest("profile", [fact("profile", "p", "ada", 0)])
    clock = BASE + 3 * DAY
    with transaction(store.path) as c:
        lineage = c.execute("SELECT value FROM meta WHERE key='lineage'").fetchone()[0]
        # Minimal stored version-1.0 generation: all computed members were exported.
        body = {"contract": 1, "lineage": lineage, "generation": 1, "parent": 0,
                "valid_at": clock, "known_through": 1, "rule_hash": digest(DEFAULT_RULES),
                "before_hash": member_hash(set()), "after_hash": member_hash({("quiet_trial", "ada")}),
                "changes": [{"segment": "quiet_trial", "person_id": "ada", "op": "add",
                             "reason": "no_observed_events_in_window", "decision_evaluated_at": clock}]}
        old = {"generation": 1, "mode": "current", "valid_at": clock, "known_through": 1,
               "implementation": "version-1-0", "rules": DEFAULT_RULES, "lineage": lineage,
               "people": {"ada": {"membership": {"engaged_trial": False, "quiet_trial": True}}},
               "members": [["quiet_trial", "ada"]], "bundle": {**body, "seal": digest(body)}}
        c.execute("INSERT INTO generations VALUES (?,?,?,?,?)", (1, "legacy", "legacy-request", "current", canonical(old)))
        c.execute("UPDATE meta SET value='1' WHERE key='active'")
    target = Destination(tmp_path / "destination.sqlite")
    target.apply(old["bundle"])
    assert target.reconcile(old)["matched"]
    new = build(store, "upgraded", clock)
    assert new["members"] == old["members"] and new["activation_members"] == []
    assert new["bundle"]["changes"][0]["op"] == "remove"
    target.apply(new["bundle"])
    assert target.reconcile(new)["matched"] and target.members() == set()
    assert store.get(1) == old


@pytest.mark.parametrize("changes", [{"revision": True}, {"covered_after": 1.5}, {"covered_through": BASE},
                                    {"retracted": "false"}, {"source": "invented"}])
def test_invalid_coverage_refused_before_writing(store, changes):
    with pytest.raises(Refused):
        store.ingest_coverage("bad", {**assertion(), **changes})
    assert store.head() == 0


@pytest.mark.parametrize("seed", [13, 71])
def test_mixed_coverage_revisions_facts_clocks_and_historical_cuts_match_oracle(store, tmp_path, seed):
    rng = random.Random(seed)
    store.ingest("population", population(9))
    target = Destination(tmp_path / "destination.sqlite")
    clock = BASE
    for step in range(24):
        clock += rng.randrange(0, DAY)
        if step % 3 == 0:
            start = BASE + rng.randrange(0, 6) * DAY
            store.ingest_coverage(f"coverage-{step}", assertion(step + 1, start, start + rng.randrange(1, 12) * DAY,
                                                              retracted=step % 9 == 0))
        elif step % 3 == 1:
            store.ingest(f"activity-{step}", [fact("activity", "correction", "person0001", rng.randrange(0, 10),
                                                  revision=step + 1, retracted=step % 2 == 0)])
        current = build(store, f"current-{step}", clock)
        check_oracle(store, current)
        target.apply(current["bundle"])
        assert target.reconcile(current)["matched"]
        historical = build(store, f"history-{step}", BASE + rng.randrange(0, 12) * DAY,
                           known=rng.randrange(0, store.head() + 1), mode="historical")
        check_oracle(store, historical)
        assert historical["bundle"] is None and store.get() == current
