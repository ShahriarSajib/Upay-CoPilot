# upay Financial Life Copilot

> **An explainable, bilingual financial independence assistant for everyday
> money decisions.**

upay Financial Life Copilot transforms transaction history into practical,
evidence-backed guidance. It helps customers understand their financial
health, anticipate cash-flow pressure, plan goals, prepare for emergencies,
and build better financial habits.

The project is implemented as a complete application rather than a static
prototype:

```text
React + TypeScript
        │
        │ authenticated REST API
        ▼
FastAPI + financial engines + ML/RAG tools
        │
        ▼
PostgreSQL
        │
        ▼
data/generated/ — canonical synthetic dataset
```

## Why this project matters

Most financial dashboards show what happened. The Copilot explains what it
means and what the customer can do next.

It answers questions such as:

- **Will I run short before my next income event?**
- **How much can I safely save this month?**
- **Which spending patterns are putting pressure on my balance?**
- **How large should my emergency buffer be?**
- **Which goal should I prioritize?**
- **What financial skill should I learn next?**

The result is a customer-centered financial guidance layer designed for
responsible, understandable, and measurable decisions.

## Product capabilities

### Understand

- Financial health score with explainable dimensions
- Spending summaries and category analysis
- Unusual spending and anomaly detection
- Recurring expense and bill tracking
- Cash-out dependency analysis
- Income and liquidity context

### Predict

- Daily cash-flow forecasting
- Income and spending pattern analysis
- End-of-month shortage detection
- Financial resilience scoring
- Behavioral segmentation

### Plan

- Goal progress and contribution planning
- Goal conflict detection
- Emergency-fund recommendations
- What-if savings and spending simulations
- Responsible credit-readiness guidance

### Learn and act

- Personalized financial-literacy recommendations
- English and Bangla interface support
- Bangla numeral display option
- Evidence trails for every major recommendation
- Grounded assistant with allowlisted financial tools
- Voice routes for transcription/text-to-speech integrations

## Key design principles

### One source of truth

The application uses the exact records in `data/generated/`. The same
generated CSV files are used to seed PostgreSQL, and the backend serves the
authenticated dataset to the frontend. The frontend does not create a
separate mock dataset.

### Explainable recommendations

Financial results include metrics, reasons, assumptions, confidence, and
source information. The assistant routes questions to deterministic financial
tools instead of inventing unsupported figures.

### Safe financial guidance

The assistant includes prompt-injection detection, sensitive-identifier
redaction, topic guardrails, and a responsible credit disclaimer. Credit
readiness is a guidance measure, not an official credit score.

### User-specific access

Signup, login, logout, bearer-token sessions, password hashing, protected
dataset access, and session revocation are implemented through the backend.
Generated users such as `U00001` can be selected during signup for independent
testing.

## Technology stack

| Layer | Technology |
| --- | --- |
| Frontend | React 19, TypeScript, Vite, React Router, Recharts, Tailwind CSS |
| Backend | Python 3.10+, FastAPI, Pydantic, pandas, NumPy, SciPy |
| Machine learning | scikit-learn, LightGBM, forecast/anomaly/health/segmentation modules |
| Assistant | REST-based LLM providers, RAG retrieval, allowlisted tools |
| Database | PostgreSQL with relational schema and foreign keys |
| Authentication | PBKDF2 password hashing, HMAC bearer tokens, PostgreSQL sessions |
| Testing | pytest, FastAPI TestClient, TypeScript build, ESLint |

## Repository structure

```text
.
├── backend/
│   ├── app/
│   │   ├── api/              # FastAPI routes, auth, assistant, engines
│   │   ├── core/             # settings, context, periods, money
│   │   ├── db/               # schema, embedded store, PostgreSQL store
│   │   ├── engines/          # financial calculations and recommendations
│   │   ├── llm/              # guards, RAG, router, tools
│   │   ├── ml/               # forecast, anomaly, health, segmentation
│   │   └── voice/            # voice integration routes
│   ├── scripts/
│   │   └── load_postgres.py  # schema application and generated-data seeding
│   └── tests/
├── frontend/
│   └── src/
│       ├── components/       # layout, charts, evidence, shared UI
│       ├── data/             # authenticated API dataset and state
│       ├── engines/           # frontend presentation engines
│       └── pages/             # product pages
├── data/
│   └── generated/             # canonical 50-user synthetic dataset
├── ml/                        # dataset-generation pipeline
├── scripts/                   # generation and frontend export utilities
└── docs/                      # data dictionary and validation documentation
```

## Quick start

### Prerequisites

- Python 3.10 or newer
- Node.js and npm
- PostgreSQL 14 or newer
- A PostgreSQL database URL

### 1. Configure the backend

Copy the example configuration and set values for your environment:

```powershell
Copy-Item backend\.env.example backend\.env
```

At minimum, configure:

```dotenv
USE_POSTGRES=true
DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/DATABASE
AUTH_SECRET=use-a-long-random-secret
```

Set `ALLOWED_ORIGINS` to the frontend origin when it is not running on the
default Vite URL.

Never commit API keys, database passwords, or production secrets.

### 2. Install backend dependencies

