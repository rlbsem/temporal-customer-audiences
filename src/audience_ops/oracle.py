"""Independent Python interpretation of raw PG source bodies, not SQL views/cache counts."""
from .db import connect


def temporal(inbox, clock, known, rules):
    latest, coverage, people = {}, None, set()
    for batch in inbox:
        if batch["seq"] > known:
            continue
        if batch["kind"] == "coverage":
            item = batch["body"]
            if coverage is None or item["revision"] > coverage["revision"]:
                coverage = item
            continue
        for fact in batch["body"]:
            people.add(fact["person_id"])
            key = fact["source"], fact["fact_id"]
            if key not in latest or fact["revision"] > latest[key]["revision"]:
                latest[key] = fact
    selected = [f for f in latest.values() if not f["retracted"]]
    covered = bool(coverage and not coverage["retracted"] and coverage["covered_after"] <= clock - rules["quiet_window"]
                   and coverage["covered_through"] >= clock)
    rows = {}
    for person in people:
        profiles = [f for f in selected if f["person_id"] == person and f["source"] == "profile" and f["effective_at"] <= clock]
        latest_time = max((f["effective_at"] for f in profiles), default=None)
        states = {f["value"] for f in profiles if f["effective_at"] == latest_time}
        trial = states == {"trial"}
        activity = [f for f in selected if f["person_id"] == person and f["source"] == "activity"
                    and f["value"] == "qualified" and f["effective_at"] <= clock]
        engaged = sum(clock - rules["engaged_window"] < f["effective_at"] for f in activity)
        quiet = sum(clock - rules["quiet_window"] < f["effective_at"] for f in activity)
        rows[person, "engaged_trial"] = {"member": trial and engaged >= rules["minimum_events"], "covered": True}
        rows[person, "quiet_trial"] = {"member": trial and quiet == 0, "covered": covered}
    return rows


def check(dsn, brand):
    with connect(dsn) as c:
        inbox = c.execute("SELECT * FROM inbox WHERE brand=%s ORDER BY seq", (brand,)).fetchall()
        pubs = c.execute("SELECT * FROM publications WHERE brand=%s ORDER BY request", (brand,)).fetchall()
        permissions = c.execute("SELECT * FROM permissions WHERE brand=%s", (brand,)).fetchall()
        clock = c.execute("SELECT clock FROM brands WHERE brand=%s", (brand,)).fetchone()["clock"]
        active = c.execute("SELECT publication FROM active WHERE brand=%s", (brand,)).fetchone()
        view = c.execute("SELECT * FROM activation_eligibility WHERE brand=%s ORDER BY person,segment", (brand,)).fetchall()
        subjects = [r["person"] for r in c.execute("SELECT person FROM subjects WHERE brand=%s", (brand,))]
        counts = 0
        expected_active = {}
        for pub in pubs:
            expected = temporal(inbox, pub["clock"], pub["known"], pub["body"]["rules"])
            actual = {(r["person"], r["segment"]): {"member": r["member"], "covered": r["covered"]}
                      for r in c.execute("SELECT * FROM decisions WHERE publication=%s AND brand=%s", (pub["id"], brand))}
            if expected != actual:
                raise AssertionError("raw_source_temporal_oracle_difference")
            counts += len(actual)
            if active and pub["id"] == active["publication"]:
                expected_active = expected
                active_pub = pub
        grants = {}
        for row in permissions:
            if row["channel"] == "email" and row["purpose"] == "trial_help":
                old = grants.get(row["person"])
                if old is None or row["revision"] > old["revision"]:
                    grants[row["person"]] = row
        expected_eligible = set()
        for key, row in expected_active.items():
            grant = grants.get(key[0])
            if (active_pub["clock"] == clock and active_pub["known"] == len(inbox)
                    and row["member"] and row["covered"] and grant and grant["allowed"] and not grant["suppressed"]
                    and grant["valid_from"] <= clock < grant["expires"]):
                expected_eligible.add(key)
        actual_eligible = {(r["person"], r["segment"]) for r in view if r["reason"] == "eligible"}
        if expected_eligible != actual_eligible or len(view) != len(subjects) * 2:
            raise AssertionError("current_permission_or_grain_oracle_difference")
        return {"brand": brand, "publications": len(pubs), "decision_rows_compared": counts,
                "eligibility_rows": len(view), "eligible": sorted([list(v) for v in expected_eligible]),
                "row_differences": 0, "method": "raw_source_revision_selection_python_windows_and_scoped_permission_journal"}
