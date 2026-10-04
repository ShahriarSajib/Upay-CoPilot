-- upay Financial Life Copilot -- relational schema
--
-- The competition prototype reads data/generated/*.csv through app.db.store.
-- This DDL is the production shape: identical tables, identical accounting
-- rules, ready for governed real data. Load with:
--   psql "$DATABASE_URL" -f backend/app/db/schema.sql
--   python backend/scripts/load_postgres.py

CREATE TABLE IF NOT EXISTS users (
    user_id            TEXT PRIMARY KEY,
    age_group          TEXT NOT NULL,
    occupation         TEXT NOT NULL,
    location_type      TEXT NOT NULL,
    account_age_days   INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS wallets (
    wallet_id          TEXT PRIMARY KEY,
    user_id            TEXT NOT NULL REFERENCES users(user_id),
    wallet_type        TEXT NOT NULL
        CHECK (wallet_type IN ('upay', 'bank', 'cash', 'other_digital')),
    opening_balance    NUMERIC(14, 2) NOT NULL
);

CREATE TABLE IF NOT EXISTS income_events (
    income_id          TEXT PRIMARY KEY,
    user_id            TEXT NOT NULL REFERENCES users(user_id),
    timestamp          TIMESTAMPTZ NOT NULL,
    income_type        TEXT NOT NULL,
    amount             NUMERIC(14, 2) NOT NULL CHECK (amount > 0),
    regularity         TEXT NOT NULL
        CHECK (regularity IN ('regular', 'irregular', 'seasonal')),
    source             TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS recurring_expenses (
    recurring_id       TEXT PRIMARY KEY,
    user_id            TEXT NOT NULL REFERENCES users(user_id),
    expense_name       TEXT NOT NULL,
    category           TEXT NOT NULL,
    amount             NUMERIC(14, 2) NOT NULL,
    frequency          TEXT NOT NULL DEFAULT 'monthly',
    next_due_date      DATE NOT NULL,
    mandatory          BOOLEAN NOT NULL DEFAULT FALSE,
    due_day            SMALLINT NOT NULL CHECK (due_day BETWEEN 1 AND 31)
);

-- Cash legs and user-to-user transfers move money between wallets. They are
-- excluded from income and consumption by CONSUMPTION_MASK so both sides of
-- the ledger stay consistent with the offline analytics.
CREATE TABLE IF NOT EXISTS transactions (
    transaction_id           TEXT PRIMARY KEY,
    user_id                  TEXT NOT NULL REFERENCES users(user_id),
    wallet_id                TEXT NOT NULL REFERENCES wallets(wallet_id),
    timestamp                TIMESTAMPTZ NOT NULL,
    transaction_type         TEXT NOT NULL,
    direction                TEXT NOT NULL CHECK (direction IN ('inflow', 'outflow')),
    amount                   NUMERIC(14, 2) NOT NULL CHECK (amount > 0),
    category                 TEXT NOT NULL,
    subcategory              TEXT NOT NULL,
    merchant_type            TEXT NOT NULL,
    channel                  TEXT NOT NULL,
    cash_out                 BOOLEAN NOT NULL DEFAULT FALSE,
    balance_after            NUMERIC(14, 2) NOT NULL,
    related_transaction_id   TEXT REFERENCES transactions(transaction_id),
    income_event_id          TEXT REFERENCES income_events(income_id),
    recurring_id             TEXT REFERENCES recurring_expenses(recurring_id),
    fee_amount               NUMERIC(14, 2) NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS financial_goals (
    goal_id           TEXT PRIMARY KEY,
    user_id           TEXT NOT NULL REFERENCES users(user_id),
    goal_name         TEXT NOT NULL,
    target_amount     NUMERIC(14, 2) NOT NULL CHECK (target_amount > 0),
    current_amount    NUMERIC(14, 2) NOT NULL DEFAULT 0,
    target_date       DATE NOT NULL,
    priority          TEXT NOT NULL CHECK (priority IN ('high', 'medium', 'low')),
    created_date      DATE NOT NULL,
    horizon_months    SMALLINT NOT NULL,
    is_achieved       BOOLEAN NOT NULL DEFAULT FALSE,
    progress_ratio    DOUBLE PRECISION NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS goal_contributions (
    contribution_id   TEXT PRIMARY KEY,
    goal_id           TEXT NOT NULL REFERENCES financial_goals(goal_id),
    user_id           TEXT NOT NULL REFERENCES users(user_id),
    timestamp         TIMESTAMPTZ NOT NULL,
    amount            NUMERIC(14, 2) NOT NULL CHECK (amount > 0)
);

-- ---------------------------------------------------------------------------
-- Derived tables (materialised features). Populated by load_postgres.py.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS user_daily_flow (
    user_id        TEXT NOT NULL REFERENCES users(user_id),
    date           DATE NOT NULL,
    period         TEXT NOT NULL,
    income         NUMERIC(14, 2) NOT NULL DEFAULT 0,
    spend          NUMERIC(14, 2) NOT NULL DEFAULT 0,
    net            NUMERIC(14, 2) NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, date)
);

CREATE TABLE IF NOT EXISTS user_monthly_flow (
    user_id        TEXT NOT NULL REFERENCES users(user_id),
    period         TEXT NOT NULL,
    income         NUMERIC(14, 2) NOT NULL DEFAULT 0,
    spend          NUMERIC(14, 2) NOT NULL DEFAULT 0,
    surplus        NUMERIC(14, 2) NOT NULL DEFAULT 0,
    savings_rate   DOUBLE PRECISION NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, period)
);

-- Ground truth, research side only. Never joined into the feature store.
CREATE TABLE IF NOT EXISTS behavior_labels (
    user_id                    TEXT NOT NULL,
    period                     TEXT NOT NULL,
    end_month_shortage_label   SMALLINT NOT NULL,
    high_cash_dependency_label SMALLINT NOT NULL,
    irregular_income_label     SMALLINT NOT NULL,
    overspending_label         SMALLINT NOT NULL,
    goal_progress_label        SMALLINT NOT NULL,
    financial_pressure_label   SMALLINT NOT NULL,
    anomaly_count              INTEGER NOT NULL,
    PRIMARY KEY (user_id, period)
);

CREATE TABLE IF NOT EXISTS injected_patterns (
    pattern_id       BIGSERIAL PRIMARY KEY,
    user_id          TEXT NOT NULL,
    period           TEXT NOT NULL,
    pattern_type     TEXT NOT NULL,
    amount           NUMERIC(14, 2) NOT NULL,
    category         TEXT NOT NULL,
    timestamp        TIMESTAMPTZ NOT NULL,
    transaction_id   TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tx_user_time ON transactions (user_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_tx_time ON transactions (timestamp);
CREATE INDEX IF NOT EXISTS idx_tx_wallet ON transactions (wallet_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_tx_category ON transactions (user_id, category);
CREATE INDEX IF NOT EXISTS idx_income_user_time ON income_events (user_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_contrib_goal ON goal_contributions (goal_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_goals_user ON financial_goals (user_id, target_date);
CREATE INDEX IF NOT EXISTS idx_recurring_user ON recurring_expenses (user_id, due_day);
CREATE INDEX IF NOT EXISTS idx_daily_period ON user_daily_flow (period);

-- Cash wallets are identified by a cash_in ever having touched them; this view
-- centralises that rule so every consumer agrees.
CREATE OR REPLACE VIEW v_cash_wallets AS
SELECT DISTINCT wallet_id FROM transactions WHERE transaction_type = 'cash_in';

CREATE OR REPLACE VIEW v_consumption AS
SELECT *
FROM transactions
WHERE transaction_type NOT IN ('send_money', 'receive_money')
  AND category <> 'cash';

-- Daily income/spend used by every forecast and liquidity calculation.
CREATE OR REPLACE VIEW v_daily_flow AS
SELECT
    user_id,
    timestamp::date                                    AS date,
    to_char(timestamp, 'YYYY-MM')                      AS period,
    SUM(CASE WHEN direction = 'inflow'  THEN amount ELSE 0 END) AS income,
    SUM(CASE WHEN direction = 'outflow' THEN amount ELSE 0 END) AS spend
FROM v_consumption
GROUP BY user_id, timestamp::date, to_char(timestamp, 'YYYY-MM');
