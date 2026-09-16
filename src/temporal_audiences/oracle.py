"""Full Python reference evaluator: no feature SQL, no timers and no cached audience state."""
from .store import transaction


def full_evaluation(store, clock, known, rules):
    with transaction(store.path, False) as c:
        rows = [dict(r) for r in c.execute("SELECT * FROM facts WHERE known_seq<=?", (known,))]
    revisions = {}
    for row in rows:
        key = (row["source"], row["fact_id"])
        if key not in revisions or row["revision"] > revisions[key]["revision"]:
            revisions[key] = row
    selected = [r for r in revisions.values() if not r["retracted"]]
    output = {}
    for person in {r["person_id"] for r in rows}:
        profiles = [r for r in selected if r["person_id"] == person and r["source"] == "profile" and r["effective_at"] <= clock]
        last = max((r["effective_at"] for r in profiles), default=None)
        states = {r["value"] for r in profiles if r["effective_at"] == last}
        state = "missing" if not states else next(iter(states)) if len(states) == 1 else "ambiguous"
        subject = [r for r in selected if r["person_id"] == person]
        active = [r for r in subject if r["source"] == "activity" and r["value"] == "qualified" and r["effective_at"] <= clock]
        engaged = sum(clock - rules["engaged_window"] < r["effective_at"] for r in active)
        quiet = sum(clock - rules["quiet_window"] < r["effective_at"] for r in active)
        due = [r["effective_at"] for r in subject if r["effective_at"] > clock]
        due += [r["effective_at"] + window for r in active for window in (rules["engaged_window"], rules["quiet_window"])
                if r["effective_at"] + window > clock]
        evidence = [r for r in profiles if r["effective_at"] == last]
        evidence += [r for r in active if r["effective_at"] > clock - max(rules["engaged_window"], rules["quiet_window"])]
        evidence = [{k: r[k] for k in ("source", "fact_id", "revision", "effective_at", "value")}
                    for r in sorted(evidence, key=lambda r: (r["source"], r["fact_id"]))]
        output[person] = {"features": {"profile_state": state, "engaged_events": engaged, "quiet_events": quiet,
                                      "next_due": min(due, default=None), "evidence": evidence},
                          "membership": {"engaged_trial": state == "trial" and engaged >= rules["minimum_events"],
                                         "quiet_trial": state == "trial" and quiet == 0}}
    return output


def full_members(store, clock, known, rules):
    result = full_evaluation(store, clock, known, rules)
    return {(segment, person) for person, item in result.items() for segment, included in item["membership"].items() if included}


def full_activation_members(store, clock, known, rules):
    """Independent full projection; no production coverage selection or gate helper."""
    computed = full_members(store, clock, known, rules)
    with transaction(store.path, False) as c:
        assertions = [dict(row) for row in c.execute("SELECT * FROM coverage") if row["known_seq"] <= known]
    latest = max(assertions, key=lambda row: row["revision"], default=None)
    covered = (latest is not None and not latest["retracted"]
               and latest["covered_after"] <= clock - rules["quiet_window"]
               and clock <= latest["covered_through"])
    return {(segment, person) for segment, person in computed if segment == "engaged_trial" or covered}
