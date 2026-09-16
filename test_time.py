import sqlite3

import pytest

from temporal_audiences.contracts import DAY, DEFAULT_RULES, Refused, utc
from temporal_audiences.engine import build
from temporal_audiences.fixtures import BASE, fact
from temporal_audiences.oracle import full_members
from temporal_audiences.store import transaction


def pairs(result):
    return {tuple(v) for v in result["members"]}


def test_original_as_known_and_restated_history_are_distinct_and_immutable(store):
    first = store.ingest("initial", [fact("profile", "p", "ada", 0), fact("activity", "a1", "ada", 1)])
    original = build(store, "original", BASE + 3 * DAY)
    store.ingest("late", [fact("activity", "a2", "ada", 2)])
    restated = build(store, "restated", BASE + 3 * DAY, mode="historical")
    known = build(store, "known", BASE + 3 * DAY, known=first, mode="historical")
    assert original["members"] == known["members"] == []
    assert pairs(restated) == {("engaged_trial", "ada")}
    assert restated["bundle"] is None and store.get() == original
    assert store.get(original["generation"]) == original
    with transaction(store.path) as c:
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            c.execute("UPDATE generations SET body='{}'")


def test_clock_alone_adds_absence_membership_and_expires_engagement(store):
    k = store.ingest("seed", [fact("profile", "p", "ada", 0), fact("activity", "a1", "ada", 1),
                              fact("activity", "a2", "ada", 2)])
    initial = build(store, "initial", BASE + 3 * DAY)
    silence = build(store, "silence", BASE + 5 * DAY)
    expired = build(store, "expired", BASE + 8 * DAY)
    assert pairs(initial) == {("engaged_trial", "ada")}
    assert pairs(silence) == {("engaged_trial", "ada"), ("quiet_trial", "ada")}
    assert pairs(expired) == {("quiet_trial", "ada")}
    assert initial["known_through"] == silence["known_through"] == expired["known_through"] == k
    assert expired["maintenance"]["changed_people"] == []
    assert expired["maintenance"]["timer_due_people"] == ["ada"]


@pytest.mark.parametrize("offset,included", [(-1, True), (0, False), (1, False)])
def test_exact_left_exclusive_window_boundary(store, offset, included):
    store.ingest("seed", [fact("profile", "p", "ada", 0), fact("activity", "a1", "ada", 1)])
    rules = {**DEFAULT_RULES, "minimum_events": 1}
    result = build(store, "test", BASE + 8 * DAY + offset, rules=rules)
    assert (("engaged_trial", "ada") in pairs(result)) is included


def test_future_activity_and_profile_transitions_trigger_without_new_data(store):
    store.ingest("seed", [fact("profile", "p", "ada", 0), fact("activity", "a1", "ada", 2),
                          fact("activity", "a2", "ada", 3), fact("profile", "paid", "ada", 4, "paid")])
    zero = build(store, "zero", BASE)
    two = build(store, "two", BASE + 2 * DAY)
    three = build(store, "three", BASE + 3 * DAY)
    four = build(store, "four", BASE + 4 * DAY)
    assert pairs(zero) == {("quiet_trial", "ada")}
    assert pairs(two) == set()
    assert pairs(three) == {("engaged_trial", "ada")}
    assert pairs(four) == set()
    assert len({v["known_through"] for v in [zero, two, three, four]}) == 1


def test_latest_revision_selected_before_business_time_filter(store):
    k1 = store.ingest("v1", [fact("profile", "p", "ada", 0)])
    store.ingest("v2", [fact("profile", "p", "ada", 10, revision=2)])
    now = build(store, "now", BASE + 5 * DAY)
    past_knowledge = build(store, "past", BASE + 5 * DAY, known=k1, mode="historical")
    assert now["people"]["ada"]["features"]["profile_state"] == "missing"
    assert pairs(now) == set() and pairs(past_knowledge) == {("quiet_trial", "ada")}
    later = build(store, "later", BASE + 10 * DAY)
    assert pairs(later) == {("quiet_trial", "ada")}


def test_retraction_removes_historical_evidence_without_erasing_earlier_knowledge(store):
    k1 = store.ingest("seed", [fact("profile", "p", "ada", 0), fact("activity", "a1", "ada", 1),
                              fact("activity", "a2", "ada", 2)])
    earlier = build(store, "earlier", BASE + 3 * DAY)
    store.ingest("withdraw", [fact("activity", "a2", "ada", 2, revision=2, retracted=True)])
    after = build(store, "after", BASE + 3 * DAY)
    assert pairs(earlier) == {("engaged_trial", "ada")} and pairs(after) == set()
    assert full_members(store, BASE + 3 * DAY, k1, DEFAULT_RULES) == pairs(earlier)
    assert after["bundle"]["changes"][0]["op"] == "remove"


def test_out_of_order_lower_revision_never_resurrects_retracted_fact(store):
    store.ingest("seed", [fact("profile", "p", "ada", 0), fact("activity", "a1", "ada", 1, revision=3, retracted=True)])
    initial = build(store, "initial", BASE + DAY)
    store.ingest("older-version", [fact("activity", "a1", "ada", 1, revision=2)])
    after = build(store, "after", BASE + DAY)
    assert after["members"] == initial["members"] and after["people"]["ada"]["features"]["engaged_events"] == 0


def test_ambiguous_profile_time_is_visible_and_excluded_until_resolved(store):
    store.ingest("conflict", [fact("profile", "p1", "ada", 0), fact("profile", "p2", "ada", 0, "paid")])
    ambiguous = build(store, "ambiguous", BASE)
    assert pairs(ambiguous) == set()
    assert ambiguous["people"]["ada"]["reasons"]["quiet_trial"] == "not_trial:ambiguous"
    store.ingest("resolve", [fact("profile", "p2", "ada", 0, "paid", revision=2, retracted=True)])
    resolved = build(store, "resolved", BASE)
    assert pairs(resolved) == {("quiet_trial", "ada")}


def test_missing_profile_is_not_assumed_trial(store):
    store.ingest("activity-only", [fact("activity", "a1", "ada", 1), fact("activity", "a2", "ada", 2)])
    result = build(store, "missing", BASE + 3 * DAY)
    assert pairs(result) == set() and result["people"]["ada"]["features"]["profile_state"] == "missing"


def test_current_cannot_publish_past_time_or_old_knowledge(store):
    first = store.ingest("first", [fact("profile", "p", "ada", 0)])
    build(store, "now", BASE + 10 * DAY)
    store.ingest("next", [fact("activity", "a1", "ada", 2)])
    with pytest.raises(Refused, match="monotone_clock"):
        build(store, "backdated", BASE + DAY)
    with pytest.raises(Refused, match="latest_knowledge"):
        build(store, "old-known", BASE + 11 * DAY, known=first)
    with pytest.raises(Refused, match="future_knowledge"):
        build(store, "future", BASE + 11 * DAY, known=99)


def test_timezone_normalization_and_whole_seconds():
    assert utc("2026-01-01T00:00:00Z") == utc("2025-12-31T19:00:00-05:00")
    with pytest.raises(Refused):
        utc("2026-01-01T00:00:00")
    with pytest.raises(Refused):
        utc("2026-01-01T00:00:00.500Z")
    with pytest.raises(Refused):
        utc("2026-01-01T00:00:00+00:00:00.500")
