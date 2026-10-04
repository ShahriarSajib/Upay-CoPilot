"""Request/response contracts for the cash-flow forecast endpoints."""

from __future__ import annotations

from app.schemas.common import EngineResponse, ForecastPoint

__all__ = [
    "ALLOWED_HORIZONS",
    "ForecastPoint",
    "ForecastResponse",
    "ShortageWindow",
]

# Horizons the forecaster is measured on, in days.
ALLOWED_HORIZONS = (7, 14, 30, 60, 90)


class ShortageWindow(EngineResponse):
    """A contiguous stretch of days where the balance sits under the buffer."""

    start_date: str
    end_date: str
    days: int
    lowest_balance: float
    shortfall_at_low: float


class ForecastResponse(EngineResponse):
    """Daily cash-flow path plus the shortage probability it implies."""

    horizon_days: int
    target_period: str
    path: list[ForecastPoint] = []
    expected_income: float = 0.0
    expected_spend: float = 0.0
    expected_ending_balance: float = 0.0
    current_balance: float = 0.0
    min_projected_balance: float = 0.0
    min_projected_balance_date: str | None = None
    shortfall_probability: float = 0.0
    liquidity_pressure: str = "low"
    buffer_target: float = 0.0
    monte_carlo_paths: int = 0
    model: str = ""
    model_gate_weights: dict[str, float] = {}
    shortages: list[ShortageWindow] = []
    recurring_schedule: dict[str, float] = {}