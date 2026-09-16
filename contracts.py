import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

DAY = 86400
DEFAULT_RULES = {"engaged_window": 7 * DAY, "minimum_events": 2, "quiet_window": 3 * DAY}


class Refused(ValueError):
    pass


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", value):
        raise Refused("invalid_identifier")


def integer(value, minimum=0):
    if type(value) is not int or not minimum <= value <= 32503680000:
        raise Refused("invalid_integer")


def utc(text):
    if not isinstance(text, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(Z|[+-]\d{2}:\d{2})", text):
        raise Refused("whole_second_timezone_required")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise Refused("invalid_timestamp") from exc
    if parsed.utcoffset() is None or parsed.microsecond:
        raise Refused("whole_second_timezone_required")
    result = int(parsed.timestamp())
    if parsed.timestamp() != result:
        raise Refused("whole_second_timezone_required")
    integer(result)
    return result


def validate_fact(fact):
    if not isinstance(fact, dict) or set(fact) != {"source", "fact_id", "revision", "person_id", "effective_at", "value", "retracted"}:
        raise Refused("invalid_fact_shape")
    for field in ("fact_id", "person_id"):
        identifier(fact[field])
    integer(fact["revision"], 1)
    integer(fact["effective_at"])
    if type(fact["retracted"]) is not bool:
        raise Refused("invalid_retraction")
    if fact["source"] not in ("profile", "activity"):
        raise Refused("unsupported_source")
    values = ("trial", "paid", "closed") if fact["source"] == "profile" else ("qualified", "noise")
    if fact["value"] not in values:
        raise Refused("unsupported_value")


def ruleset(rules):
    if not isinstance(rules, dict) or set(rules) != set(DEFAULT_RULES):
        raise Refused("invalid_rules")
    for value in rules.values():
        integer(value, 1)
    if max(rules["engaged_window"], rules["quiet_window"]) > 366 * DAY or rules["minimum_events"] > 1000:
        raise Refused("rule_budget_exceeded")
    return dict(rules)


def implementation_hash():
    folder = Path(__file__).parent
    return digest({p.name: p.read_text(encoding="utf-8") for p in sorted(folder.iterdir())
                   if p.suffix in (".py", ".sql")})


def member_hash(members):
    return digest(sorted([list(v) for v in members]))
