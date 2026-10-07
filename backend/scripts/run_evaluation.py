"""Run the full evaluation suite and write both report formats.

    PYTHONPATH=backend python backend/scripts/run_evaluation.py
    PYTHONPATH=backend python backend/scripts/run_evaluation.py --markdown-only
    PYTHONPATH=backend python backend/scripts/run_evaluation.py --only llm --only customer_impact

``--markdown-only`` skips model fitting entirely and re-renders
``docs/evaluation_report.md`` from the JSON that is already on disk. It exists
because the claim rules and the renderer change far more often than the models
do, and a three-minute refit to check a table is a bad trade.

``--only`` runs a subset of blocks; anything it skips is simply absent from
the report, so the claims that depend on it report ``not_measured`` rather
than silently passing.
"""

from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--markdown-only",
        action="store_true",
        help="re-render docs/evaluation_report.md from the existing JSON",
    )
    parser.add_argument(
        "--only",
        action="append",
        default=None,
        metavar="BLOCK",
        help="run only this block (repeatable): forecasting, anomaly, "
        "segmentation, health, explainability, llm, customer_impact",
    )
    parser.add_argument("--quiet", action="store_true", help="do not print per-block progress")
    args = parser.parse_args(argv)

    if args.markdown_only:
        from app.evaluation.report import write

        path = write()
        print(f"wrote {path}")
        return 0

    from app.evaluation.pipeline import run

    report = run(verbose=not args.quiet, only=tuple(args.only) if args.only else None)
    return 0 if report.get("claims") else 1


if __name__ == "__main__":
    sys.exit(main())
