import sqlite3

import pytest

from temporal_audiences.contracts import Refused
from temporal_audiences.fixtures import fact
from temporal_audiences.store import transaction


def test_batch_retry_and_repeated_fact_are_deduplicated(store):
    row = fact("profile", "p", "ada", 0)
    assert store.ingest("batch", [row]) == store.ingest("batch", [row]) == 1
    store.ingest("another-batch", [row])
    with transaction(store.path, False) as c:
        assert c.execute("SELECT count(*) FROM facts").fetchone()[0] == 1
    with pytest.raises(Refused, match="batch_identity"):
        store.ingest("batch", [{**row, "value": "paid"}])


def test_conflicting_revision_rejects_whole_batch_including_earlier_valid_rows(store):
    row = fact("profile", "p", "ada", 0)
    store.ingest("original", [row])
    with pytest.raises(Refused, match="revision_conflict"):
        store.ingest("conflict", [fact("profile", "p2", "bea", 0), {**row, "value": "paid"}])
    assert store.head() == 1
    with transaction(store.path, False) as c:
        assert c.execute("SELECT count(*) FROM facts").fetchone()[0] == 1


def test_fact_owner_cannot_change_and_duplicate_batch_revision_is_rejected(store):
    row = fact("profile", "p", "ada", 0)
    store.ingest("original", [row])
    with pytest.raises(Refused, match="owner"):
        store.ingest("move", [{**row, "person_id": "bea", "revision": 2}])
    with pytest.raises(Refused, match="duplicate_revision"):
        store.ingest("duplicates", [row, row])


@pytest.mark.parametrize("field,value", [("revision", True), ("effective_at", 1.5), ("retracted", "false"),
                                       ("source", "unapproved"), ("person_id", "../../other"), ("value", "prospect")])
def test_closed_contract_refuses_malformed_fact_without_writing(store, field, value):
    row = fact("profile", "p", "ada", 0)
    row[field] = value
    with pytest.raises(Refused):
        store.ingest("bad", [row])
    assert store.head() == 0


def test_raw_facts_and_receipts_are_immutable(store):
    store.ingest("original", [fact("profile", "p", "ada", 0)])
    with transaction(store.path) as c:
        for sql in ("UPDATE facts SET value='paid'", "DELETE FROM facts", "UPDATE batches SET hash='changed'"):
            with pytest.raises(sqlite3.IntegrityError, match="immutable"):
                c.execute(sql)
