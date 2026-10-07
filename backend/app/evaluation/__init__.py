"""Offline evaluation for the upay Financial Life Copilot.

This package is the project's **AI validation lab**. It answers, with numbers,
the questions a judge should ask:

* Do the models beat simple baselines on data they have never seen?
* Is the split genuinely temporal, and is the test window untouched?
* Are the explanations real attributions (SHAP), not prose?
* Is the LLM grounded, tool-bounded and resistant to prompt injection?
* Do the recommendations change *measured* outcomes in a controlled
  simulation?

Design rules
------------
1. **The test window is read once, at the end.** Thresholds, hyperparameters
   and gates are fitted on train/validation only.
2. **Every headline number ships next to its baseline.** A metric with nothing
   to beat is not evidence.
3. **Ground truth is used for scoring, never for fitting**, except where the
   task is explicitly supervised.
4. **Everything is reproducible.** Fixed seeds, fixed windows, a single entry
   point (:func:`app.evaluation.pipeline.run_all`).

The single entry point writes:

* ``backend/reports/evidence_report.json`` -- machine readable, served by
  ``GET /api/evidence``
* ``docs/evaluation_report.md``            -- the human readable version
"""

from __future__ import annotations

__all__ = ["run_all"]


def run_all(*args, **kwargs):
    from app.evaluation.pipeline import run_all as _run_all

    return _run_all(*args, **kwargs)
