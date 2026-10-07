"""Render the evidence report as ``docs/evaluation_report.md``.

The JSON is the source of truth and the API serves it; this module exists so
the same numbers are readable in a repository that has no running backend.

Two rules shape the output:

* **Every number carries its baseline.** A model metric without the thing it
  was compared against is not evidence, so the renderer never prints a
  precision, an F1 or an MAE on its own.
* **Failures are printed at the same size as passes.** The claims table is
  sorted by status in the order ``not_supported``, ``mixed``, ``supported``,
  so the first thing a reader sees is what did not hold.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.evaluation.pipeline import REPORT_JSON, build_claims

REPO_ROOT = Path(__file__).resolve().parents[3]
DOC_PATH = REPO_ROOT / "docs" / "evaluation_report.md"

STATUS_LABEL = {
    "supported": "PASS",
    "mixed": "MIXED",
    "not_supported": "FAIL",
    "not_measured": "n/a",
}
STATUS_ORDER = {"not_supported": 0, "mixed": 1, "not_measured": 2, "supported": 3}


def _fmt(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        if abs(value) >= 100:
            return f"{value:,.1f}"
        return f"{value:.4f}".rstrip("0").rstrip(".")
    if isinstance(value, int):
        return f"{value:,}"
    return str(value)


def _table(headers: list[str], rows: list[list[Any]]) -> str:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(_fmt(cell) for cell in row) + " |")
    return "\n".join(lines)


def render(report: dict | None = None) -> str:
    if report is None:
        report = json.loads(REPORT_JSON.read_text(encoding="utf-8"))
    claims = report.get("claims") or build_claims(report)
    claims = sorted(claims, key=lambda c: (STATUS_ORDER.get(c["status"], 9), c["id"]))

    out: list[str] = []
    add = out.append

    add("# Evaluation report")
    add("")
    run = report.get("run", {})
    add(
        f"Generated {run.get('generated_at', 'unknown')} from seed "
        f"`{run.get('seed')}` against `{run.get('split_path')}` in "
        f"{run.get('total_seconds', 'n/a')}s."
    )
    add("")
    add("Reproduce with:")
    add("")
    add("```bash")
    add("PYTHONPATH=backend python -m app.evaluation.pipeline")
    add("```")
    add("")

    # -- headline ---------------------------------------------------------
    add("## Headline")
    add("")
    headline = report.get("headline", {})
    counts = (
        f"{headline.get('claims_supported', 0)} supported, "
        f"{headline.get('claims_mixed', 0)} mixed, "
        f"{headline.get('claims_not_supported', 0)} not supported "
        f"(of {headline.get('claims_total', 0)})"
    )
    add(f"**{counts}.**")
    add("")
    headline_rows = [
        ["Spend forecast vs best naive baseline", f"{_fmt(headline.get('spend_forecast_improvement_percent'))}%"],
        ["Income forecast vs best naive baseline", f"{_fmt(headline.get('income_forecast_improvement_percent'))}%"],
        ["Anomaly detector F1 (test)", _fmt(headline.get("anomaly_f1"))],
        ["Anomaly detector vs best naive rule", f"+{_fmt(headline.get('anomaly_improvement_over_best_rule_percent'))}%"],
        ["Anomalous taka put in front of the customer", f"{_fmt(headline.get('anomaly_value_coverage'))}"],
        ["Segmentation temporal stability (ARI)", _fmt(headline.get("segmentation_stability_ari"))],
        ["Retrieval recall@3", _fmt(headline.get("retrieval_recall_at_3"))],
        ["Guard false positives on legitimate questions", _fmt(headline.get("guard_legitimate_false_positive_rate"))],
        ["Live provider suite", _fmt(headline.get("live_llm_suite_status"))],
        ["Simulation placebo moved nothing", _fmt(headline.get("placebo_harness_sensitive"))],
        ["Customers able to follow a saving plan", f"{_fmt(headline.get('customers_able_to_save'))}"],
    ]
    add(_table(["Measure", "Value"], headline_rows))
    add("")

    # -- claims -----------------------------------------------------------
    add("## Claims")
    add("")
    add(
        "Each claim states what would have to be true *before* the run; the "
        "thresholds live in `app/evaluation/pipeline.py::CLAIM_RULES`. Rows are "
        "sorted so that what did not hold appears first."
    )
    add("")
    add(
        _table(
            ["Status", "Claim", "Value", "Evidence"],
            [
                [STATUS_LABEL.get(c["status"], "????"), c["claim"], c["value"], f"`{c['evidence_path']}`"]
                for c in claims
            ],
        )
    )
    add("")

    # -- protocol ---------------------------------------------------------
    add("## Protocol")
    add("")
    dataset = report.get("dataset", {})
    split_rows = [
        [
            s.get("split"),
            s.get("period_range"),
            f"{s.get('transactions'):,}" if isinstance(s.get("transactions"), int) else s.get("transactions"),
            s.get("injected_anomalies"),
        ]
        for s in dataset.get("splits", [])
    ]
    add(_table(["Split", "Periods", "Transactions", "Injected anomalies"], split_rows))
    add("")
    add(
        "Train is used to fit every model, validation to choose hyperparameters "
        "and thresholds, and test is scored once by the block that needs it. "
        "Windows are disjoint by construction; `dataset.disjoint` in the report "
        "records the check. Ground-truth tables (personas, injected patterns, "
        "behaviour flags) are used for scoring only and are listed as such."
    )
    add("")

    _section_forecasting(add, report)
    _section_anomaly(add, report)
    _section_segmentation(add, report)
    _section_health(add, report)
    _section_explain(add, report)
    _section_llm(add, report)
    _section_impact(add, report)

    # -- weaknesses -------------------------------------------------------
    add("## What did not hold")
    add("")
    failed = [c for c in claims if c["status"] in ("not_supported", "mixed")]
    if not failed:
        add("Nothing.")
    else:
        add(_table(
            ["Status", "Claim", "Value"],
            [[STATUS_LABEL.get(c["status"], "????"), c["claim"], c["value"]] for c in failed],
        ))
    add("")

    add("## Known data defects")
    add("")
    quality = _label_quality(report)
    if quality:
        for row in quality:
            add(f"- {row}")
    else:
        add("- none reported")
    add("")

    add("---")
    add("")
    add(
        "Every figure above comes from `backend/reports/evidence_report.json`, "
        "which is what the Evidence Dashboard in the app serves. Nothing in "
        "this document is entered by hand."
    )
    add("")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Sections
# ---------------------------------------------------------------------------

def _section_forecasting(add, report: dict) -> None:
    block = report.get("forecasting") or {}
    if not block:
        return
    add("## Forecasting")
    add("")
    add(f"Task: {block.get('task', 'n/a')}")
    add("")
    rows = []
    for target, entry in (block.get("summary") or {}).items():
        rows.append(
            [
                target,
                entry.get("test_best_baseline"),
                _fmt(entry.get("test_best_baseline_mae")),
                entry.get("test_best_model"),
                _fmt(entry.get("test_best_model_mae")),
                f"{_fmt(entry.get('test_improvement_over_best_baseline_percent'))}%",
            ]
        )
    add(_table(
        ["Target", "Best baseline", "Baseline MAE", "Shipped model", "Model MAE", "Improvement"],
        rows,
    ))
    add("")


def _section_anomaly(add, report: dict) -> None:
    block = report.get("anomaly") or {}
    if not block:
        return
    add("## Anomaly detection")
    add("")
    head = block.get("headline", {})
    operating = block.get("operating_point", {})
    add(
        f"Detector `{block.get('detector')}`, contamination "
        f"`{operating.get('contamination')}` chosen on "
        f"{operating.get('chosen_on')}. Ground truth: {block.get('ground_truth')}."
    )
    add("")
    windows = block.get("windows", {})
    rows = [
        [
            name,
            _fmt(w.get("n_scored_transactions")),
            _fmt((w.get("model") or {}).get("precision")),
            _fmt((w.get("model") or {}).get("recall")),
            _fmt((w.get("model") or {}).get("f1")),
            _fmt((w.get("model") or {}).get("average_precision")),
            _fmt((w.get("model") or {}).get("precision_at_k")),
            _fmt((w.get("model") or {}).get("false_positive_rate")),
        ]
        for name, w in windows.items()
    ]
    add(_table(
        ["Window", "n", "Precision", "Recall", "F1", "AP", "P@50", "FPR"],
        rows,
    ))
    add("")
    rules = [
        [
            name,
            (w.get("headline") or {}).get("best_naive_rule"),
            _fmt((w.get("headline") or {}).get("best_naive_rule_f1")),
            f"{_fmt((w.get('headline') or {}).get('f1_improvement_over_best_rule_percent'))}%",
        ]
        for name, w in windows.items()
    ]
    add(_table(["Window", "Best naive rule", "Rule F1", "Detector improvement"], rules))
    add("")
    recall = (windows.get("test") or {}).get("by_pattern")
    if recall:
        add("Recall by injected pattern (test):")
        add("")
        add(
            _table(
                ["Pattern", "Injected", "Detected", "Recall"],
                [
                    [name, v.get("injected"), v.get("detected"), _fmt(v.get("recall"))]
                    for name, v in recall.items()
                ],
            )
        )
        add("")


def _section_segmentation(add, report: dict) -> None:
    block = report.get("segmentation") or {}
    if not block:
        return
    add("## Segmentation")
    add("")
    add(
        f"k = {block.get('n_clusters')} chosen by {block.get('chosen_by')} over "
        f"{block.get('population_size')} customers."
    )
    add("")
    curve = block.get("internal_metrics", {}).get("silhouette_by_k") or block.get("silhouette_by_k")
    if isinstance(curve, dict):
        add(_table(["k", "Silhouette"], [[k, v] for k, v in curve.items()]))
        add("")
    persona = block.get("persona_alignment", {})
    stability = block.get("temporal_stability", {})
    add(_table(
        ["Check", "Metric", "Value"],
        [
            ["Agreement with generator personas (ARI)", "ARI", _fmt(persona.get("adjusted_rand_index"))],
            ["Agreement with generator personas (NMI)", "NMI", _fmt(persona.get("normalized_mutual_information"))],
            ["Customers compared", "n", _fmt(persona.get("n"))],
            ["Temporal stability across time cuts (ARI)", "ARI", _fmt(stability.get("adjusted_rand_index"))],
            ["Temporal stability: identical assignments", "share", _fmt(stability.get("identical_assignment_share"))],
        ],
    ))
    add("")


def _section_health(add, report: dict) -> None:
    health = report.get("health") or {}
    if not health:
        return
    add("## Financial health models")
    add("")
    profile = health.get("profile_calibration", {})
    if profile.get("fitted"):
        add(f"Profile recovery: {profile.get('task', '')}")
        add("")
        verdicts = profile.get("evaluation", {}).get("honest_verdict", [])
        add(_table(
            ["Target", "Type", "Verdict", "Model", "Baseline"],
            [
                [
                    v.get("target"),
                    v.get("task"),
                    v.get("verdict"),
                    _fmt(v.get("model_mae") if v.get("task") == "regression" else v.get("model_f1")),
                    _fmt(v.get("direct_feature_baseline_mae") if v.get("task") == "regression" else v.get("majority_baseline_f1")),
                ]
                for v in verdicts
            ],
        ))
        add("")
        caveat = profile.get("evaluation", {}).get("caveat")
        if caveat:
            add(f"> {caveat}")
            add("")

    early = health.get("early_warning", {})
    if early.get("fitted"):
        add(f"Early warning: {early.get('task', '')}")
        add("")
        add(_table(
            ["Target", "Constant", "Persistence", "Best model", "Best F1", "vs persistence"],
            [
                [
                    name,
                    _fmt((entry.get("models") or {}).get("constant", {}).get("f1")),
                    _fmt((entry.get("models") or {}).get("persistence", {}).get("f1")),
                    entry.get("best_model"),
                    _fmt(entry.get("best_model_f1")),
                    f"{_fmt(entry.get('improvement_over_persistence_percent'))}%",
                ]
                for name, entry in (early.get("targets") or {}).items()
            ],
        ))
        add("")


def _section_explain(add, report: dict) -> None:
    block = report.get("explainability") or {}
    if not block:
        return
    add("## Explainability")
    add("")
    add(f"Method: {block.get('method', 'n/a')}")
    add("")
    aggregate = block.get("aggregate", {})
    add(
        "Checks per target: fidelity (does the explanation reproduce the "
        "model), faithfulness (does removing a top feature move the model the "
        "way the explanation says), stability (do two windows name the same "
        "drivers), sanity (do the attributions collapse when inputs are "
        "shuffled)."
    )
    add("")
    add(_table(
        ["Target", "Fidelity max rel. error", "Faithfulness (chance 0.5)", "Stability Spearman", "Decorrelation"],
        [
            [
                name,
                _fmt((entry.get("fidelity") or {}).get("relative_to_prediction_scale")),
                _fmt((entry.get("faithfulness") or {}).get("direction_agreement")),
                _fmt((entry.get("stability") or {}).get("spearman")),
                _fmt((entry.get("sanity") or {}).get("mean_attribution_decorrelation")),
            ]
            for name, entry in (block.get("targets") or {}).items()
        ],
    ))
    add("")
    if aggregate:
        add("Worst target across all checks:")
        add("")
        add(_table(
            ["Check", "Worst value"],
            [
                ["Fidelity relative error", _fmt(aggregate.get("fidelity_worst_relative_error"))],
                ["Faithfulness direction agreement", _fmt(aggregate.get("faithfulness_min_direction_agreement"))],
                ["Stability Spearman", _fmt(aggregate.get("stability_min_spearman"))],
                ["Attribution decorrelation", _fmt(aggregate.get("sanity_worst_mean_attribution_decorrelation"))],
            ],
        ))
        add("")


def _section_llm(add, report: dict) -> None:
    block = report.get("llm") or {}
    if not block:
        return
    add("## Copilot: safety and grounding")
    add("")
    headline = block.get("headline", {})
    add(_table(
        ["Check", "Result"],
        [[k, _fmt(v)] for k, v in headline.items()],
    ))
    add("")
    grounding = block.get("grounding", {})
    if grounding.get("out_of_scope"):
        add(
            f"Out-of-scope refusal rate: "
            f"{_fmt(grounding['out_of_scope'].get('refusal_rate'))} "
            f"over {grounding['out_of_scope'].get('n')} cases."
        )
        add("")
    live = block.get("live", {})
    if live.get("status") != "executed":
        add(
            f"**Live provider suite: {live.get('status')}.** "
            f"{live.get('reason') or live.get('note') or ''} This is coverage "
            "the evaluation does *not* have; the offline suites above still ran."
        )
        add("")


def _section_impact(add, report: dict) -> None:
    block = report.get("customer_impact") or {}
    if not block:
        return
    add("## Customer impact")
    add("")
    detection = block.get("detection_value", {})
    if detection.get("available"):
        add("Detection value, measured in taka on the untouched test window:")
        add("")
        add(_table(
            ["Measure", "Value"],
            [
                ["Anomalous taka in the window", _fmt(detection.get("total_anomalous_value"))],
                ["Anomalous taka flagged", _fmt(detection.get("caught_anomalous_value"))],
                ["Coverage", f"{_fmt(detection.get('value_coverage'))}"],
                ["Taka wrongly flagged", _fmt(detection.get("false_positive_value"))],
                ["Wrongly flagged share of what was shown", f"{_fmt(detection.get('wrongly_flagged_share_of_flagged_value'))}"],
            ],
        ))
        add("")
        by_pattern = detection.get("by_pattern", {})
        if by_pattern:
            add(_table(
                ["Injected pattern", "Events", "Detected", "Value coverage"],
                [
                    [name, v.get("events"), v.get("detected"), f"{_fmt(v.get('value_coverage'))}"]
                    for name, v in by_pattern.items()
                ],
            ))
            add("")

    deficit = block.get("deficit_warnings", {})
    if deficit.get("available"):
        add(f"Deficit warnings: {deficit.get('task')}")
        add("")
        add(
            f"Best model `{deficit.get('best_model')}` F1 "
            f"{_fmt(deficit.get('best_model_f1'))}, "
            f"{_fmt(deficit.get('improvement_over_persistence_percent'))}% over "
            "persistence. Outcome: " + str(deficit.get("outcome_source"))
        )
        add("")
        action = deficit.get("actionability", {})
        add(_table(
            ["Warnings emitted", "Correct", "Novel", "Novel share", "Missed"],
            [[
                action.get("warnings_emitted"),
                action.get("warnings_correct"),
                action.get("novel_warnings"),
                f"{_fmt(action.get('novel_warning_share'))}",
                action.get("deficits_missed"),
            ]],
        ))
        add("")

    simulation = block.get("simulation", {})
    if simulation.get("available"):
        placebo = simulation.get("placebo", {})
        add(
            f"Simulation on {simulation.get('population', {}).get('n_customers')} "
            "customers from the product population. Placebo (no intervention) "
            f"moved nothing: {placebo.get('harness_sensitive')}."
        )
        add("")
        rows = []
        for name, arm in (simulation.get("interventions") or {}).items():
            rows.append(
                [
                    name,
                    arm.get("policy"),
                    _fmt(arm.get("mean_balance_change")),
                    _fmt(arm.get("mean_net_worth_change")),
                    _fmt(arm.get("mean_goals_unlocked")),
                ]
            )
        add(_table(
            ["Arm", "Policy", "Mean spendable balance change", "Mean net worth change", "Mean goals unlocked"],
            rows,
        ))
        add("")
        actionability = simulation.get("recommendation_actionability", {})
        if actionability:
            add(_table(
                ["Measure", "Value"],
                [[k, v] for k, v in actionability.items() if k != "population_finding"],
            ))
            add("")
            finding = actionability.get("population_finding")
            if finding:
                add(f"> {finding}")
                add("")


def _label_quality(report: dict) -> list[str]:
    quality = ((report.get("health") or {}).get("label_quality")) or {}
    rows: list[str] = []
    for key in ("duplicate_columns", "constant_columns", "notes", "findings"):
        value = quality.get(key)
        if isinstance(value, list):
            rows.extend(str(v) for v in value)
        elif isinstance(value, dict):
            rows.extend(f"{k}: {v}" for k, v in value.items())
        elif value:
            rows.append(str(value))
    return rows


def write(report: dict | None = None, path: Path = DOC_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(report), encoding="utf-8")
    return path


if __name__ == "__main__":  # pragma: no cover
    written = write()
    print(f"wrote {written}")
