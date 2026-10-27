"""One-time isolated Compose setup; preserves data/configuration on ordinary restart."""
import argparse
import json
import secrets
from pathlib import Path

from psycopg.conninfo import make_conninfo

from .demo import execute
from .runtime import initialize, private_json


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("step", choices=["configure", "initialize", "demo"])
    args = parser.parse_args()
    if args.step == "configure":
        password = Path("/secrets/postgres-password")
        if not password.exists():
            password.write_text(secrets.token_urlsafe(32), encoding="utf-8")
            password.chmod(0o444)
        return
    controller = Path("/controller/controller.json")
    if args.step == "initialize":
        password = Path("/secrets/postgres-password").read_text(encoding="utf-8")
        admin = make_conninfo(host="postgres", port=5432, user="postgres", dbname="postgres", password=password)
        initialize(admin, Path("/controller"), "http://receiver:8331")
        for name in ["receiver", "console"]:
            original = Path("/controller") / (name + ".json")
            target = Path("/" + name) / (name + ".json")
            if original.exists():
                private_json(target, json.loads(original.read_bytes()))
                original.unlink()
            if not target.exists():
                raise RuntimeError("scoped_configuration_missing")
            target.chmod(0o444)  # Separate private volumes, never a public file or shared web mount.
        controller.chmod(0o444)
        return
    config = json.loads(controller.read_bytes())
    receiver = json.loads(Path("/receiver/receiver.json").read_bytes())
    report = execute(config, receiver, controller)
    print(json.dumps({"status": "passed", "executed_checks": len(report["checks"]),
                      "synthetic": True, "native_vendor_calls": 0}), flush=True)


if __name__ == "__main__":
    main()
