#!/usr/bin/env python
"""Generate the synthetic financial dataset and its temporal splits.

Usage:
    python scripts/generate_synthetic_data.py
    python scripts/generate_synthetic_data.py --users 100 --seed 7
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ml.dataset.config import (
    MONTHS,
    NUM_USERS,
    OUTPUT_DIR,
    SEED,
    SPLIT_DIRS,
)
from ml.dataset.pipeline import generate_all


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--users", type=int, default=NUM_USERS)
    parser.add_argument("--months", type=int, default=MONTHS)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--output-dir", default=OUTPUT_DIR)
    args = parser.parse_args()

    generate_all(
        seed=args.seed,
        num_users=args.users,
        months_count=args.months,
        output_dir=args.output_dir,
        split_dirs=SPLIT_DIRS,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())