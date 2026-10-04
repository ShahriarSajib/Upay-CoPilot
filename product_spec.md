# upay Financial Life Copilot — Product Specification

**Status:** Phase 0 baseline. This document is the contract the code is reviewed against.
**Audience:** product, design, data science, backend, frontend, QA.
**Data:** 100% synthetic. No real upay customer data is used, stored, or required at any phase.

---

## 1. Mission

Give every upay customer a financial co-pilot that turns raw transaction history into
clear, evidence-backed guidance for **financial independence**: know where the money goes,
what the next month looks like, which goal to fund next, and what to do when plans break.

The product must be useful to a customer with no financial vocabulary, in their own
language, on a phone, without reading a single financial manual.

### Non-goals

- Not a bank. It never moves money, approves credit, or changes an autopay setting.
- Not an advisor giving regulated advice. It shows arithmetic; the customer decides.
- Not a chatbot with opinions. It answers only from computed results and a fixed
  service-information file.

---

## 2. Target user

| Persona (cohort design label) | Situation | What they need first |
|---|---|---|
| Gig worker | Irregular daily income, ride-hailing/freelance | Income-stability and low-balance warnings |
| Salary employee | Predictable income, tight month-end | Bills calendar and end-of-month shortage |
| Small business owner | Mixed personal/business flows | Source concentration and cash-out dependency |
| Micro-entrepreneur | Daily cash in, irregular large costs | Emergency buffer and income diversification |

These labels exist to design and evaluate the synthetic cohort. **They are ground truth.**
They are never model inputs and are never presented to the customer as an account trait.

---

## 3. Core architecture

```
Synthetic transactions
        ↓
Financial Context Engine        ← one immutable per-customer context, no page reads raw data
        ↓
Deterministic engines            ← health, spending, forecast, goals, simulator, emergency,
        ↓                          cash-out, sources, resilience, credit, literacy, bills
Financial Evidence              ← metrics, confidence, reasons, assumptions, sources
        ↓
Explanation layer                ← bilingual, Banglish-tolerant, voice in/out, refusal-first
        ↓
Customer action                  ← one prioritised action at a time, user-initiated
        ↓
Measurable outcome               ← evaluated against held-out labels
```

### Non-negotiable rules

1. **The LLM never calculates.** Every figure comes from a deterministic engine.
   The assistant may only rephrase, translate, summarise and refuse.
2. **No naked numbers.** Every user-facing figure carries evidence: the inputs, the
   method, the confidence and the assumptions.
3. **No autonomous decisions.** No score changes, no loan decisions, no transfers,
   no arbitrary SQL or shell, no persisted financial advice.
4. **No ground-truth leakage.** `persona`, `is_anomaly`, behaviour labels and the
   anomaly flag are evaluation-only.
5. **Refuse first.** Out-of-scope requests are rejected before any tool runs.

---

## 4. Feature modules

Each module lists the output it owns, the page that presents it, and the safety
constraint that applies.

