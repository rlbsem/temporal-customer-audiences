import hashlib
import json
import os
import platform
import sqlite3
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import temporal_audiences

ROOT = Path(__file__).resolve().parents[1]


def manifest():
    paths = [p for folder in ("src", "tests", "scripts", ".github") for p in (ROOT / folder).rglob("*")
             if p.is_file() and p.suffix in (".py", ".sql", ".yml") and "__pycache__" not in p.parts
             and not any(v.endswith(".egg-info") for v in p.parts)]
    paths += [ROOT / "requirements.lock", ROOT / "pyproject.toml"]
    return {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}


def main():
    start = time.monotonic()
    output = ROOT / "docs/evidence"
    output.mkdir(parents=True, exist_ok=True)
    scratch = ROOT / "work/verification" / uuid4().hex
    scratch.mkdir(parents=True)
    installed = Path(temporal_audiences.__file__).parent
    for path in (ROOT / "src/temporal_audiences").iterdir():
        if path.is_file() and path.read_bytes() != (installed / path.name).read_bytes():
            raise RuntimeError("Installed package differs from source; reinstall")
    before = manifest()
    def execute(*args):
        subprocess.run([sys.executable, *args], cwd=ROOT, check=True)
    execute("-m", "ruff", "check", "src", "tests", "scripts")
    execute("-m", "pip", "check")
    execute("-m", "pytest", "-q", "--basetemp", str(scratch / "pytest"), "-o", "cache_dir=" + str(scratch / "cache"),
            "--junitxml", str(output / "tests.xml"))
    execute("scripts/demo.py", "--workspace", str(scratch / "demo"), "--output", str(output))
    assert before == manifest(), "Source changed during verification"
    suite = ET.parse(output / "tests.xml").getroot().find("testsuite")
    record = {"executed_at": datetime.now(UTC).isoformat(), "python": platform.python_version(),
              "sqlite": sqlite3.sqlite_version, "platform": platform.platform(),
              **{k: int(suite.attrib[k]) for k in ("tests", "failures", "errors", "skipped")},
              "seconds": round(time.monotonic() - start, 2), "source_sha256": before,
              "installation": "source" if installed.resolve() == (ROOT / "src/temporal_audiences").resolve() else "installed_wheel",
              "hosted_ci": "not_observed" if not os.getenv("GITHUB_ACTIONS") else "workflow_in_progress",
              "scope": "synthetic local SQL temporal engine, independent Python oracle and SQLite membership destination"}
    (output / "verification.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(f"Verified {record['tests']} tests and the complete temporal audience proof.")


if __name__ == "__main__":
    main()
