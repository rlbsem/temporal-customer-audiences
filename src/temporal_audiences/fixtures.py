from .contracts import DAY, utc

BASE = utc("2026-01-01T00:00:00Z")


def fact(source, key, person, day, value=None, revision=1, retracted=False):
    return {"source": source, "fact_id": key, "revision": revision, "person_id": person,
            "effective_at": BASE + day * DAY, "value": value or ("trial" if source == "profile" else "qualified"),
            "retracted": retracted}


def population(count=120):
    rows = []
    for i in range(count):
        person = f"person{i:04d}"
        rows.append(fact("profile", f"profile-{i}", person, 0))
        if i % 3:
            rows.append(fact("activity", f"use-a-{i}", person, 1))
            rows.append(fact("activity", f"use-b-{i}", person, 2))
    return rows
