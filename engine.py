"""Maintain finite audience queries using changed-subject and scheduled-time invalidation."""
import json
from pathlib import Path

from .contracts import DEFAULT_RULES, Refused, canonical, digest, identifier, implementation_hash, integer, member_hash, ruleset
from .coverage import coverage_at
from .store import transaction

SQL = Path(__file__).with_name("features.sql").read_text()


def evaluate(c, person, clock, known, rules):
    features = dict(c.execute(SQL, {"person": person, "clock": clock, "known": known, **rules}).fetchone())
    features["evidence"] = json.loads(features["evidence"])
    trial = features["profile_state"] == "trial"
    membership = {"engaged_trial": trial and features["engaged_events"] >= rules["minimum_events"],
                  "quiet_trial": trial and features["quiet_events"] == 0}
    return {"evaluated_at": clock, "evaluated_known_through": known, "features": features, "membership": membership,
            "reasons": {"engaged_trial": "not_trial:" + features["profile_state"] if not trial else
                        "event_threshold_met" if membership["engaged_trial"] else "below_event_threshold",
                        "quiet_trial": "not_trial:" + features["profile_state"] if not trial else
                        "no_observed_events_in_window" if membership["quiet_trial"] else "observed_recent_activity"}}


def members(people):
    return {(segment, person) for person, row in people.items() for segment, included in row["membership"].items() if included}


def build(store, run_key, clock, known=None, rules=None, mode="current", force_full=False):
    identifier(run_key)
    integer(clock)
    rules = ruleset(DEFAULT_RULES if rules is None else rules)
    if mode not in ("current", "historical") or type(force_full) is not bool:
        raise Refused("invalid_build_mode")
    code = implementation_hash()
    with transaction(store.path) as c:
        head = c.execute("SELECT COALESCE(MAX(seq),0) FROM batches").fetchone()[0]
        known = head if known is None else known
        integer(known)
        if known > head:
            raise Refused("future_knowledge")
        request_hash = digest({"clock": clock, "known": known, "rules": rules, "implementation": code,
                               "mode": mode, "force_full": force_full})
        old = c.execute("SELECT request_hash,body FROM generations WHERE run_key=?", (run_key,)).fetchone()
        if old:
            if old["request_hash"] != request_hash:
                raise Refused("run_identity_conflict")
            return json.loads(old["body"])
        active = int(c.execute("SELECT value FROM meta WHERE key='active'").fetchone()[0])
        row = c.execute("SELECT body FROM generations WHERE id=?", (active,)).fetchone()
        previous = json.loads(row["body"]) if row else None
        if mode == "current" and (known != head or (previous and clock < previous["valid_at"])):
            raise Refused("current_requires_latest_knowledge_and_monotone_clock")
        everyone = {r[0] for r in c.execute("SELECT DISTINCT person_id FROM facts WHERE known_seq<=?", (known,))}
        full = (mode == "historical" or force_full or not previous or previous["rules"] != rules
                or previous["implementation"] != code)
        changed, due = set(), set()
        if full:
            impacted = everyone
        else:
            changed = {r[0] for r in c.execute("SELECT DISTINCT person_id FROM facts WHERE known_seq>? AND known_seq<=?",
                                             (previous["known_through"], known))}
            due = {p for p, item in previous["people"].items()
                   if item["features"]["next_due"] is not None and item["features"]["next_due"] <= clock}
            impacted = changed | due
        people = {} if full else dict(previous["people"])
        for person in sorted(impacted):
            people[person] = evaluate(c, person, clock, known, rules)
        computed = members(people)
        # Cheap global gate is evaluated every publication, independently of reused person features.
        coverage = coverage_at(c, clock, known, rules["quiet_window"])
        after = {pair for pair in computed if pair[0] != "quiet_trial" or coverage["eligible"]}
        # An older generation predating the gate exported all computed members.
        before = {tuple(v) for v in previous.get("activation_members", previous["members"])} if previous else set()
        identifier_value = c.execute("SELECT COALESCE(MAX(id),0)+1 FROM generations").fetchone()[0]
        lineage = c.execute("SELECT value FROM meta WHERE key='lineage'").fetchone()[0]
        bundle = None
        if mode == "current":
            changes = [{"segment": segment, "person_id": person, "op": op,
                        "reason": ("coverage:" + ",".join(coverage["failures"]))
                        if segment == "quiet_trial" and (segment, person) in computed and not coverage["eligible"]
                        else people[person]["reasons"][segment],
                        "decision_evaluated_at": clock if segment == "quiet_trial" else people[person]["evaluated_at"]}
                       for op, rows in (("remove", before - after), ("add", after - before)) for segment, person in sorted(rows)]
            body = {"contract": 1, "lineage": lineage, "generation": identifier_value, "parent": active,
                    "valid_at": clock, "known_through": known, "rule_hash": digest(rules),
                    "before_hash": member_hash(before), "after_hash": member_hash(after), "changes": changes}
            bundle = {**body, "seal": digest(body)}
        result = {"generation": identifier_value, "mode": mode, "valid_at": clock, "known_through": known,
                  "rules": rules, "implementation": code, "lineage": lineage, "people": people,
                  "members": sorted([list(v) for v in computed]), "bundle": bundle,
                  "activation_members": sorted([list(v) for v in after]), "activity_coverage": coverage,
                  "maintenance": {"strategy": "full" if full else "incremental", "population": len(everyone),
                                  "evaluated_people": len(impacted), "changed_people": sorted(changed), "timer_due_people": sorted(due),
                                  "reused_people": 0 if full else len(people) - len(impacted)}}
        c.execute("INSERT INTO generations VALUES (?,?,?,?,?)", (identifier_value, run_key, request_hash, mode, canonical(result)))
        if mode == "current":
            c.execute("UPDATE meta SET value=? WHERE key='active'", (str(identifier_value),))
        return result
