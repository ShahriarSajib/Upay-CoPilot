"""Rebuild the claims table and markdown from an existing evidence report.

The full pipeline takes ~3 minutes, most of it refitting models whose outputs
do not change when only the claim rules or the renderer change. This script
reloads ``backend/reports/evidence_report.json``, recomputes the claims and
headline from :mod:`app.evaluation.pipeline`, rewrites the JSON and regenerates
``docs/evaluation_report.md``.

It must be run from the repository root with ``PYTHONPATH=backend``.

    python backend/scripts/rebuild_report.py
"""

from __future__ import annotations

import json

from app.evaluation.pipeline import REPORT_JSON, _headline, build_claims
from app.evaluation.report import write

STATUS_MARK = {
    "supported": "PASS",
    "mixed": "MIXED",
    "not_supported": "FAIL",
    "not_measured": "n/a",
}


def main() -> None:
    report = json.loads(REPORT_JSON.read_text(encoding="utf-8"))
    report["claims"] = build_claims(report)
    report["headline"] = _headline(report)
    REPORT_JSON.write_text(
        json.dumps(report, indent=2, default=str, ensure_ascii=False), encoding="utf-8"
    )
    doc = write(report)

    headline = report["headline"]
    print(
        f"claims: {headline['claims_supported']} supported, "
        f"{headline['claims_mixed']} mixed, "
        f"{headline['claims_not_supported']} not supported "
        f"(of {headline['claims_total']})"
    )
    for claim in report["claims"]:
        mark = STATUS_MARK.get(claim["status"], "????")
        value = claim["value"]
        if isinstance(value, str) and len(value) > 90:
            value = value[:87] + "..."
        print(f"  {mark:5s} {claim['id']:34s} {value}")
    print(f"\nwrote {REPORT_JSON}\nwrote {doc}")


if __name__ == "__main__":
    main()