| # | Module | Engine output | Page | Constraint |
|---|---|---|---|---|
| 1 | Financial Health Coach | 7-dimension weighted score, positives, concerns, low-balance days | `/health` | Weights are fixed product assumptions, never fitted per customer |
| 2 | Smart Spending | Unusual transactions, recurring detection, money leaks, essential/discretionary split, end-of-month concentration | `/spending` | Detections carry a stated rule, not a judgement |
| 3 | Cash-Flow Forecasting | Balance projection at 7/14/30/60/90 days, income schedule, obligation calendar, buffer breach | `/forecast` | Baseline comparison reported alongside every model figure |
| 4 | Bills & Obligations | Per-due-date schedule: balance before → bill → balance after, income coverage | `/bills` | Read-only; cannot pay or reschedule |
| 5 | Goal & Savings Planning | Feasibility per goal, surplus capacity, 3 allocation scenarios | `/goals` | Plans show shortfall honestly, never assume a raise |
| 6 | What-If Simulator | Shock scenarios: job loss, income drop, big expense | `/simulator` | Labelled hypothetical; never persisted as a prediction |
| 7 | Emergency Fund Planning | Target in months of essential spend, monthly contribution, gap | `/emergency-fund` | Target formula is explicit |
| 8 | Cash-Out Dependency | Net cash-out, liquidity need, dependency band | `/cash-out` | Descriptive, never moralising |
| 9 | Money Sources | Income-source stability, source concentration, wallet liquidity | `/money-sources` | `other_digital` excluded from liquid balance by design |
| 10 | Resilience | 7 resilience dimensions, shock absorption, weakest link | `/resilience` | States what would break the plan |
| 11 | Responsible Credit Readiness | Readiness bands, hypothetical affordability, obligation load | `/credit-readiness` | **Never a lending decision; no approval or rejection** |
| 12 | Financial Literacy | Signal-triggered lessons, quizzes, dormant topics | `/learning` | Teaches behaviour, not products |
| 13 | Ask upay (assistant) | Intent → tool trace → answer + citations | `/assistant` | Scope check first; refusals are first-class output |
| 14 | Monthly Review | Month summary, action centre, anomalies, categories | `/review` | Anomalies shown as "review this", never "fraud" |
| 15 | Evaluation & Responsible AI | Backtest, anomaly F1, label agreement, benchmark, fairness probe, persona table | `/evaluation` | Ground-truth rows are hatched and labelled evaluation-only |

### Language and voice

- English and Bangla throughout, including numbers and charts.
- Banglish input is normalised before matching (`Ei mashe amar koto taka khoroch hoise?`).
- Voice input via the browser speech-recognition API; voice output via the browser
  speech-synthesis API. Both degrade gracefully and both state when unsupported.
- Engine content is authored as bilingual field pairs so the language switch is one
  state change, not a page-by-page audit.

---

## 5. Evidence standard

Every user-facing number must be traceable to:

1. **Inputs** — which records, which date range, which filters.
2. **Method** — the formula or model in one sentence.
3. **Confidence** — 0–1 plus a plain-language reason for the level.
4. **Assumptions** — what was held constant and what was ignored.
5. **Sources** — the dataset files used.
6. **Rejection reasons** — when a metric cannot be trusted, say so.

A confidence level is a statement about data coverage and stability, never about
whether an answer is "good for you".

---

## 6. Data and evaluation

### Dataset

- Synthetic cohort with the file-level dictionary in `docs/data_dictionary.md` and the
  generation assumptions in `docs/synthetic_data_assumptions.md`.
- Split rules and label definitions in `docs/dataset_split.md`;
  validation output in `docs/dataset_validation_report.md`.

### Ledger semantics (must be implemented identically everywhere)

- `send_money` and `receive_money` are internal transfers: excluded from income and
  consumption so the ledger matches the wallet.
- Only transaction legs with a mapped economic category count as income or spend.
- `asOf` is the latest ledger date, not the wall-clock date.

### Evaluation targets

| Area | Method | Reported as |
|---|---|---|
| Forecasting | Rolling-origin backtest vs a 30-day-average baseline | MAE, RMSE, MAPE, improvement |
| Anomaly detection | Precision / recall / F1 against `is_anomaly` | F1 with support count |
| Behaviour labels | Agreement with generator behaviour labels | Agreement rate + disagreement list |
| Assistant | Labelled question set | Accuracy, refusal correctness, citation presence |
| Fairness | Cohort slices by occupation, age group, location type | Result spread; no protected attribute as a model input |
| Numerics | Every engine figure re-derived independently | Exact-match rate |

Fairness slices use only observable, non-protected cohort fields. The cohort carries no
language or gender column, and no engine may read one.

---

## 7. Technology

