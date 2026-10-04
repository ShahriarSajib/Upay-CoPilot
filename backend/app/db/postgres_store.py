"""PostgreSQL implementation of the FinancialStore read contract."""

from __future__ import annotations

from functools import lru_cache

import pandas as pd

from app.db.store import TABLES, daily_flow, month_windows, monthly_flow


class PostgresStore:
    """Read the production schema into the same frames used by embedded mode.

    psycopg is imported lazily so the explicit embedded fallback remains
    usable without installing database drivers.
    """

    def __init__(self, database_url: str) -> None:
        try:
            import psycopg
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise RuntimeError("Install the postgres extra to use PostgreSQL") from exc
        self._connection = psycopg.connect(database_url, autocommit=True)
        self.root = database_url
        self._tables: dict[str, pd.DataFrame] = {}
        self._as_of: pd.Timestamp | None = None
        self._periods: list[str] | None = None

    def table(self, name: str) -> pd.DataFrame:
        if name not in TABLES:
            raise ValueError(f"Unknown table {name!r}")
        if name not in self._tables:
            # Table names are a closed internal allow-list, never user input.
            self._tables[name] = pd.read_sql_query(
                f'SELECT * FROM "{name}"', self._connection
            )
            if name in {"transactions", "income_events", "goal_contributions", "injected_patterns"}:
                self._tables[name]["timestamp"] = pd.to_datetime(
                    self._tables[name]["timestamp"], utc=False
                )
            for column in ("target_date", "created_date", "next_due_date"):
                if column in self._tables[name]:
                    self._tables[name][column] = pd.to_datetime(self._tables[name][column])
        return self._tables[name]

    def users(self): return self.table("users")
    def wallets(self): return self.table("wallets")
    def transactions(self): return self.table("transactions")
    def income_events(self): return self.table("income_events")
    def recurring(self): return self.table("recurring_expenses")
    def goals(self): return self.table("financial_goals")
    def contributions(self): return self.table("goal_contributions")
    def profiles(self): return self.table("financial_profiles")
    def behavior_labels(self): return self.table("behavior_labels")
    def injected_patterns(self): return self.table("injected_patterns")

    def as_of_date(self) -> pd.Timestamp:
        if self._as_of is None:
            self._as_of = pd.Timestamp(self.transactions()["timestamp"].max()).normalize()
        return self._as_of

    def periods(self) -> list[str]:
        if self._periods is None:
            self._periods = sorted(monthly_flow(self.transactions())["period"].unique().tolist())
        return self._periods

    def daily_flow(self): return daily_flow(self.transactions())
    def monthly_flow(self): return monthly_flow(self.transactions())
    def month_windows(self): return month_windows(self.transactions())

    def close(self) -> None:
        self._connection.close()
