"""Check committed execution evidence, preserved original bytes and public package integrity."""
import argparse
import hashlib
import json
import re
import struct
from pathlib import Path
from urllib.parse import unquote, urlparse

from temporal_audiences.contracts import digest

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check(evidence):
    evidence = evidence.resolve()
    inventory = json.loads((evidence / "artifact-integrity.json").read_bytes())
    actual = {p.relative_to(evidence).as_posix() for p in evidence.rglob("*") if p.is_file()}
    assert actual == {*inventory, "artifact-integrity.json"}, "evidence_inventory_difference"
    for name, value in inventory.items():
        path = (evidence / name).resolve()
        assert path.is_relative_to(evidence) and sha(path) == value, "evidence_hash_difference"
    original = json.loads((ROOT / "docs/evidence/activation-assurance/original-files.json").read_bytes())
    assert all(sha(ROOT / name) == value for name, value in original["sha256"].items()), "original_bytes_changed"
    verification = json.loads((evidence / "verification.json").read_bytes())
    assert verification["status"] == "passed" and verification["native_vendor_calls"] == 0
    assert verification["owned_processes_stopped"]
    for name, value in verification["source_sha256"].items():
        assert sha(ROOT / name) == value, "executed_source_changed: " + name
    for suite in verification["suites"].values():
        assert not any(suite[k] for k in ["failures", "errors", "skipped"])
        assert len(suite["cases"]) == suite["tests"]
        assert all(c["status"] == "passed" for c in suite["cases"])
    assert verification["suites"]["original"]["tests"] == 58
    report = json.loads((evidence / "acceptance.json").read_bytes())
    assert report["synthetic"] and report["native_vendor_calls"] == 0
    assert len(report["checks"]) == 36 and all(r["passed"] and r["expected"] == r["observed"] for r in report["checks"])
    assert sum(r["decision_rows_compared"] for r in report["oracle"]) == 164
    assert sum(r["eligibility_rows"] for r in report["oracle"]) == 20
    assert all(r["row_differences"] == 0 for r in report["oracle"])
    source, receiver = report["snapshot"]["operating"], report["snapshot"]["receiver"]
    for table in ["inbox", "permissions", "publications"]:
        assert all(digest(row["body"]) == row["hash"] for row in source[table]), "journal_content_difference"
    effects = {row["id"]: row for row in receiver["effects"]}
    records = {row["id"]: row for row in receiver["records"]}
    assert len(effects) == len(receiver["effects"]) == len(records)
    for effect, row in effects.items():
        assert row["hash"] == digest(row["payload"]) == row["receipt"]["payload_hash"]
        assert row["receipt"]["effect_id"] == effect
        assert digest(records[effect]["body"]) == records[effect]["hash"] == row["receipt"]["record_hash"]
        assert records[effect]["body"] == row["receipt"]["record"]
    for row in source["intents"]:
        assert row["hash"] == digest(row["payload"])
        assert row["id"] == digest({k: v for k, v in row["payload"].items() if k != "effect_id"})
        if row["state"] == "confirmed":
            assert effects[row["id"]]["payload"] == row["payload"]
    browser = json.loads((evidence / "browser/browser.json").read_bytes())
    assert len(browser["checks"]) == 109 and all(r["passed"] for r in browser["checks"])
    assert len(browser["accessibility"]) == 20
    assert not any(browser[k] for k in ["page_errors", "http_writes", "external_requests"])
    for scan in browser["accessibility"]:
        assert not scan["violations"]
        assert sum(len(i["nodes"]) for i in scan["incomplete"]) == len(scan["visibility_followups"])
        assert all(not f["violations"] and not f["incomplete"] and f["passes"] for f in scan["visibility_followups"])
    for name, details in browser["images"].items():
        path = evidence / "browser" / name
        assert sha(path) == browser["image_sha256"][name]
        assert struct.unpack(">II", path.read_bytes()[16:24]) == (details["width"], details["height"])
    for path in evidence.rglob("*.json"):
        body = path.read_text(encoding="utf-8")
        assert not re.search(r'"(?:dsn|password|read_token|write_token|api_secret)"\s*:', body), "private_field_in_evidence"
        assert not re.search(r"(?:postgres(?:ql)?://|Bearer [A-Za-z0-9_-]{20,}|-----BEGIN .*PRIVATE KEY)", body), "credential_pattern_in_evidence"
    links = 0
    for path in [ROOT / "README.md", ROOT / "docs/activation-assurance.md", evidence.parent / "README.md"]:
        if not path.exists():
            continue
        for value in re.findall(r"\[[^\]]*\]\(([^)]+)\)", path.read_text(encoding="utf-8")):
            target = urlparse(value.strip("<>"))
            if target.scheme or not target.path:
                continue
            resolved = (path.parent / unquote(target.path)).resolve()
            assert resolved.is_relative_to(ROOT) and resolved.exists(), "broken_local_link: " + value
            links += 1
    return {"status": "passed", "evidence_files": len(inventory), "preserved_original_files": len(original["sha256"]),
            "historical_decision_rows": 164, "current_eligibility_rows": 20,
            "receiver_effects": len(effects), "browser_checks": 109, "accessibility_states": 20, "local_links": links}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, default=ROOT / "docs/evidence/activation-assurance/run01")
    args = parser.parse_args()
    print(json.dumps(check(args.evidence), indent=2))