| Layer | Choice | Notes |
|---|---|---|
| Frontend | React + TypeScript + Vite, Tailwind CSS, Recharts | Presentational only; no calculation in components |
| Backend (target) | FastAPI + Python | Serves engines, models and assistant orchestration |
| Database (target) | PostgreSQL | Cohort store; replaced by a static snapshot in the frontend-only build |
| ML (target) | Gradient-boosted trees, clustering, SHAP | Forecast, segmentation, explanation attribution |
| LLM | Tool-calling explanation layer | Read-only tools; cannot mutate state |
| Voice | Speech-to-text + text-to-speech | Browser APIs in the frontend build |

### Frontend build boundary

The current frontend is a **self-contained prototype**: it loads
`frontend/public/data/snapshot.json`, runs every engine in the browser, and needs no
backend. This is a deliberate, documented scope decision, not an omission:

- Proves the full information architecture, evidence model and language layer.
- Makes every number reproducible from one command.
- Keeps the "LLM never calculates" boundary provable by inspection.

When the FastAPI layer lands, the engines move behind typed endpoints and the React
components keep their current contract.

---

## 8. UX principles

1. **One decision per screen.** Each page ends in a single recommended action.
2. **Explain before asking.** Numbers appear with their method, not after a click.
3. **Bilingual by construction,** never a translated afterthought.
4. **Mobile-first,** readable on a 360 px screen, dense enough for desktop review.
5. **Honest failure.** "Not enough history in this cohort to answer that" is a valid,
   expected answer.
6. **No dark patterns.** No urgency theatre, no shame framing, no streak pressure.

---

## 9. Responsible-AI commitments

| Commitment | Implementation |
|---|---|
| No autonomous lending | Readiness page is explicitly hypothetical; assistant refuses credit decisions |
| Transparency | Every figure carries evidence, method, confidence, assumptions |
| Explainability | Fixed weights and stated formulas, not opaque scores |
| Fairness | Observable cohort slices only; no protected attribute as input |
| Privacy | Synthetic data only; no third-party calls; no persistence of financial advice |
| Human control | Every suggestion requires an explicit user action |
| Auditability | Evaluation page exposes backtests, disagreements and failure modes |

---

## 10. Delivery phases

| Phase | Deliverable | Status |
|---|---|---|
| 0 | `product_spec.md`, data dictionary, split rules, validation report | Complete |
| 1 | Synthetic cohort + validation | Complete |
| 2 | Financial Context Engine | Complete |
| 3 | Core engines (health, spending, forecast, goals, simulator) | Complete |
| 4 | Planning and safety modules (emergency, cash-out, sources, resilience, credit) | Complete |
| 5 | Literacy, assistant, monthly review, bills calendar | Complete |
| 6 | Evaluation and responsible-AI reporting | Complete |
| 7 | Bilingual + Banglish + voice | Complete |
| 8 | FastAPI service layer | Not started |
| 9 | Python ML training and serving (GBDT, clustering, SHAP) | Not started |
| 10 | PostgreSQL, auth, deployment, user testing | Not started |

---

## 11. Acceptance criteria for the frontend

- [x] `npm run build` passes with no type errors.
- [x] `npm run lint` passes with no errors.
- [x] All pages bilingual, with a working Bangla-numeral toggle.
- [x] Every user-facing figure reachable from an evidence panel.
- [x] No ground-truth field used as a model input or shown as a product attribute.
- [x] Assistant refuses out-of-scope requests before running any tool.
- [x] Credit-readiness page states it is not a lending decision.
- [x] Forecast reports a baseline comparison and a backtest.
- [ ] Browser-level interaction, accessibility and responsive test pass (no automated
      browser test in the repository yet).
- [ ] Assistant evaluation set extended beyond the current 42 labelled questions.

---

## 12. Open decisions

1. **Segmentation:** ship a feature-derived behavioural segment (never the ground-truth
   persona) or omit segmentation from the customer-facing product.
2. **TTS provider:** keep browser speech synthesis for the prototype, or move STT/TTS
   server-side for consistent Bangla voice quality across devices.
3. **Model depth:** keep deterministic browser engines as the shipped behaviour, or
   replace them with served Python models once Phase 8 starts.