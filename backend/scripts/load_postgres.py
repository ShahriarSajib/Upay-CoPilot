"""Apply schema.sql and load the generated CSV tables into PostgreSQL.

Usage: python backend/scripts/load_postgres.py [--data-root data/dev]
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import psycopg
from psycopg import sql

ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = ROOT / "backend"
# Running this file directly puts backend/scripts on sys.path, not backend, so the
# application package has to be made importable before app.* can be used.
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

TABLE_ORDER = [
    "users", "wallets", "income_events", "recurring_expenses", "transactions",
    "financial_goals", "goal_contributions", "financial_profiles",
    "behavior_labels", "injected_patterns",
]


def database_url_from_settings() -> str:
    """Read backend/.env the same way the API does, including DATABASE_URL."""
    from app.core.config import settings

    return settings.database_url


def load_derived_tables(conn, data_root: Path) -> dict[str, int]:
    """Repopulate user_daily_flow / user_monthly_flow from the loaded CSVs.

    These are materialised features: the schema declares them, so a load that
    leaves them stale would quietly serve pre-load numbers to anything that
    reads them. The accounting rules mirror app.db.store.
    """
    if not (data_root / "transactions.csv").exists():
        return {}
    import pandas as pd

    from app.db.store import daily_flow, monthly_flow

    transactions = pd.read_csv(
        data_root / "transactions.csv",
        parse_dates=["timestamp"],
        keep_default_na=True,
    )
    counts: dict[str, int] = {}
    with conn.cursor() as cursor:
        cursor.execute("TRUNCATE TABLE user_daily_flow, user_monthly_flow")
        for name, frame in (
            ("user_daily_flow", daily_flow(transactions)),
            ("user_monthly_flow", monthly_flow(transactions)),
        ):
            columns = list(frame.columns)
            statement = sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
                sql.Identifier(name),
                sql.SQL(", ").join(map(sql.Identifier, columns)),
                sql.SQL(", ").join(sql.Placeholder() for _ in columns),
            )
            values = [
                [None if pd.isna(value) else value for value in row]
                for row in frame.itertuples(index=False, name=None)
            ]
            cursor.executemany(statement, values)
            counts[name] = len(values)
    return counts


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--data-root", type=Path, default=ROOT / "data" / "generated")
    parser.add_argument(
        "--skip-derived",
        action="store_true",
        help="do not repopulate user_daily_flow / user_monthly_flow",
    )
    args = parser.parse_args()
    database_url = args.database_url or database_url_from_settings()
    if not database_url:
        parser.error("--database-url or DATABASE_URL is required")
    if not args.data_root.exists():
        parser.error(f"data root not found: {args.data_root}")
    with psycopg.connect(database_url) as conn:
        conn.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
        conn.execute((BACKEND_ROOT / "app" / "db" / "schema.sql").read_text())
        loaded: dict[str, int] = {}
        for table in TABLE_ORDER:
            path = args.data_root / f"{table}.csv"
            if not path.exists():
                print(f"skip {table}: {path.name} not present")
                continue
            with path.open(newline="", encoding="utf-8") as source:
                rows = list(csv.DictReader(source))
            if not rows:
                print(f"skip {table}: no rows")
                continue
            columns = list(rows[0])
            conn.execute(sql.SQL("TRUNCATE TABLE {} CASCADE").format(sql.Identifier(table)))
            statement = sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
                sql.Identifier(table),
                sql.SQL(", ").join(map(sql.Identifier, columns)),
                sql.SQL(", ").join(sql.Placeholder() for _ in columns),
            )
            values = [[None if value == "" else value for value in row.values()] for row in rows]
            with conn.cursor() as cursor:
                cursor.executemany(statement, values)
            loaded[table] = len(values)
            print(f"loaded {table}: {len(values)} rows")
        if not args.skip_derived:
            for name, count in load_derived_tables(conn, args.data_root).items():
                print(f"loaded {name}: {count} rows")
        conn.commit()
    print(f"done: {sum(loaded.values())} rows across {len(loaded)} tables from {args.data_root}")


if __name__ == "__main__":
    main()
