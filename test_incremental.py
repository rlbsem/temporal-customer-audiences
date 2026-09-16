import random
from concurrent.futures import ThreadPoolExecutor

import pytest

from temporal_audiences.contracts import DAY, DEFAULT_RULES, Refused
from temporal_audiences.engine import build
from temporal_audiences.fixtures import BASE, fact, population
from temporal_audiences.oracle import full_evaluation, full_members


def test_sparse_correction_reevaluates_one_subject_and_equals_full_oracle(store):
    store.ingest("seed", population())
    before = build(store, "before", BASE + 3 * DAY)
    store.ingest("correct", [fact("activity", "use-b-1", "person0001", 2, revision=2, retracted=True)])
    after = build(store, "after", BASE + 3 * DAY)
    assert after["maintenance"]["evaluated_people"] == 1
    assert after["maintenance"]["reused_people"] == 119
    assert after["people"]["person0002"] == before["people"]["person0002"]
    assert {tuple(v) for v in after["members"]} == full_members(store, BASE + 3 * DAY, store.head(), after["rules"])


def test_rule_change_invalidates_whole_population(store):
    store.ingest("seed", population(12))
    build(store, "before", BASE + 3 * DAY)
    result = build(store, "stricter", BASE + 3 * DAY, rules={**DEFAULT_RULES, "minimum_events": 3})
    assert result["maintenance"]["strategy"] == "full" and result["maintenance"]["evaluated_people"] == 12
    assert not any(v[0] == "engaged_trial" for v in result["members"])
    assert any(v["op"] == "remove" for v in result["bundle"]["changes"])


def test_code_change_invalidates_cached_features(store, monkeypatch):
    store.ingest("seed", population(9))
    build(store, "before", BASE)
    monkeypatch.setattr("temporal_audiences.engine.implementation_hash", lambda: "new-implementation")
    result = build(store, "after", BASE)
    assert result["maintenance"]["strategy"] == "full" and result["maintenance"]["evaluated_people"] == 9


def test_long_clock_jump_and_unchanged_interval_equal_full_evaluation(store):
    store.ingest("seed", population(12))
    build(store, "start", BASE + 3 * DAY)
    unchanged = build(store, "second", BASE + 3 * DAY + 1)
    assert unchanged["maintenance"]["evaluated_people"] == 0
    jumped = build(store, "jump", BASE + 100 * DAY)
    assert {tuple(v) for v in jumped["members"]} == full_members(store, BASE + 100 * DAY, store.head(), DEFAULT_RULES)
    assert all(v[0] == "quiet_trial" for v in jumped["members"])


@pytest.mark.parametrize("seed", [3, 17, 59, 211])
def test_randomized_corrections_retractions_and_clock_steps_match_independent_oracle(store, seed):
    rng = random.Random(seed)
    store.ingest("profiles", [fact("profile", f"p{i}", f"person{i}", 0) for i in range(8)])
    revisions = {}
    clock = BASE
    for step in range(32):
        clock += rng.randrange(0, 2 * DAY)
        if step % 4 != 0:
            person = rng.randrange(8)
            source = "profile" if step % 5 == 0 else "activity"
            key = f"{source}-{person}-{rng.randrange(3)}"
            revision = revisions.get(key, 0) + 1
            revisions[key] = revision
            value = rng.choice(["trial", "paid", "closed"]) if source == "profile" else rng.choice(["qualified", "noise"])
            row = fact(source, key, f"person{person}", rng.randrange(0, 25), value, revision, rng.random() < 0.2)
            store.ingest(f"batch-{step}", [row])
        generation = build(store, f"current-{step}", clock)
        assert {tuple(v) for v in generation["members"]} == full_members(store, clock, store.head(), DEFAULT_RULES)
        full = full_evaluation(store, clock, store.head(), DEFAULT_RULES)
        assert set(full) == set(generation["people"])
        for person, expected in full.items():
            assert generation["people"][person]["features"] == expected["features"]
            assert generation["people"][person]["membership"] == expected["membership"]
        if step % 8 == 0:
            historical_known = rng.randrange(0, store.head() + 1)
            historical_time = BASE + rng.randrange(0, 12) * DAY
            historical = build(store, f"historical-{step}", historical_time, known=historical_known, mode="historical")
            assert {tuple(v) for v in historical["members"]} == full_members(store, historical_time, historical_known, DEFAULT_RULES)
            assert store.get()["generation"] == generation["generation"]


def test_failed_recomputation_cannot_publish_partial_generation(store, monkeypatch):
    store.ingest("seed", population(6))
    original = build(store, "original", BASE)
    def fail(*args, **kwargs):
        raise RuntimeError("injected feature evaluation failure")
    monkeypatch.setattr("temporal_audiences.engine.evaluate", fail)
    with pytest.raises(RuntimeError, match="injected"):
        build(store, "broken", BASE + 3 * DAY)
    assert store.get() == original


def test_concurrent_same_run_key_returns_one_generation(store):
    store.ingest("seed", population(6))
    with ThreadPoolExecutor(4) as pool:
        results = list(pool.map(lambda _: build(store, "same-run", BASE + 3 * DAY), range(8)))
    assert all(r == results[0] for r in results)
    assert store.get()["generation"] == 1
    with pytest.raises(Refused, match="run_identity"):
        build(store, "same-run", BASE + 4 * DAY)
