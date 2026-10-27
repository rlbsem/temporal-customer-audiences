"""Read-only validation of executed acceptance and independently readable current state."""
import argparse
import hashlib
import json
from pathlib import Path

from temporal_audiences.contracts import digest

from .client import Client
from .db import connect
from .oracle import check


def source_hash():
    root = Path(__file__).parents[1]
    return digest({p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                   for folder in [root / "audience_ops", root / "temporal_audiences"]
                   for p in sorted(folder.rglob("*")) if p.is_file() and p.suffix in {".py", ".sql", ".html", ".js", ".css"}})


def verify(config):
    client = Client(config["url"], config["read_token"])
    results = []
    with connect(config["dsn"]) as c:
        stored = c.execute("SELECT * FROM acceptance_reports WHERE id='synthetic-v1'").fetchone()
        if not stored or stored["source_hash"] != source_hash():
            raise AssertionError("executed_acceptance_or_source_fingerprint_missing")
        report = stored["body"]
        assert report["synthetic"] and report["native_vendor_calls"] == 0
        assert len(report["checks"]) == 36 and all(r["passed"] and r["expected"] == r["observed"] for r in report["checks"])
        for brand in config["brands"]:
            oracle = check(config["dsn"], brand)
            remote = client.membership(brand)
            expected = {tuple(r) for r in oracle["eligible"]}
            actual = {(r["person"], r["segment"]) for r in remote if r["active"]}
            assert expected == actual, "independent_destination_difference"
            confirmed = c.execute("SELECT payload FROM intents WHERE brand=%s AND state='confirmed'", (brand,)).fetchall()
            receipts = [client.readback(r["payload"]) for r in confirmed]
            assert all(receipts), "confirmed_intent_without_independent_receipt"
            results.append({**oracle, "independent_receipts": len(receipts), "destination_differences": 0})
    return {"status": "passed", "source_hash": source_hash(), "checks": len(report["checks"]),
            "brands": results, "native_vendor_calls": 0, "read_only_verification": True}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(verify(json.loads(args.config.read_bytes())), indent=2))


if __name__ == "__main__":
    main()
