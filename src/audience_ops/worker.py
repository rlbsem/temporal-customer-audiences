import argparse
import json
from pathlib import Path

from .activation import Activation
from .client import Client
from .db import Principal


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--brand", required=True)
    parser.add_argument("--effect")
    parser.add_argument("--lease-seconds", type=int, default=30)
    parser.add_argument("--crash-after-post", action="store_true", help="Controlled synthetic acceptance fault only")
    args = parser.parse_args()
    config = json.loads(args.config.read_bytes())
    activation = Activation(config["dsn"], Client(config["url"], config["read_token"], config["write_token"]))
    actor = Principal("worker", "controller", frozenset(config["brands"]))
    print(activation.dispatch(actor, args.brand, args.effect, args.lease_seconds, args.crash_after_post))


if __name__ == "__main__":
    main()
