import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_original_engine_tests_and_archived_evidence_are_exact_base_bytes():
    baseline = json.loads((ROOT / "docs/evidence/activation-assurance/original-files.json").read_bytes())
    for name, expected in baseline["sha256"].items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected, name
