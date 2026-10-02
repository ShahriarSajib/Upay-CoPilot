#!/usr/bin/env python
"""Check the generated splits for target and temporal leakage.

Usage:
    python scripts/leakage_check.py
    python scripts/leakage_check.py --split-root data --data-dir data/generated
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ml.dataset.config import OUTPUT_DIR
from ml.dataset.leakage import render, run_leakage_check


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split-root", default="data")
    parser.add_argument("--data-dir", default=OUTPUT_DIR)
    args = parser.parse_args()

    tables = {
        path.stem: pd.read_csv(path)
        for path in sorted(Path(args.data_dir).glob("*.csv"))
    }

    violations = run_leakage_check(args.split_root, tables)
    print(render(violations))
    return 0 if not violations else 1


if __name__ == "__main__":
    raise SystemExit(main())