import argparse
import json
import time
from pathlib import Path

from psycopg.types.json import Jsonb

from .db import connect
from .runtime import LocalRuntime
from .scenario import run
from .verify import source_hash, verify


def execute(config, receiver_config, controller_file):
    with connect(config["dsn"]) as c:
        old = c.execute("SELECT * FROM acceptance_reports WHERE id='synthetic-v1'").fetchone()
    if old:
        if old["source_hash"] != source_hash():
            raise ValueError("code_changed_requires_explicit_fresh_synthetic_environment")
        return old["body"]
    report = run(config, receiver_config["dsn"], controller_file)
    with connect(config["dsn"]) as c:
        c.execute("INSERT INTO acceptance_reports VALUES('synthetic-v1',%s,%s)", (Jsonb(report), source_hash()))
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--port", type=int, default=8596)
    args = parser.parse_args()
    with LocalRuntime(args.workspace) as runtime:
        execute(runtime.config, runtime.receiver_config, runtime.path / "private/controller.json")
        console = json.loads((runtime.path / "private/console.json").read_bytes())
        print(json.dumps(verify(console)), flush=True)
        if args.serve:
            runtime.spawn("console", runtime.path / "private/console.json", args.port)
            print(f"Read-only synthetic console: http://127.0.0.1:{args.port}/", flush=True)
            try:
                while True:
                    time.sleep(0.5)
            except KeyboardInterrupt:
                pass


if __name__ == "__main__":
    main()
