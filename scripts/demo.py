import argparse
from pathlib import Path

from temporal_audiences.demo import run

p = argparse.ArgumentParser()
p.add_argument("--workspace", type=Path, default=Path("work/demo"))
p.add_argument("--output", type=Path, default=Path("docs/evidence"))
args = p.parse_args()
run(args.workspace, args.output)
print("Verified temporal history, no-ingestion expiry, sparse correction, coverage-conditioned export and destination deltas.")
print("Evidence:", args.output / "report.md")
