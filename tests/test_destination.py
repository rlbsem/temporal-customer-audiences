import copy

import pytest

from temporal_audiences.contracts import DAY, Refused, digest
from temporal_audiences.destination import Destination
from temporal_audiences.engine import build
from temporal_audiences.fixtures import BASE, fact
from temporal_audiences.store import transaction


def generations(store):
    store.ingest("seed", [fact("profile", "p", "ada", 0), fact("activity", "a1", "ada", 1), fact("activity", "a2", "ada", 2)])
    first = build(store, "first", BASE + 3 * DAY)
    second = build(store, "second", BASE + 8 * DAY)
    return first, second


def test_membership_deltas_match_full_sets_and_old_delivery_cannot_resurrect(store, tmp_path):
    first, second = generations(store)
    target = Destination(tmp_path / "destination.sqlite")
    target.apply(first["bundle"])
    assert target.reconcile(first)["matched"]
    target.apply(second["bundle"])
    assert target.reconcile(second)["matched"] and target.apply(second["bundle"]) == "duplicate"
    with pytest.raises(Refused, match="out_of_order"):
        target.apply(first["bundle"])
    reopened = Destination(target.path)
    assert reopened.members() == {tuple(v) for v in second["activation_members"]}


def test_missing_parent_delta_is_refused(store, tmp_path):
    _, second = generations(store)
    target = Destination(tmp_path / "destination.sqlite")
    with pytest.raises(Refused, match="out_of_order"):
        target.apply(second["bundle"])
    assert target.members() == set()


def test_tampered_delta_and_wrong_result_hash_do_not_partially_apply(store, tmp_path):
    first, second = generations(store)
    target = Destination(tmp_path / "destination.sqlite")
    target.apply(first["bundle"])
    bad = copy.deepcopy(second["bundle"])
    bad["after_hash"] = "wrong"
    with pytest.raises(Refused, match="seal"):
        target.apply(bad)
    bad["seal"] = digest({k: v for k, v in bad.items() if k != "seal"})
    with pytest.raises(Refused, match="result_mismatch"):
        target.apply(bad)
    assert target.reconcile(first)["matched"] and len(target.receipts()) == 1


def test_destination_drift_detected_before_delivery_and_on_retry(store, tmp_path):
    first, second = generations(store)
    target = Destination(tmp_path / "destination.sqlite")
    target.apply(first["bundle"])
    with transaction(target.path) as c:
        c.execute("INSERT INTO members VALUES ('quiet_trial','phantom')")
    assert target.reconcile(first)["extra"] == [["quiet_trial", "phantom"]]
    with pytest.raises(Refused, match="drift"):
        target.apply(first["bundle"])
    with pytest.raises(Refused, match="drift"):
        target.apply(second["bundle"])


def test_historical_generations_have_no_destination_contract(store, tmp_path):
    first, _ = generations(store)
    historical = build(store, "history", BASE, mode="historical")
    target = Destination(tmp_path / "destination.sqlite")
    with pytest.raises(Refused, match="contract"):
        target.apply(historical["bundle"])
    assert historical["bundle"] is None and historical["generation"] > first["generation"]


def test_wrong_lineage_and_duplicate_changes_are_rejected(store, tmp_path):
    first, second = generations(store)
    target = Destination(tmp_path / "destination.sqlite")
    target.apply(first["bundle"])
    bad = copy.deepcopy(second["bundle"])
    bad["lineage"] = "other-dataset"
    bad["seal"] = digest({k: v for k, v in bad.items() if k != "seal"})
    with pytest.raises(Refused, match="lineage"):
        target.apply(bad)
    bad = copy.deepcopy(second["bundle"])
    bad["changes"].append(copy.deepcopy(bad["changes"][0]))
    bad["seal"] = digest({k: v for k, v in bad.items() if k != "seal"})
    with pytest.raises(Refused, match="duplicate_membership"):
        target.apply(bad)


@pytest.mark.parametrize("field,value", [("reason", False), ("decision_evaluated_at", BASE + 100 * DAY)])
def test_destination_refuses_invalid_explanation_metadata(store, tmp_path, field, value):
    first, _ = generations(store)
    target = Destination(tmp_path / "destination.sqlite")
    bad = copy.deepcopy(first["bundle"])
    bad["changes"][0][field] = value
    bad["seal"] = digest({k: v for k, v in bad.items() if k != "seal"})
    with pytest.raises(Refused, match="provenance"):
        target.apply(bad)
    assert target.members() == set()
