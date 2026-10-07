"""Contract tests for the Evidence API.

The dashboard renders whatever this endpoint returns, so the endpoint is the
single place where a stale or internally inconsistent report could reach a
reader. These tests check the invariants a reader relies on:

* every claim carries the five fields the dashboard draws,
* every ``evidence_path`` actually resolves inside the report JSON, so a claim
  can never point at something that is not there,
* the headline counts are a recount of the claim table rather than a second,
  independently maintained number,
* section filtering cannot invent or lose a claim.

They read the report from disk and never run the pipeline.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.evaluation.pipeline import REPORT_JSON
from app.main import app

VALID_STATUS = {"supported", "mixed", "not_supported", "not_measured"}
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

client = TestClient(app)


def _report() -> dict:
    if not REPORT_JSON.exists():
        pytest.skip(
            "backend/reports/evidence_report.json is missing; "
            "run `PYTHONPATH=backend python -m app.evaluation.pipeline`"
        )
    return json.loads(REPORT_JSON.read_text(encoding="utf-8"))


def _resolve(payload: dict, path: str):
    node = payload
    for key in path.split("."):
        if not isinstance(node, dict) or key not in node:
            raise KeyError(path)
        node = node[key]
    return node


def test_status_endpoint_reports_the_artifact():
    body = client.get("/api/evidence/status").json()
    assert body["available"] is True
    assert body["path"].endswith("evidence_report.json")
    assert body["generated_at"]
    assert body["claims_total"] >= 1


def test_every_claim_is_renderable_and_backed_by_a_real_path():
    report = _report()
    claims = report["claims"]
    assert claims
    for claim in claims:
        assert set(claim) == {"id", "claim", "evidence_path", "value", "status"}
        assert claim["status"] in VALID_STATUS, claim["id"]
        assert isinstance(claim["claim"], str) and claim["claim"].strip()
        assert claim["value"] is not None
        _resolve(report, claim["evidence_path"])


def test_headline_counts_are_a_recount_of_the_claims():
    report = _report()
    headline = report["headline"]
    claims = report["claims"]
    tally = {status: 0 for status in VALID_STATUS}
    for claim in claims:
        tally[claim["status"]] += 1
    assert headline["claims_total"] == len(claims)
    assert headline["claims_supported"] == tally["supported"]
    assert headline["claims_mixed"] == tally["mixed"]
    assert headline["claims_not_supported"] == tally["not_supported"]


def test_claims_cannot_be_lost_or_invented_by_section_filtering():
    everything = client.get("/api/evidence").json()["claims"]
    for status in VALID_STATUS:
        filtered = client.get("/api/evidence/claims", params={"status": status}).json()
        assert filtered["count"] == sum(1 for claim in everything if claim["status"] == status)
    assert client.get("/api/evidence/claims").json()["count"] == len(everything)


@pytest.mark.parametrize("section", SECTIONS)
def test_section_filter_returns_exactly_that_section(section):
    body = client.get("/api/evidence", params={"section": section}).json()
    assert list(body) == [section]


def test_unknown_section_is_rejected_with_the_valid_set():
    response = client.get("/api/evidence", params={"section": "nope"})
    assert response.status_code == 400
    assert "claims" in response.json()["detail"]


def test_reload_rereads_the_artifact():
    response = client.post("/api/evidence/reload")
    assert response.status_code == 200
    assert client.get("/api/evidence/claims").json()["count"] >= 1
