"""One synthetic activity-source assertion stream; never infer coverage from events."""
from .contracts import Refused, integer


def validate_coverage(assertion):
    if not isinstance(assertion, dict) or set(assertion) != {"revision", "covered_after", "covered_through", "retracted"}:
        raise Refused("invalid_coverage_shape")
    integer(assertion["revision"], 1)
    for key in ("covered_after", "covered_through"):
        integer(assertion[key])
    if assertion["covered_after"] >= assertion["covered_through"] or type(assertion["retracted"]) is not bool:
        raise Refused("invalid_coverage_interval_or_retraction")


def coverage_at(c, clock, known, window):
    # A correction replaces the entire assertion, even when its interval excludes T.
    row = c.execute("SELECT revision,covered_after,covered_through,retracted,known_seq FROM coverage "
                    "WHERE known_seq<=? ORDER BY revision DESC LIMIT 1", (known,)).fetchone()
    evidence = dict(row) if row else None
    if evidence:
        evidence["retracted"] = bool(evidence["retracted"])
    failures = []
    if evidence is None:
        failures.append("missing_coverage")
    elif evidence["retracted"]:
        failures.append("retracted_coverage")
    else:
        if evidence["covered_after"] > clock - window:
            failures.append("incomplete_window")
        if evidence["covered_through"] < clock:
            failures.append("coverage_behind_clock")
    # Exact eligibility interval at fixed K: [covered_after + window, covered_through].
    boundaries = []
    if evidence and not evidence["retracted"]:
        start, end = evidence["covered_after"] + window, evidence["covered_through"]
        if start <= end:
            boundaries = [t for t in (start, end + 1) if t > clock]
    return {"evaluated_at": clock, "evaluated_known_through": known,
            "required_interval": {"after": clock - window, "through": clock},
            "evidence": evidence, "eligible": not failures, "failures": failures,
            "next_due": min(boundaries, default=None)}
