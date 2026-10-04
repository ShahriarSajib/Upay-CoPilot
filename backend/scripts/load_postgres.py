"""Apply schema.sql and load the generated CSV tables into PostgreSQL.

Usage: python backend/scripts/load_postgres.py [--data-root data/generated]
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

import psycopg
from psycopg import sql

ROOT = Path(__file__).resolve().parents[2]
TABLE_ORDER = [
    "users", "wallets", "income_events", "recurring_expenses", "transactions",
    "financial_goals", "goal_contributions", "financial_profiles",
    "behavior_labels", "injected_patterns",
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", default=None)
    parser.add_argument("--data-root", type=Path, default=ROOT / "data" / "generated")
    args = parser.parse_args()
    import os
    database_url = args.database_url or os.environ.get("DATABASE_URL")
    if not database_url:
        from app.core.config import settings

        database_url = settings.database_url
    if not database_url:
        parser.error("--database-url or DATABASE_URL is required")
    with psycopg.connect(database_url) as conn:
        conn.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
        conn.execute((ROOT / "backend" / "app" / "db" / "schema.sql").read_text())
        for table in TABLE_ORDER:
            path = args.data_root / f"{table}.csv"
            if not path.exists():
                continue
            with path.open(newline="", encoding="utf-8") as source:
                rows = list(csv.DictReader(source))
            if not rows:
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
        conn.commit()


if __name__ == "__main__":
    main()
