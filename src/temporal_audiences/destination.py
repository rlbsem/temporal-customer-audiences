"""Synthetic membership projection; no campaign, personal-data export or vendor API."""
import json
from pathlib import Path

from .contracts import Refused, canonical, digest, identifier, integer, member_hash
from .store import transaction


class Destination:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with transaction(self.path) as c:
            c.executescript("""CREATE TABLE IF NOT EXISTS members(segment TEXT,person_id TEXT,PRIMARY KEY(segment,person_id));
              CREATE TABLE IF NOT EXISTS state(singleton INTEGER PRIMARY KEY CHECK(singleton=1),lineage TEXT,generation INTEGER);
              INSERT OR IGNORE INTO state VALUES (1,NULL,0);
              CREATE TABLE IF NOT EXISTS receipts(generation INTEGER PRIMARY KEY,seal TEXT NOT NULL,body TEXT NOT NULL);""")

    def members(self):
        with transaction(self.path, False) as c:
            return {tuple(r) for r in c.execute("SELECT segment,person_id FROM members")}

    def apply(self, bundle):
        required = {"contract", "lineage", "generation", "parent", "valid_at", "known_through", "rule_hash",
                    "before_hash", "after_hash", "changes", "seal"}
        if not isinstance(bundle, dict) or set(bundle) != required:
            raise Refused("invalid_destination_contract")
        if type(bundle["contract"]) is not int or bundle["contract"] != 1:
            raise Refused("unknown_destination_contract")
        for key in ("generation", "parent", "valid_at", "known_through"):
            integer(bundle[key])
        identifier(bundle["lineage"])
        if bundle["generation"] <= bundle["parent"] or not isinstance(bundle["changes"], list):
            raise Refused("invalid_generation_or_changes")
        body = {k: v for k, v in bundle.items() if k != "seal"}
        if digest(body) != bundle["seal"]:
            raise Refused("delta_seal_mismatch")
        touched = set()
        for change in bundle["changes"]:
            if not isinstance(change, dict) or set(change) != {"segment", "person_id", "op", "reason", "decision_evaluated_at"}:
                raise Refused("invalid_membership_change")
            identifier(change["person_id"])
            if change["segment"] not in ("engaged_trial", "quiet_trial") or change["op"] not in ("add", "remove"):
                raise Refused("unsupported_membership_operation")
            integer(change["decision_evaluated_at"])
            if (change["decision_evaluated_at"] > bundle["valid_at"] or not isinstance(change["reason"], str)
                    or not 1 <= len(change["reason"]) <= 100):
                raise Refused("invalid_decision_provenance")
            key = (change["segment"], change["person_id"])
            if key in touched:
                raise Refused("duplicate_membership_change")
            touched.add(key)
        with transaction(self.path) as c:
            state = dict(c.execute("SELECT * FROM state").fetchone())
            current = {tuple(r) for r in c.execute("SELECT segment,person_id FROM members")}
            if state["lineage"] is not None and state["lineage"] != bundle["lineage"]:
                raise Refused("destination_lineage_mismatch")
            if state["generation"] == bundle["generation"]:
                receipt = c.execute("SELECT seal FROM receipts WHERE generation=?", (bundle["generation"],)).fetchone()
                if not receipt or receipt["seal"] != bundle["seal"] or member_hash(current) != bundle["after_hash"]:
                    raise Refused("retry_conflict_or_destination_drift")
                return "duplicate"
            if state["generation"] != bundle["parent"]:
                raise Refused("out_of_order_delta")
            if member_hash(current) != bundle["before_hash"]:
                raise Refused("destination_membership_drift")
            for change in bundle["changes"]:
                key = (change["segment"], change["person_id"])
                if change["op"] == "add":
                    if key in current:
                        raise Refused("add_existing_member")
                    c.execute("INSERT INTO members VALUES (?,?)", key)
                    current.add(key)
                else:
                    if key not in current:
                        raise Refused("remove_missing_member")
                    c.execute("DELETE FROM members WHERE segment=? AND person_id=?", key)
                    current.remove(key)
            if member_hash(current) != bundle["after_hash"]:
                raise Refused("delta_result_mismatch")
            c.execute("UPDATE state SET lineage=?,generation=?", (bundle["lineage"], bundle["generation"]))
            c.execute("INSERT INTO receipts VALUES (?,?,?)", (bundle["generation"], bundle["seal"], canonical(bundle)))
        return "applied"

    def reconcile(self, generation):
        expected = {tuple(v) for v in generation.get("activation_members", generation["members"])}
        with transaction(self.path, False) as c:
            actual = {tuple(r) for r in c.execute("SELECT segment,person_id FROM members")}
            state = dict(c.execute("SELECT * FROM state").fetchone())
        return {"matched": actual == expected and state["generation"] == generation["generation"]
                and state["lineage"] == generation["lineage"],
                "missing": sorted([list(v) for v in expected - actual]), "extra": sorted([list(v) for v in actual - expected]),
                "generation": state["generation"], "expected_generation": generation["generation"]}

    def receipts(self):
        with transaction(self.path, False) as c:
            return [json.loads(r[0]) for r in c.execute("SELECT body FROM receipts ORDER BY generation")]
