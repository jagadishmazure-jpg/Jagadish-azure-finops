"""Write the deterministic synthetic datasets to data/ (or --check that they are current)."""

from __future__ import annotations

import argparse
import sys

from finops import DATA
from finops.datasets import generate_all


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="exit 1 if data/ differs from the generator")
    a = ap.parse_args()
    stale = []
    for rel, text in generate_all().items():
        path = DATA / rel
        if a.check:
            if not path.exists() or path.read_text() != text:
                stale.append(rel)
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        print(f"wrote data/{rel} ({len(text.splitlines())} lines)")
    if a.check:
        print("data is current" if not stale else f"stale: {stale}")
    return 1 if stale else 0


if __name__ == "__main__":
    sys.exit(main())
