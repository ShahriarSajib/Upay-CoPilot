# upay Financial Life Copilot

AI-powered bilingual financial independence assistant for upay customers.

## Core capabilities

- Financial Health Coach
- Smart Spending Intelligence
- Cash-Flow Forecasting
- Goal & Savings Planning
- What-If Financial Simulation
- Emergency Fund Planning
- Cash-Out Dependency Analysis
- Financial Literacy Personalization
- Responsible Credit Readiness
- Bangla / English / Banglish Assistant
- Voice Financial Assistant

## Architecture

```
Synthetic Data          -> data/generated, data/{train,validation,test}
    ↓
Feature & Context Layer -> ml/dataset
    ↓
ML / AI Engines         -> not implemented yet
    ↓
Financial Evidence
    ↓
LLM Explanation
    ↓
Customer Action
    ↓
Measurable Outcome
```

## Project layout

```
backend/app/          FastAPI service (main.py, config.py)
ml/dataset/           Synthetic data generator, validator, leakage checks, splits
scripts/              CLI entry points for the data pipeline
tests/                unittest suite covering the generator and validators
data/schema/          Column contract for every generated table
data/generated/       Full generated dataset
data/{train,validation,test}/  Leak-safe temporal splits (features/ + labels/)
docs/                 Data dictionary, assumptions, split and validation reports
```

## Requirements

- Python 3.10 or newer
- [`uv`](https://docs.astral.sh/uv/) is recommended for environment setup, but
  `pip` inside a virtualenv works too.
- Node.js is **not** required. `package.json` only holds repository metadata and
  convenience scripts that shell out to the Python commands below.

## Quick start

```bash
# 1. Create the environment and install dependencies
uv venv .venv
uv pip install --python .venv/bin/python -r requirements-dev.txt
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 2. Configure (optional, sensible defaults are already committed)
cp .env.example .env

# 3. Generate the synthetic dataset and its temporal splits
python scripts/generate_synthetic_data.py

# 4. Validate the dataset, then confirm the splits are leak-safe
python scripts/validate_dataset.py
python scripts/leakage_check.py

# 5. Run the API
python -m backend.app.main
```

<details>
<summary>Prefer stdlib venv / pip?</summary>

```bash
sudo apt install python3-venv      # required once on Debian/Ubuntu
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
```

If `python3 -m venv` reports that `ensurepip` is unavailable, install
`python3-venv` (or `python3.14-venv`) first, or just use `uv` as above.

</details>

The API then serves:

| URL                           | Purpose                  |
| ----------------------------- | ------------------------ |
| http://127.0.0.1:8000/        | Service banner           |
| http://127.0.0.1:8000/health  | Liveness probe           |
| http://127.0.0.1:8000/docs    | Interactive OpenAPI docs |

Host and port come from `API_HOST` / `API_PORT` in `.env`. In `APP_ENV=development`
the server starts with auto-reload.

## Running the tests

```bash
python -m pytest                            # via pytest
python -m unittest discover -s tests -v     # via stdlib unittest
```

## Useful variations

```bash
python scripts/generate_synthetic_data.py --users 100 --months 6 --seed 7
python scripts/validate_dataset.py --data-dir data/generated --schema-dir data/schema
python scripts/leakage_check.py --split-root data
```

## Backend

FastAPI + Python.

## Frontend

Not implemented yet. The API ships CORS headers for a Vite dev server on
`localhost:5173` so a React + TypeScript client can be wired up next.

## Database

Not implemented yet. The generated CSVs are the current source of truth.