Using the project virtual environment:

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

### 3. Generate the canonical dataset

The repository is designed around a 50-user generated population:

```powershell
.\.venv\Scripts\python.exe scripts\generate_synthetic_data.py `
  --users 50 `
  --output-dir data\generated
```

The generator produces users, wallets, income events, transactions, goals,
contributions, profiles, labels, and injected patterns.

### 4. Create and seed PostgreSQL

This applies the relational schema and loads the exact contents of
`data/generated/`:

```powershell
$env:PYTHONPATH="backend"
.\.venv\Scripts\python.exe backend\scripts\load_postgres.py
```

### 5. Start the backend

```powershell
$env:PYTHONPATH="backend"
.\.venv\Scripts\python.exe -m uvicorn app.main:app `
  --app-dir backend `
  --reload
```

The API is available at `http://127.0.0.1:8000`.

Useful checks:

```text
GET  /health
GET  /
```

### 6. Start the frontend

In a second terminal:

```powershell
cd frontend
npm ci
npm run dev
```

The frontend is available at the Vite URL shown in the terminal, normally
`http://localhost:5173`.

If the backend is hosted somewhere else, set:

```dotenv
VITE_API_URL=http://127.0.0.1:8000
```

## Authentication flow

The application follows this flow:

```text
Signup/Login
    │
    ▼
Signed bearer token
    │
    ▼
Protected /api/dataset request
    │
    ▼
User-specific frontend context
    │
    ▼
Financial pages and assistant tools
    │
    ▼
Logout → session revoked
```

Available authentication endpoints:

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `POST` | `/auth/signup` | Create an account and issue a session |
| `POST` | `/auth/login` | Verify credentials and issue a session |
| `POST` | `/auth/logout` | Revoke the current session |
| `GET` | `/auth/me` | Validate the current bearer token |
| `GET` | `/api/dataset` | Return the authenticated application dataset |

Signup accepts an optional generated user ID:

```json
{
  "email": "customer@example.com",
  "password": "secure-password",
  "user_id": "U00001"
}
```

## API surface

The backend exposes endpoints for:

```text
/api/health/{user_id}
/api/spending/{user_id}
/api/spending/{user_id}/unusual
/api/spending/{user_id}/recurring
/api/spending/{user_id}/leaks
/api/spending/{user_id}/late-month
/api/forecast/{user_id}
/api/bills/{user_id}
/api/goals/status/{user_id}
/api/goals/plan/{user_id}
/api/goals/conflicts/{user_id}
/api/emergency/{user_id}
/api/cashout/{user_id}
/api/resilience/{user_id}
/api/credit/readiness/{user_id}
/api/literacy/{user_id}
/api/segments
/api/segments/{user_id}
/api/context/{user_id}
/api/assistant
/api/intent
/api/simulate
/voice/transcribe
/voice/synthesize
```

## Database model

The PostgreSQL schema defines the following core relationships:

```text
users
 ├── wallets
 ├── income_events
 ├── transactions
 ├── recurring_expenses
 ├── financial_goals
 │    └── goal_contributions
 ├── financial_profiles
 ├── behavior_labels
 └── injected_patterns
```

Transactions retain wallet, category, channel, direction, balance, anomaly,
fee, and related-record information. Transfer and cash-leg accounting rules
are shared by the embedded and PostgreSQL stores so financial calculations
remain consistent across environments.

## Testing and validation

### Backend tests

```powershell
cd backend
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD="1"
..\.venv\Scripts\python.exe -m pytest tests\test_copilot.py -q
```

From the repository root, use:

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests\test_copilot.py -q
```

The test suite covers:

- API health and route availability
- Unknown-user handling
- Forecast horizon behavior
- Goal-capacity constraints
- Simulation arithmetic
- Literacy and credit-readiness contracts
- Prompt-injection and identifier redaction guards
- RAG retrieval
- Intent routing
- Voice request validation

### Frontend checks

```powershell
cd frontend
npm run typecheck
npm run build
npm run lint
```

The lint configuration may report existing Fast Refresh export warnings; these
do not prevent the build.

## Demonstration flow

For a complete product demonstration:

1. Open the frontend.
2. Create an account using a generated user such as `U00001`.
3. Confirm that the dashboard loads authenticated data.
4. Switch between generated users.
5. Open Financial Health, Spending, Forecast, Bills, Goals, Emergency Fund,
   Cash-Out, Credit Readiness, Literacy, and Monthly Review.
6. Run a what-if simulation.
7. Ask the assistant about a cash shortage, goal, emergency fund, or credit
   readiness.
8. Change language between English and Bangla.
9. Log out.
10. Log in again and confirm the protected session flow.

## Responsible-use note

This project is an educational and decision-support prototype. It does not
replace regulated financial advice, a bank's official balance, or an official
credit score. Production deployment would require additional controls such as
formal identity verification, privacy governance, audit logging, key
management, rate limiting, monitoring, and regulatory review.

## License and project status

This repository is an academic/prototype implementation of an AI-powered
financial independence assistant. Refer to the repository's project
requirements and accompanying documentation for dataset assumptions,
validation details, and model-evaluation context.
