<div align="center">

# upay Financial Life Copilot

**An evidence-first, bilingual financial independence assistant for upay customers.**

Every number this product shows is computed by a deterministic engine and ships with
its inputs, method, confidence and assumptions. The language model never calculates.

[React](https://react.dev) · [TypeScript](https://www.typescriptlang.org) · [Vite](https://vite.dev) · [FastAPI](https://fastapi.tiangolo.com) · [LightGBM](https://lightgbm.readthedocs.io) · [PostgreSQL](https://www.postgresql.org)

</div>

---

## Table of Contents

- [Overview](#overview)
- [The Five Rules](#the-five-rules)
- [Architecture](#architecture)
- [Feature Modules](#feature-modules)
- [Tech Stack](#tech-stack)
- [Repository Layout](#repository-layout)
- [Quick Start](#quick-start)
- [Data Pipeline](#data-pipeline)
- [ML Models](#ml-models)
- [API Reference](#api-reference)
- [LLM Layer](#llm-layer)
- [Frontend](#frontend)
- [Database](#database)
- [Testing](#testing)
- [Configuration](#configuration)
- [Evaluation Results](#evaluation-results)
- [Roadmap](#roadmap)
- [License](#license)

---

## Overview

upay Financial Life Copilot turns a customer's raw transaction history into clear,
evidence-backed guidance for **financial independence**: where the money goes, what
next month looks like, which goal to fund next, and what to do when plans break.

The product is built for four cohorts — gig workers, salary employees, small business
owners and micro-entrepreneurs — across eight synthetic personas that act as
**design and evaluation ground truth only**, never as model inputs.

| | |
|---|---|
| **Languages** | English, বাংলা (Bangla), Banglish input normalisation |
| **Numerals** | Toggleable Latin ↔ Bangla digits across all charts and copy |
| **Voice** | Browser `SpeechRecognition` in, `speechSynthesis` out, both degrade gracefully |
| **Data** | 100% synthetic. No real customer data is used, stored or required |
| **Pages** | 16 routes, code-split, mobile-first at 360 px |
| **Tests** | 76 tests (59 dataset invariants, 17 service/API) |

### What makes it different

Most "AI financial assistants" hand a language model the customer's transactions and
ask it to reason. This one does not. The LLM is an **explanation layer over an
allowlisted tool surface** — it can rephrase, translate, summarise and refuse. It
cannot compute, cannot write, cannot transfer money and cannot approve credit. That
boundary is provable by reading `backend/app/llm/tools.py` in 85 lines.

---

## The Five Rules

These are non-negotiable and enforced in code, not just documented.

1. **The LLM never calculates.** Every figure originates in a deterministic engine
   (`backend/app/engines/`, `frontend/src/engines/`). The assistant may only rephrase,
   translate, summarise and refuse.
2. **No naked numbers.** Every user-facing figure carries `Evidence` — inputs, method,
   confidence (0–1 + plain-language reason), assumptions, source tables.
3. **No autonomous decisions.** No score changes, no lending decisions, no transfers,
   no arbitrary SQL or shell, no persisted financial advice.
4. **No ground-truth leakage.** `persona`, `is_anomaly`, `pattern_type` and behaviour
   labels are evaluation-only. `scripts/leakage_check.py` fails the build if any appear
   in a `features/` file.
5. **Refuse first.** Out-of-scope requests are blocked before any tool executes.

---

## Architecture

```
Synthetic transactions
        ↓
Financial Context Engine          ← one immutable per-customer context
        ↓                             no page ever reads raw data
Deterministic engines              ← health, spending, forecast, goals, simulator,
        ↓                             emergency, cash-out, sources, resilience,
Financial Evidence                 credit, literacy, bills, segmentation
        ↓                             metrics · confidence · reasons · assumptions
Explanation layer                  ← bilingual, Banglish-tolerant, voice in/out,
        ↓                             refusal-first, tool-calling
Customer action                    ← one prioritised action at a time, user-initiated
        ↓
Measurable outcome                 ← evaluated against held-out labels
```

**Two runnable implementations.** The frontend is a self-contained prototype that loads
a static JSON snapshot and runs every engine in the browser — no backend required. The
FastAPI service runs the same engine contracts server-side with Python ML models and
the LLM tool layer. Both satisfy the same evidence contract, so the React components
keep their contract when engines move behind typed endpoints.

---

## Feature Modules

| # | Module | Engine output | Route | Safety constraint |
|---|---|---|---|---|
| 1 | Financial Health Coach | Weighted multi-dimension score, positives, concerns, low-balance days | `/health` | Weights are fixed product assumptions, never fitted per customer |
| 2 | Smart Spending | Unusual transactions, recurring detection, money leaks, essential/discretionary split, end-of-month concentration | `/spending` | Detections carry a stated rule, not a judgement |
| 3 | Cash-Flow Forecasting | Balance projection at 7/14/30/60/90 days, income schedule, obligation calendar, buffer breach | `/forecast` | Baseline comparison reported beside every model figure |
| 4 | Bills & Obligations | Per-due-date schedule: balance before → bill → balance after, income coverage | `/bills` | Read-only; cannot pay or reschedule |
| 5 | Goal & Savings Planning | Feasibility per goal, surplus capacity, 3 allocation scenarios | `/goals` | Shows shortfall honestly, never assumes a raise |
| 6 | What-If Simulator | Shock scenarios: job loss, income drop, big expense | `/simulator` | Labelled hypothetical; never persisted as a prediction |
| 7 | Emergency Fund Planning | Target in months of essential spend, monthly contribution, gap | `/emergency-fund` | Target formula is explicit |
| 8 | Cash-Out Dependency | Net cash-out, liquidity need, dependency band | `/cash-out` | Descriptive, never moralising |
| 9 | Money Sources | Income-source stability, source concentration, wallet liquidity | `/money-sources` | `other_digital` excluded from liquid balance by design |
| 10 | Resilience | Shock-absorption dimensions, weakest link | `/resilience` | States what would break the plan |
| 11 | Responsible Credit Readiness | Readiness bands, hypothetical affordability, obligation load | `/credit-readiness` | **Never a lending decision; no approval or rejection** |
| 12 | Financial Literacy | Signal-triggered lessons, quizzes, dormant topics | `/learning` | Teaches behaviour, not products |
| 13 | Ask upay (assistant) | Intent → tool trace → answer + citations | `/assistant` | Scope check first; refusals are first-class output |
| 14 | Monthly Review | Month summary, action centre, anomalies, categories | `/review` | Anomalies shown as "review this", never "fraud" |
| 15 | Evaluation & Responsible AI | Backtest, anomaly F1, label agreement, benchmark, fairness probe, persona table | `/evaluation` | Ground-truth rows hatched and labelled evaluation-only |

### Financial Health scoring

The customer-facing health score is a **weighted composite of measured ratios**, never a
black box — a score shown next to a person's name has to be arguable.

| Component | Weight |
|---|---|
| Saving after spending | 0.20 |
| Spending against income | 0.20 |
| Money kept in reserve | 0.20 |
| Consistency of income | 0.15 |
| Progress toward savings goals | 0.15 |
| Spending paid in cash | 0.10 |

Each component is scored from ladders of measured ratios and carries its own `Evidence`.
The **ML layer sits on top as a calibration model** — it predicts the ground-truth
financial profile from behavioural features so the product can (a) estimate a profile
when history is thin and (b) state its own accuracy rather than implying certainty.

---

## Tech Stack

| Layer | Choice | Notes |
|---|---|---|
| Frontend | React 19, TypeScript 5.9, Vite 8, Tailwind CSS 4, Recharts 3 | Presentational only; no calculation in components |
| Backend | FastAPI, Pydantic v2, Uvicorn | Serves engines, models and assistant orchestration |
| Database | PostgreSQL 16 | Cohort store; replaced by a static snapshot in the frontend-only build |
| Data | pandas, NumPy, SciPy | Generation, feature engineering, validation |
| ML | scikit-learn, LightGBM | Forecast, anomaly detection, segmentation, explanation attribution |
| LLM | Gemini 2.5 Flash → Groq Llama 3.1 70B fallback | REST via `httpx`, read-only tools |
| Voice | Browser STT/TTS + env-pluggable server providers | Both paths degrade gracefully |
| Tests | pytest, FastAPI TestClient, unittest | 76 tests across dataset and service layers |

---

## Repository Layout

```
Upay-CoPilot/
├── frontend/                     React + TypeScript prototype (no backend needed)
│   ├── public/data/snapshot.json Static dataset snapshot (1.4 MB, columnar JSON)
│   └── src/
│       ├── engines/              16 in-browser deterministic engines
│       ├── pages/                16 routed pages, all code-split
│       ├── components/           Layout, Evidence panel, charts, UI primitives
│       ├── data/                 Snapshot loader, context builder, store
│       ├── i18n.ts               Bilingual UI dictionary
│       └── types.ts              Evidence, EngineResponse, Lang types
│
├── backend/                      FastAPI service + Python ML
│   ├── app/
│   │   ├── api/                  engines.py, engines_extra.py, assistant.py
│   │   ├── core/                 config, context, money, periods
│   │   ├── db/                   store.py (Embedded + Postgres), schema.sql
│   │   ├── engines/              10 deterministic engines (Python)
│   │   ├── llm/                  router, tools, guards, rag
│   │   ├── ml/                   forecast, anomaly, health, segmentation, artifacts
│   │   ├── schemas/              Pydantic response models
│   │   ├── voice/                STT/TTS routes
│   │   └── features/build.py     Feature matrix construction
│   ├── artifacts/                Trained model bundles + model cards
│   ├── reports/evaluation_report.json
│   ├── scripts/                  Training entrypoints
│   └── tests/test_copilot.py     17 service tests
│
├── ml/dataset/                   Synthetic cohort generator
│   ├── config.py                 Personas, probabilities, budgets, seed
│   ├── pipeline.py               generate_all() orchestration
│   ├── users.py transactions.py goals.py recurring.py profiles.py labels.py
│   ├── splits.py                 Strict temporal split + leakage blocklist
│   ├── leakage.py                Leakage detection & rendering
│   └── validation.py             Schema, ledger, vocabulary, relationship checks
│
├── scripts/
│   ├── generate_synthetic_data.py    Full 500-user population
│   ├── generate_dev_dataset.py       50-user development dataset
│   ├── validate_dataset.py           Schema + ledger validation report
│   ├── leakage_check.py              Target & temporal leakage gate
│   └── export_frontend_snapshot.py   Dataset → snapshot.json
│
├── data/
│   ├── schema/                   Column contracts (source of truth for validation)
│   ├── generated/                Full population: 500 users, ~191k transactions
│   ├── dev/                      Development dataset: 50 users, ~7.6k transactions
│   └── train|validation|test/    Temporal splits (features/ + labels/)
│
├── docs/                         Data dictionary, split rules, assumptions, report
├── tests/test_dataset.py         59 dataset invariant tests
└── product_spec.md               The contract the code is reviewed against
```

---

## Quick Start

### Prerequisites

- Python **3.10+**
- Node.js **20+** and npm

### 1. Frontend (self-contained — recommended first run)

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`. The app fetches `public/data/snapshot.json` and computes
everything client-side. **No backend, no API keys, no database.**

| Script | Purpose |
|---|---|
| `npm run dev` | Vite dev server on port 5173 |
| `npm run build` | Type-check (`tsc -b`) + production build |
| `npm run preview` | Serve the production build |
| `npm run lint` | ESLint |
| `npm run typecheck` | TypeScript only |

If the snapshot is missing, regenerate it:

```bash
python scripts/export_frontend_snapshot.py
```

### 2. Backend (FastAPI service)

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

pip install -r backend/requirements.txt

cp backend/.env.example backend/.env   # add provider keys if you want the LLM

cd backend
uvicorn app.main:app --reload --port 8000
```

- API root: `http://localhost:8000`
- Interactive docs: `http://localhost:8000/docs`
- Health check: `http://localhost:8000/health`

The service runs **fully without any LLM key**. With no provider configured the
assistant degrades to a deterministic keyword-routed answer rather than failing —
a product that stops working when a model is down is not a financial product.

### 3. Full data + model pipeline

```bash
# Development dataset: 50 users, ~7.6k transactions, ≤10k row budget
python scripts/generate_dev_dataset.py

# Full population: 500 users, ~191k transactions, 9 months
python scripts/generate_synthetic_data.py --users 500 --months 9 --seed 42

# Validation + leakage gates (both exit non-zero on failure)
python scripts/validate_dataset.py
python scripts/leakage_check.py

# Export the frontend snapshot
python scripts/export_frontend_snapshot.py

# Train and persist all models
cd backend && python scripts/train_splits_all.py
```

---

## Data Pipeline

The generator is **persona-driven and deterministic** (seed 42). Each persona encodes a
cohort design label — income shape, spend ratio, cash dependency, goal behaviour — and
the generator emits a ledger where `balance_after` reconciles exactly.

### Personas

| Persona | Share | Characteristic |
|---|---|---|
| `stable_saver` | 20% | Predictable income, low spend ratio, consistent funding |
| `end_month_shortage` | 15% | Spend concentrates in the last third of the month |
| `irregular_income` | 12% | High income coefficient of variation |
| `high_cash_dependency` | 12% | Majority of spend funded from cash-out |
| `goal_oriented` | 15% | Multiple funded goals, consistent contributions |
| `seasonal_spender` | 10% | Periodic large expenses |
| `financial_pressure` | 10% | High expense ratio, low buffer |
| `sudden_anomaly` | 6% | Injected anomalous transactions |

### Ledger semantics (identical in every implementation)

- `send_money` and `receive_money` are **internal transfers** — excluded from income and
  consumption so the ledger reconciles with the wallet.
- Only legs with a mapped economic category count as income or spend. Cash legs are
  wallet-to-wallet movements, never consumption.
- `asOf` is the **latest ledger date**, not the wall-clock date.

### Temporal splits — never random

| Split | Periods | Months | Transactions | Share |
|---|---|---|---|---|
| Train | 2026-01 … 2026-05 | 5 | 87,891 | 55.7% |
| Validation | 2026-06 … 2026-07 | 2 | 34,870 | 22.1% |
| Test | 2026-08 … 2026-09 | 2 | 35,021 | 22.2% |

Each split writes `features/` and `labels/` separately. Three classes of column are
blocked from features:

1. **Ground truth** — `persona`, `is_anomaly`, `pattern_type` and every generator knob.
2. **Label columns** — the six behaviour flags and `anomaly_count`.
3. **Whole-window aggregates** — `financial_profiles.csv` plus `current_amount`,
   `progress_ratio`, `is_achieved`, which aggregate the entire window including the test
   period.

`recurring_id` **is** kept: it is a real foreign key observable at transaction time.

### Reference counts

| Table | Generated (500 users) | Dev (50 users) |
|---|---|---|
| `users` | 500 | 50 |
| `wallets` | 1,468 | 147 |
| `transactions` | 191,167 | 7,609 |
| `income_events` | 6,939 | 724 |
| `recurring_expenses` | 1,399 | 149 |
| `financial_goals` | 542 | 53 |
| `goal_contributions` | 2,693 | 253 |
| `behavior_labels` | 4,500 | 450 |
| `injected_patterns` | 755 | 88 |

Full detail: [`docs/data_dictionary.md`](docs/data_dictionary.md),
[`docs/dataset_split.md`](docs/dataset_split.md),
[`docs/synthetic_data_assumptions.md`](docs/synthetic_data_assumptions.md),
[`docs/dataset_validation_report.md`](docs/dataset_validation_report.md).

---

## ML Models

Four trained models, each persisted as a joblib bundle **plus a model card** carrying its
training window, feature list, metrics and baselines. Every served number can quote which
model version produced it.

| Model | Algorithm | Task | Card |
|---|---|---|---|
| `forecast_spend_level` | LightGBM + volatility-gated stack | Predict next-period monthly spend level | `backend/artifacts/forecast_spend_level.card.json` |
| `forecast_income_level` | LightGBM + volatility-gated stack | Predict next-period monthly income level | `backend/artifacts/forecast_income_level.card.json` |
| `anomaly_detection` | Isolation Forest (unsupervised) | Rank unusual spending for review | `backend/artifacts/anomaly_detection.card.json` |
| `health` | LightGBM multi-target + TreeSHAP | Predict financial profile + behaviour flags | `backend/artifacts/health.card.json` |
| `segmentation` | K-Means on 30 standardised features | Unsupervised behavioural grouping | `backend/artifacts/segmentation.card.json` |

### Design decisions worth knowing

**Forecasting predicts levels, not days.** The first implementation forecast day-to-day
spend with a GBDT on lag features and **lost to the user's own trailing mean** against
baselines. That is a property of the data, not a bug: monthly spend is drawn as a budget
proportional to that month's income, so there is little day-to-day autocorrelation to
exploit. The module now predicts the *level* — the question customers actually ask — with
three competing estimators (structural trailing, LightGBM, and a **learned
volatility gate** between them). The gate earns the GBM weight only where a user's own
history is too noisy to trust. Day-level timing is then deterministic: bills land on
their contractual `due_day`, income on the observed payday, and discretionary spend is
spread by the user's own day-of-month profile.

**Anomaly detection is unsupervised.** Labels score the detector, never fit it, so the
same code path runs on production data where no labels exist. A known recurring
obligation is never reported as an anomaly — rent is not an anomaly.

**Segmentation is validated externally.** Silhouette and inertia are gameable by
increasing *k*, so the fit is also scored against two references the clustering never saw:
the generator's behaviour labels (ARI / NMI) and the temporal folds (ARI between
train-cut and validation-cut assignments). A segmentation that reshuffles when a month of
data arrives is a description of the sample, not of the customers.

**Fairness is enforced structurally.** Age group, occupation and location type are
**dropped from every design matrix**. They are retained only for display and the fairness
report, so a score cannot drift into a proxy for who the customer is rather than what
they do. There is no language or gender column in the cohort at all.

**Explainability is exact.** `predict(..., pred_contrib=True)` returns TreeSHAP values
computed by LightGBM's own C++ code — mathematically identical to `shap.TreeExplainer`
without requiring the `shap` package.

---

## API Reference

Base URL `/api`. All engine routes return pre-computed, evidenced values. `404` for an
unknown user, `400` for an invalid parameter.

### Context & metadata

| Method | Path | Description |
|---|---|---|
| `GET` | `/` | Service banner |
| `GET` | `/health` | Liveness probe |
| `GET` | `/api/users` | Cohort roster with count |
| `GET` | `/api/context/{user_id}` | Financial Context Engine summary |
| `GET` | `/api/models` | All model cards |
| `GET` | `/api/segments` | Population-level segments |
| `GET` | `/api/segments/{user_id}` | Segment assignment for one customer |

### Understanding

| Method | Path | Query params |
|---|---|---|
| `GET` | `/api/health/{user_id}` | — |
| `GET` | `/api/resilience/{user_id}` | — |
| `GET` | `/api/spending/{user_id}` | `period` |
| `GET` | `/api/spending/{user_id}/unusual` | `period` |
| `GET` | `/api/spending/{user_id}/recurring` | — |
| `GET` | `/api/spending/{user_id}/leaks` | `period`, `threshold=500.0` |
| `GET` | `/api/spending/{user_id}/late-month` | `months=3` |
| `GET` | `/api/cashout/{user_id}` | `months=3` |
| `GET` | `/api/bills/{user_id}` | `days_ahead=45` |

### Planning

| Method | Path | Query / body params |
|---|---|---|
| `GET` | `/api/forecast/{user_id}` | `horizon_days=30` |
| `GET` | `/api/goals/status/{user_id}` | — |
| `GET` | `/api/goals/plan/{user_id}` | `target`, `months`, `scenario=balanced` |
| `GET` | `/api/goals/conflicts/{user_id}` | — |
| `GET` | `/api/emergency/{user_id}` | — |
| `POST` | `/api/simulate` | `user_id` + scenario body |

### Literacy, credit & assistant

| Method | Path | Query / body params |
|---|---|---|
| `GET` | `/api/literacy/{user_id}` | `topic` |
| `GET` | `/api/credit/readiness/{user_id}` | — |
| `POST` | `/api/assistant` | `{ user_id, message }` |
| `POST` | `/api/intent` | `{ user_id, message }` — deterministic intent routing, no LLM |

### Voice (env-pluggable stubs)

| Method | Path | Body |
|---|---|---|
| `POST` | `/voice/transcribe` | Raw `audio/*` bytes |
| `POST` | `/voice/synthesize` | `{ text }` |

---

## LLM Layer

```
customer message
      ↓
sanitize_input()          redact PII + neutralise injection attempts
      ↓
is_on_topic()             scope gate — refuse off-topic before any tool runs
      ↓
retrieve() / render_context()   ground the answer in documented facts
      ↓
Gemini 2.5 Flash  ──fail──▶  Groq Llama 3.1 70B
      ↓
tool call → ALLOWED_TOOLS (8 tools, read-only)
      ↓
guard_output()            final filter before it reaches a customer
      ↓
answer + citations
```

### The allowlisted tool surface

Exactly eight tools, all read-only (`backend/app/llm/tools.py`):

`cashflow_forecast` · `financial_literacy` · `credit_readiness` · `goal_status` ·
`goal_plan` · `goal_conflicts` · `emergency_fund` · `simulate`

No writes. No SQL. No score mutation. No credit decisions.

### Guardrails (`backend/app/llm/guards.py`)

- **Prompt injection** — eight patterns (`ignore previous instructions`, `you are now`,
  `system:`, `act as a`, `pretend to be`, `jailbreak`, …). Injection spans are replaced
  with `[removed-instruction]` rather than dropping the whole message, because blocking
  a customer's goal named *"system savings"* is not acceptable.
- **PII redaction** — account numbers, BD phone numbers, long digit runs, emails and
  `sk-` secrets are replaced before text reaches a provider. The model never needs them;
  it works from already-aggregated engine output.
- **Output filtering** — banned phrases and leaked identifiers are stripped from model
  output before display.
- **Deterministic temperature** — `temperature=0.1`, `max_tokens=256`, JSON response mode.

---

## Frontend

The frontend is a **self-contained prototype**: it loads `public/data/snapshot.json`,
builds a per-customer `UserContext`, and runs all 16 engines in the browser. This is a
deliberate, documented scope decision — it proves the information architecture, the
evidence model and the language layer, makes every number reproducible from one command,
and keeps the "LLM never calculates" boundary provable by inspection.

| Concern | Implementation |
|---|---|
| Routing | `react-router-dom` 7, 16 routes, all pages lazy-loaded except the dashboard |
| Charts | Recharts 3, shared components in `components/charts.tsx` |
| Styling | Tailwind CSS 4 via `@tailwindcss/vite`, no CSS framework lock-in |
| State | React context store, memoised bundle per selected customer |
| i18n | Bilingual `{ en, bn }` field pairs authored in engines + `i18n.ts` dictionary |
| Evidence | `components/Evidence.tsx` — collapsible panel: metrics, reasons, assumptions, sources |
| Icons | `lucide-react` |

Because every engine is pure and deterministic, the whole bundle is memoised on the
context object — switching language or customer recomputes nothing.

---

## Database

The production relational shape lives in `backend/app/db/schema.sql`:

```bash
psql "$DATABASE_URL" -f backend/app/db/schema.sql
```

```sql
users · wallets · income_events · recurring_expenses · transactions
financial_goals · goal_contributions
user_daily_flow · user_monthly_flow          -- materialised features
behavior_labels · injected_patterns          -- ground truth, research side only
```

Plus three views that centralise the accounting rules so every consumer agrees:

| View | Purpose |
|---|---|
| `v_cash_wallets` | Wallets that have ever touched a `cash_in` |
| `v_consumption` | Transactions excluding transfers and cash legs |
| `v_daily_flow` | Per-user daily income/spend used by every forecast |

Two store implementations satisfy the same `FinancialStore` protocol:
**`EmbeddedStore`** (reads `data/dev` into a cached pandas store — zero setup, used by
the API and tests) and **`PostgresStore`** (the same rollups in SQL).

> `data/generated` is named in config **only so code can refuse to read it**. The
> development dataset is the source of truth.

---

## Testing

```bash
# Dataset invariants (59 tests)
pytest tests/test_dataset.py -v

# Service, guards and routes (17 tests)
cd backend && pytest tests/test_copilot.py -v

# Everything
cd backend && pytest -v
```

The dataset suite covers schema and foreign keys, ledger integrity, transfer pairing,
recurring schedules, goal arithmetic, label observability, determinism, temporal splits
and leakage — including a test that **injects a `persona` column and asserts the leakage
check catches it**.

The service suite asserts read routes return 200, unknown users return 404 (never 500),
goal allocation never exceeds disposable capacity, forecast horizons are respected and
not double-counted, credit readiness never touches protected attributes, injection is
neutralised, identifiers are redacted, RAG retrieves the right documented fact, and the
voice routes accept raw audio and reject empty bodies.

---

## Configuration

Copy `backend/.env.example` to `backend/.env`:

```bash
# Financial policy
MINIMUM_BALANCE_BUFFER=5000        # BDT floor for the liquidity buffer
BUFFER_FLOOR_MONTHS=1              # Minimum reserve in months of essential spend
EMERGENCY_FUND_MONTHS=3            # Emergency fund target formula
MONTHLY_RECURRING_CAP=0.40         # Recurring obligations as share of income

# Simulation
MONTE_CARLO_PATHS=2000
MONTE_CARLO_SEED=42

# LLM providers (REST via httpx — no SDK required)
GEMINI_API_KEY=                    # primary
GROQ_API_KEY=                      # fallback

# Voice (env-pluggable)
STT_PROVIDER=env
TTS_PROVIDER=env

# Storage
USE_POSTGRES=false
DATABASE_URL=
```

Financial policy values are **product assumptions**, versioned in
`backend/app/core/config.py` and quoted back to the customer as assumptions in the
evidence panel.

---

## Evaluation Results

From `backend/reports/evaluation_report.json`, trained on `data/dev/splits`
(train `2026-01..05`, validation `2026-06..07`, test `2026-08..09`).

| Area | Method | Result |
|---|---|---|
| Spend forecast | Rolling-origin backtest vs 30-day trailing baseline | **15.72% MAE improvement** |
| Income forecast | Same | **4.79% MAE improvement** |
| Anomaly detection | Isolation Forest vs `is_anomaly` ground truth | Precision 0.63 / Recall 0.28 / **F1 0.38** at 1.2% contamination |
| Segmentation | K-Means, k=4 chosen by silhouette | Silhouette 0.238, temporal ARI **0.857** |
| Numerics | Every engine figure re-derived independently | Exact-match enforced in tests |
| Fairness | Slices by age group, occupation, location type | Protected attributes excluded from all design matrices |

> **Honest caveat, reproduced from the report.** The dataset generator derives both
> `financial_profiles` and `behavior_labels` by aggregating the same transactions the
> features are built from. A model can therefore reach a high R²/F1 while learning
> nothing a rule could not, because it is re-deriving a statistic it was handed. The
> defensible claim is that the pipeline **reproduces ground truth reliably on unseen
> customers and unseen months** — not that it predicts future financial behaviour.
> Proving the latter requires held-out real-customer data.

The `/evaluation` page in the app exposes these backtests, the disagreement lists, the
fairness probe and the failure modes. Ground-truth rows are hatched and labelled
evaluation-only.

---

## Roadmap

| Phase | Deliverable | Status |
|---|---|---|
| 0 | Product spec, data dictionary, split rules, validation report | ✅ Complete |
| 1 | Synthetic cohort + validation | ✅ Complete |
| 2 | Financial Context Engine | ✅ Complete |
| 3 | Core engines (health, spending, forecast, goals, simulator) | ✅ Complete |
| 4 | Planning & safety (emergency, cash-out, sources, resilience, credit) | ✅ Complete |
| 5 | Literacy, assistant, monthly review, bills calendar | ✅ Complete |
| 6 | Evaluation and responsible-AI reporting | ✅ Complete |
| 7 | Bilingual + Banglish + voice | ✅ Complete |
| 8 | FastAPI service layer | ✅ Complete |
| 9 | Python ML training and serving (GBDT, clustering, TreeSHAP) | ✅ Complete |
| 10 | PostgreSQL, auth, deployment, user testing | ⬜ Not started |

**Open decisions**

1. **Segmentation** — ship a feature-derived behavioural segment (never the ground-truth
   persona) or omit segmentation from the customer-facing product.
2. **TTS provider** — keep browser speech synthesis for the prototype, or move STT/TTS
   server-side for consistent Bangla voice quality across devices.
3. **Model depth** — keep deterministic browser engines as shipped behaviour, or replace
   them with served Python models as the default path.

---

## Contributing

1. Read [`product_spec.md`](product_spec.md) first — it is the contract the code is
   reviewed against.
2. Any new user-facing number needs an `Evidence` record.
3. Any new model input must clear `scripts/leakage_check.py`.
4. `npm run build`, `npm run lint` and `pytest` all pass before a PR.

---

## Responsible AI

| Commitment | Implementation |
|---|---|
| No autonomous lending | Readiness page explicitly hypothetical; assistant refuses credit decisions |
| Transparency | Every figure carries inputs, method, confidence, assumptions |
| Explainability | Fixed weights and stated formulas, not opaque scores |
| Fairness | Observable cohort slices only; no protected attribute as an input |
| Privacy | Synthetic data only; no third-party calls; no persistence of financial advice |
| Human control | Every suggestion requires an explicit user action |
| Auditability | Evaluation page exposes backtests, disagreements and failure modes |
| Honest failure | "Not enough history in this cohort to answer that" is a valid, expected answer |
| No dark patterns | No urgency theatre, no shame framing, no streak pressure |

---

## License

This project is developed for the upay Financial Life Copilot challenge. All data is
synthetic. See repository history for authorship and contribution records.
