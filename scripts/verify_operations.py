"""Repeatable real PostgreSQL/HTTP/browser acceptance; fresh output, no vendor credentials."""
import argparse
import hashlib
import importlib.metadata
import json
import platform
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path
from urllib.request import urlopen

from audience_ops.db import connect
from audience_ops.demo import execute
from audience_ops.runtime import LocalRuntime, free_port
from audience_ops.verify import source_hash, verify

from browser_operations import browser_check

ROOT = Path(__file__).resolve().parents[1]


def source_files():
    names = [p for folder in ["src", "tests", "operations_tests", "scripts", ".github"]
             for p in (ROOT / folder).rglob("*") if p.is_file() and "__pycache__" not in p.parts
             and p.suffix in {".py", ".sql", ".js", ".css", ".html", ".yml", ".json"}]
    names += [ROOT / n for n in ["pyproject.toml", "requirements.lock", "requirements-operations.lock", "requirements-runtime.lock", "Dockerfile", "compose.yaml"]]
    return {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(names)}


def command(args, log):
    with log.open("w", encoding="utf-8") as target:
        result = subprocess.run([sys.executable, *args], cwd=ROOT, stdout=target, stderr=subprocess.STDOUT, timeout=900)
    if result.returncode:
        raise RuntimeError(f"check failed; inspect {log.name} in the private workspace")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    workspace, output = args.workspace.resolve(), args.output.resolve()
    if workspace.exists() or output.exists():
        raise ValueError("fresh_workspace_and_evidence_directory_required")
    workspace.mkdir(parents=True)
    output.mkdir(parents=True)
    before = source_files()
    revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, check=True, text=True, capture_output=True).stdout.strip()
    suites = {}
    command(["-m", "ruff", "check", "src", "tests", "operations_tests", "scripts"], workspace / "lint.log")
    command(["-m", "pip", "check"], workspace / "dependencies.log")
    for suite, folder in [("original", "tests"), ("operations", "operations_tests")]:
        xml = workspace / (suite + ".xml")
        command(["-m", "pytest", folder, "-q", "--basetemp", str(workspace / (suite + "-tests")), "--junitxml", str(xml)],
                workspace / (suite + ".log"))
        root = ET.parse(xml).getroot()
        node = next(root.iter("testsuite"))
        suites[suite] = {k: int(node.attrib[k]) for k in ["tests", "failures", "errors", "skipped"]}
        suites[suite]["cases"] = [{"test": t.attrib["classname"] + "." + t.attrib["name"], "status": "passed"}
                                   for t in root.iter("testcase")]
        assert not any(suites[suite][k] for k in ["failures", "errors", "skipped"])
    # Reexecute the original complete proof into fresh output, never its archived files.
    command(["scripts/demo.py", "--workspace", str(workspace / "original-demo"), "--output", str(output / "original-demo")],
            workspace / "original-demo.log")
    started = datetime.now(UTC).isoformat()
    with LocalRuntime(workspace / "native") as runtime:
        report = execute(runtime.config, runtime.receiver_config, runtime.path / "private/controller.json")
        console_config = json.loads((runtime.path / "private/console.json").read_bytes())
        independently_verified = verify(console_config)
        with connect(runtime.config["dsn"]) as c:
            pg_version = c.execute("SELECT version() AS version").fetchone()["version"]
        port = free_port()
        runtime.spawn("console", runtime.path / "private/console.json", port)
        url = f"http://127.0.0.1:{port}/"
        for _ in range(100):
            try:
                urlopen(url + "health", timeout=2).close()
                break
            except OSError:
                time.sleep(0.1)
        else:
            raise RuntimeError("console_not_ready")
        browser_check(url, output / "browser")
    assert before == source_files(), "source_changed_during_acceptance"
    original = json.loads((ROOT / "docs/evidence/activation-assurance/original-files.json").read_bytes())
    assert all(hashlib.sha256((ROOT / n).read_bytes()).hexdigest() == h for n, h in original["sha256"].items())
    result = {"status": "passed", "started_at": started, "finished_at": datetime.now(UTC).isoformat(),
              "python": platform.python_version(), "os": platform.system(), "postgresql": pg_version,
              "dependencies": {n: importlib.metadata.version(n) for n in ["psycopg", "playwright", "pytest"]},
              "lane": "actual_native_local_postgresql_sqlite_http_browser_and_terminated_worker",
              "git_revision": revision, "source_sha256": before, "runtime_source_hash": source_hash(), "suites": suites,
              "read_only_verification": independently_verified, "synthetic": True, "native_vendor_calls": 0,
              "docker": {"local_cli_present": shutil.which("docker") is not None,
                         "executed_by_this_command": False, "note": "Compose acceptance is a separate CI lane."},
              "owned_processes_stopped": all(p.poll() is not None for p, _ in runtime.processes),
              "original_files_preserved": len(original["sha256"])}
    (output / "acceptance.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    (output / "verification.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8", newline="\n")
    artifacts = {p.relative_to(output).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in sorted(output.rglob("*")) if p.is_file()}
    (output / "artifact-integrity.json").write_text(json.dumps(artifacts, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"status": "passed", "original_tests": suites["original"]["tests"],
                      "operations_tests": suites["operations"]["tests"], "native_checks": len(report["checks"]),
                      "output": str(output)}))


if __name__ == "__main__":
    main()
