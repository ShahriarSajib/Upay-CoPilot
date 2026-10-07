"""Serve the evaluation evidence report to the Evidence Dashboard.

Deliberately unauthenticated. The payload describes the *product* -- model
metrics, claim outcomes, guard test results -- and contains no customer data:
every table in it is an aggregate over synthetic accounts, and the report
itself is committed to the repository as ``docs/evaluation_report.md``. Auth
here would buy nothing and would keep the one page that shows what the product
cannot do behind a login it does not need.

The report is produced offline by ``python -m app.evaluation.pipeline`` and
read from disk; this router never fits a model.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.evaluation.pipeline import REPORT_JSON

router = APIRouter(prefix="/api/evidence", tags=["evidence"])

_LOCK = threading.Lock()
_CACHE: dict[str, Any] = {"mtime": None, "payload": None}

# Sections a client may ask for on its own, so the dashboard can fetch the
# claims table without pulling every per-model diagnostic behind it.
SECTIONS = (
    "headline",
    "claims",
    "run",
    "dataset",
    "forecasting",
    "anomaly",
    "segmentation",
    "health",
    "explainability",
    "llm",
    "customer_impact",
)


def load_report(force: bool = False) -> dict:
    """Read the report once per file change; the file is a few MB at most."""
    if not REPORT_JSON.exists():
        raise HTTPException(
            404,
            detail=(
                "No evidence report on disk. Generate one with "
                "`PYTHONPATH=backend python -m app.evaluation.pipeline` "
                f"(expected at {REPORT_JSON})."
            ),
        )
    mtime = REPORT_JSON.stat().st_mtime
    with _LOCK:
        if not force and _CACHE["mtime"] == mtime and _CACHE["payload"] is not None:
            return _CACHE["payload"]
        try:
            payload = json.loads(REPORT_JSON.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise HTTPException(
                500, detail=f"evidence report is not valid JSON: {exc}"
            ) from exc
        _CACHE["mtime"] = mtime
        _CACHE["payload"] = payload
        return payload


def _summary(payload: dict) -> dict:
    return {
        "run": payload.get("run", {}),
        "dataset": payload.get("dataset", {}),
        "headline": payload.get("headline", {}),
        "claims": payload.get("claims", []),
    }


@router.get("")
def evidence(section: str | None = Query(default=None, description="one of: " + ", ".join(SECTIONS))):
    """Full report, or a single named section of it."""
    payload = load_report()
    if section is None:
        return payload
    if section not in SECTIONS:
        raise HTTPException(
            400, detail=f"unknown section '{section}'; expected one of {list(SECTIONS)}"
        )
    if section not in payload:
        raise HTTPException(
            404,
            detail=(
                f"section '{section}' is missing from this report -- the block "
                "did not run. Re-run the pipeline without --only to fill it in."
            ),
        )
    return {section: payload[section]}


@router.get("/summary")
def summary():
    """Claims and headline only -- what the top of the dashboard renders."""
    return _summary(load_report())


@router.get("/claims")
def claims(status: str | None = Query(default=None, description="supported | mixed | not_supported | not_measured")):
    payload = load_report()
    rows = payload.get("claims", [])
    if status:
        allowed = {"supported", "mixed", "not_supported", "not_measured"}
        if status not in allowed:
            raise HTTPException(400, detail=f"status must be one of {sorted(allowed)}")
        rows = [row for row in rows if row.get("status") == status]
    return {"count": len(rows), "claims": rows}


@router.get("/status")
def status():
    """Whether a report exists, and when it was generated -- no payload."""
    if not REPORT_JSON.exists():
        return {"available": False, "path": str(REPORT_JSON), "reason": "report not generated"}
    payload = load_report()
    run = payload.get("run", {})
    return {
        "available": True,
        "path": str(REPORT_JSON),
        "generated_at": run.get("generated_at"),
        "total_seconds": run.get("total_seconds"),
        "blocks_run": run.get("blocks_run", []),
        "claims_total": len(payload.get("claims", [])),
        "claims_supported": (payload.get("headline") or {}).get("claims_supported"),
    }


@router.post("/reload", status_code=200)
def reload_report():
    """Drop the in-memory cache so an externally regenerated report is visible."""
    payload = load_report(force=True)
    return {"reloaded": True, "generated_at": (payload.get("run") or {}).get("generated_at")}


def report_path() -> Path:
    return REPORT_JSON
