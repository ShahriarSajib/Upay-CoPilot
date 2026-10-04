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

Synthetic Data
    ↓
Feature & Context Layer
    ↓
ML / AI Engines
    ↓
Financial Evidence
    ↓
LLM Explanation
    ↓
Customer Action
    ↓
Measurable Outcome

## Backend

FastAPI + Python

## Frontend

React + TypeScript

## Database

PostgreSQL

## Run the connected application

1. Copy `backend/.env.example` to `backend/.env` and set the PostgreSQL
   connection and `AUTH_SECRET` values. The checked-in generated dataset is
   the single source of truth.
2. Apply the schema and seed the exact contents of `data/generated/`:

   ```powershell
   $env:PYTHONPATH="backend"
   python backend/scripts/load_postgres.py
   ```

3. Start the API:

   ```powershell
   uvicorn app.main:app --app-dir backend --reload
   ```

4. Start the frontend in another terminal:

   ```powershell
   cd frontend
   npm ci
   npm run dev
   ```

The frontend authenticates through `/auth/signup`, `/auth/login`, and
`/auth/logout`, then loads the authenticated dataset from `/api/dataset`.
Signup accepts an optional generated `user_id` such as `U00001`, allowing the
50 generated users to be tested independently without creating replacement
mock data.