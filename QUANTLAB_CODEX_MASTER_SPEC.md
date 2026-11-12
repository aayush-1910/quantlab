# QUANTLAB — Codex Master Project Specification

> **Document type:** Product, architecture, engineering, research-methodology and implementation specification  
> **Project:** QUANTLAB  
> **Version:** 1.0  
> **Prepared:** 11 November 2026  
> **Target market:** Indian listed equities, initially NSE cash equities  
> **Ambition:** Extreme engineering ambition; institutional-style research discipline  
> **Execution model:** Research and paper trading first; broker-connected trade proposals with explicit human approval later

---

## 0. Instructions to Codex — read this first

This document is the source of truth for the QUANTLAB project. Before changing or generating code:

1. Inspect the existing repository, its current implementation, dependency files, tests and Git status. Do not assume the repository is empty.
2. Read this specification fully and summarize the relevant requirements before implementing a milestone.
3. Work incrementally. Implement one coherent vertical slice at a time. Do not attempt to scaffold the entire platform in one response or one giant commit.
4. Preserve working functionality. Do not replace functioning code merely because a different design is preferred.
5. Never fabricate market data, backtest results, broker responses, regulatory requirements or benchmark performance. Clearly label synthetic fixtures as synthetic and keep them out of performance claims.
6. Treat financial correctness, data provenance, reproducibility, security and test coverage as core features—not optional polish.
7. Do not enable live order placement unless the user explicitly requests that milestone and the broker, exchange, regulatory and security prerequisites have been verified. Default to research-only or paper-trading mode.
8. Never place real trades, use real brokerage credentials, or make external financial transactions during development or tests.
9. Never commit secrets, API tokens, licensed market data, account identifiers or personal financial information.
10. If a requirement is ambiguous, choose the safest reversible implementation, document the assumption, and ask only when the ambiguity blocks safe progress.

### Required implementation loop

For every task:

1. State the intended change and the relevant acceptance criteria from this document.
2. Inspect the smallest relevant part of the codebase.
3. Propose a short implementation plan.
4. Implement the minimum complete slice.
5. Add or update unit, integration and regression tests as appropriate.
6. Run formatting, linting, type checks and tests that are available.
7. Report files changed, commands run, results, known limitations and the next recommended task.
8. Update relevant documentation and architecture decision records (ADRs).

Do not claim a test passed unless it was actually run. If an external dependency, API key or paid dataset is unavailable, create a clearly labelled adapter boundary or fixture; do not pretend the integration works.

---

# 1. Product definition

## 1.1 What QUANTLAB is

QUANTLAB is an AI-assisted quantitative research and investment decision-support platform for Indian equity markets. It enables a researcher to move from a financial hypothesis to a reproducible experiment, evaluate the robustness of strategies and models, construct and stress-test portfolios, monitor paper positions, and—only after separate compliance and safety gates are satisfied—prepare broker-connected trade proposals for explicit human approval.

The product combines three forms of intelligence:

- **Quantitative intelligence:** deterministic calculations, statistical tests, portfolio mathematics and a reproducible backtesting engine.
- **Machine-learning intelligence:** feature engineering, supervised learning, ranking, volatility modelling and market-regime classification.
- **AI research assistance:** natural-language hypothesis interpretation, controlled tool orchestration, experiment planning and evidence-grounded report writing.

The AI layer assists research. It does not replace the deterministic financial engine, authoritatively certify a strategy, or independently authorize a trade.

## 1.2 Product mission

Build a research system that helps answer:

> Is this financial hypothesis supported by point-in-time data, realistic assumptions, statistically defensible tests and genuinely out-of-sample evidence?

QUANTLAB should make it easier to discover useful ideas and harder to fool oneself with data leakage, survivorship bias, overfitting, unrealistic execution assumptions or cherry-picked results.

## 1.3 Initial market scope

**Initial scope:** Indian cash equities, with NSE as the primary exchange and BSE support considered after the core data and instrument model is stable.

Initial research universe:

- NIFTY 50, NIFTY 100, NIFTY 200 and NIFTY 500 constituents where point-in-time membership data is available.
- Other NSE-listed cash-equity instruments where data licensing and quality permit.
- Selected sectoral indices and liquid ETFs where appropriate.

The platform must store instrument identity independently from the display symbol. Symbols, names, exchange identifiers and instrument tokens can change. Use stable internal instrument IDs and effective-dated mappings.

**Explicitly out of initial scope:** options pricing and execution, futures strategy execution, commodity markets, FX, crypto, high-frequency market making, tick-level execution research and multi-user commercial distribution. These may be future modules, not first-release requirements.

## 1.4 Execution scope

Build capabilities in this order:

1. Historical research and backtesting.
2. Paper trading using simulated orders and fills.
3. Broker connection in read-only mode (quotes, holdings, positions and order status, subject to provider permissions).
4. Human-approved order proposals.
5. Broker order submission only after a separate explicit go-live milestone, current compliance review, broker confirmation, security review and operational sign-off.

No autonomous live trading in v1.0. No AI-generated order may be sent directly to a broker.

## 1.5 Non-goals and claims to avoid

QUANTLAB must not:

- Promise returns, profitability, alpha or predictive accuracy.
- Present historical backtest performance as evidence of future results.
- Treat an LLM explanation as proof of a financial claim.
- Allow the AI agent to alter an experiment after seeing results without creating a new, separately versioned experiment.
- Use current index constituents as a substitute for historical constituents in historical tests.
- Assume every stock can be shorted, traded at the close, filled completely or traded without market impact.
- Scrape websites or use data in ways that violate provider terms, exchange terms or data licences.
- Enable live trading merely because a broker API technically accepts an order.

---

# 2. Product modules

## 2.1 Market Data Engine

Responsibilities:

- Instrument master and effective-dated symbol mappings.
- Daily OHLCV ingestion as the first supported data frequency.
- Index levels and historical index constituents where licensed and available.
- Corporate actions: splits, bonuses, dividends, rights and other relevant events.
- Fundamental observations and publication/availability timestamps when a licensed source exists.
- Trading calendar and exchange sessions.
- Data validation, provenance, versioning, quarantine and correction handling.
- Dataset manifests, checksums and reproducible snapshots.

Initial acceptance criteria:

- Ingest a licensed or user-supplied daily OHLCV dataset through a provider adapter.
- Validate required fields, data types, timestamp alignment, duplicates, impossible OHLC relationships and negative/invalid volume.
- Record source, retrieval time, source dataset/version, schema version and checksum.
- Preserve raw input immutably; write normalized data to a separate canonical layer.
- Make bad records visible in a quarantine report rather than silently dropping them.

## 2.2 Market Explorer and Screener

Responsibilities:

- Instrument search and watchlists.
- Daily price/volume charts.
- Benchmark and sector comparisons.
- Technical indicator overlays.
- Filterable stock screener.
- Data freshness and missing-history indicators.

The UI must display data source and as-of timestamp. Do not label delayed or end-of-day data as real-time.

## 2.3 Quantitative Strategy Laboratory

Responsibilities:

- Versioned strategy definitions.
- Configurable universe, entry/exit conditions, rebalance frequency and position sizing.
- Deterministic backtesting.
- Execution, slippage, liquidity and transaction-cost models.
- Benchmark comparison and performance analytics.
- Experiment comparison and reproducibility.

Initial strategy families:

1. Moving-average trend following.
2. RSI or other indicator-based mean reversion.
3. Cross-sectional momentum ranking.
4. Price/volume breakout.
5. Volatility targeting.
6. Pairs trading only after the basic engine supports synchronized series, borrow assumptions and robust statistical tests.
7. Factor investing only after point-in-time fundamental data is available.

Do not claim that a strategy is validated simply because it completes a backtest.

## 2.4 Machine Learning Research Platform

Initial research tasks:

- Cross-sectional ranking or classification of future relative returns.
- Market-regime classification.
- Volatility forecasting.
- Risk forecasting and exposure diagnostics.

Candidate model progression:

1. Naive and linear baselines.
2. Logistic/linear regression.
3. Random Forest.
4. XGBoost or LightGBM.
5. Time-series models such as GARCH where appropriate.
6. Neural networks (LSTM/GRU and transformer architectures) only after simpler baselines, data quality and evaluation are established.

Every model must have a target definition, prediction timestamp, feature availability rules, training window, validation method, holdout window, code version, dataset version, model parameters and metrics.

## 2.5 Portfolio and Risk Engine

Responsibilities:

- Equal-weight and benchmark-weighted portfolio baselines.
- Minimum variance, mean-variance and risk-parity experiments.
- Portfolio constraints and rebalancing.
- Exposure, concentration and liquidity analysis.
- Volatility, beta, drawdown, historical VaR and Expected Shortfall.
- Scenario analysis and stress testing.

Optimization output is a research proposal, not a guaranteed optimal investment decision. Show assumptions, constraints, input window and sensitivity.

## 2.6 AI Research Analyst

The AI agent should accept a natural-language research question, convert it into a structured experiment specification, identify data requirements, invoke approved deterministic tools, interpret returned results and generate an evidence-grounded report.

The agent must not perform financial calculations by mental arithmetic or invent results. The backtesting, statistics and portfolio services are the source of truth.

Initial agent tools:

```text
list_datasets()
inspect_dataset(dataset_id)
get_universe(universe_id, as_of_date)
list_features()
inspect_feature(feature_id)
create_hypothesis(specification)
create_experiment(specification)
run_experiment(experiment_id)
get_experiment_results(run_id)
compare_experiments(run_ids)
calculate_portfolio_risk(portfolio_id, as_of_date)
generate_report(run_id)
```

Tools must have explicit input/output schemas, permissions, timeouts, resource limits and audit logs. The agent should not have unrestricted production SQL, filesystem access, shell access or arbitrary access to broker APIs.

### AI research workflow

1. Parse the question and identify ambiguities.
2. Produce a structured hypothesis and target definition.
3. Check whether suitable point-in-time data exists.
4. Propose the universe, feature definitions, benchmark, horizon, costs and validation plan.
5. Require user approval of the experiment specification before expensive execution.
6. Execute through the deterministic research runner.
7. Retrieve actual metrics and diagnostics.
8. Generate a report with evidence references, caveats and reproducibility metadata.
9. Save prompts, model/provider metadata, tool calls, experiment IDs and report version.

If an experiment specification is revised after results are visible, create a new experiment version and preserve the original. Never silently overwrite the original hypothesis.

## 2.7 Paper Trading and Execution Gateway

Responsibilities:

- Simulated order lifecycle and fill model.
- Broker adapter interface.
- Read-only broker connectivity before order placement.
- Trade proposal creation.
- Human approval workflow.
- Pre-trade risk checks.
- Idempotent order submission and broker reconciliation, if/when enabled.
- Immutable audit records.

A proposal must be bound to an exact, immutable payload: account, instrument, exchange, side, quantity, order type, limit/trigger price, product type, validity, risk checks, market-data timestamp and expiry. Any material change invalidates approval and requires re-approval.

---

# 3. Architecture and technology decisions

## 3.1 Architecture principle

Use a **modular monolith with isolated background workers** first. Keep strong module boundaries and explicit interfaces. Do not introduce microservices until there is a measurable scaling, deployment, reliability or security reason.

The frontend, API and workers may be deployed separately, but they should share versioned contracts and a common Python domain package where appropriate.

## 3.2 Proposed stack

| Layer | Preferred technology | Notes |
|---|---|---|
| Web application | Next.js + TypeScript | App Router; server-side secrets only |
| UI | Tailwind CSS + shadcn/ui | Accessible, consistent components |
| Charting | TradingView Lightweight Charts or equivalent | Verify licence and usage terms |
| API | Python + FastAPI | Typed request/response schemas |
| Python packaging | `uv` + `pyproject.toml` | Lock dependencies |
| Data processing | Polars, NumPy, Pandas | Benchmark before optimizing |
| Statistics | SciPy, statsmodels | Use tested implementations where suitable |
| ML | scikit-learn, XGBoost/LightGBM, PyTorch | Add only when needed |
| Database | PostgreSQL | Metadata, transactions and relational data |
| Historical storage | Parquet | Partitioned, versioned datasets |
| Cache/queue broker | Redis | Cache and background task coordination |
| Background jobs | Celery initially | Keep jobs idempotent and observable |
| Experiment tracking | MLflow | Track parameters, artifacts and metrics |
| Containers | Docker / Docker Compose | Local reproducibility |
| Frontend package manager | pnpm | Lockfile committed |
| Tests | pytest, Vitest/Playwright as needed | Unit, integration and end-to-end |
| Observability | Structured logs + metrics | Add OpenTelemetry when useful |

TimescaleDB, object storage, DVC, Kubernetes and a dedicated feature store are optional future choices. Do not add them without a concrete requirement.

## 3.3 Logical architecture

```mermaid
flowchart TB
    USER[Researcher / Trader] --> WEB[Next.js Web App]
    WEB --> API[FastAPI Application]
    API --> AUTH[Authentication / Authorization]
    API --> APP[Application Services]

    APP --> DATA[Market Data Module]
    APP --> QUANT[Quant Research Module]
    APP --> ML[ML Module]
    APP --> RISK[Portfolio / Risk Module]
    APP --> AGENT[AI Research Orchestrator]
    APP --> EXEC[Execution Gateway]

    DATA --> PROVIDERS[Licensed Data Provider Adapters]
    DATA --> PG[(PostgreSQL)]
    DATA --> LAKE[(Parquet Data Lake)]
    APP --> REDIS[(Redis)]
    APP --> QUEUE[Background Workers]

    QUANT --> BACKTEST[Deterministic Backtest Engine]
    ML --> TRACK[MLflow]
    AGENT --> TOOLS[Allowlisted Tool Registry]
    TOOLS --> BACKTEST
    TOOLS --> RISK

    EXEC --> APPROVAL[Human Approval Gate]
    APPROVAL --> BROKER[Broker Adapter]
    BROKER --> EXCHANGE[Broker / Exchange API]
```

## 3.4 Module boundary rules

- The backtesting engine must not depend on the AI agent.
- Core financial calculations must be deterministic and testable without a web server or LLM.
- The AI agent calls application services through typed tools; it must not import internal database models and mutate them directly.
- Broker connectivity must exist only behind the execution gateway and broker adapter interface.
- Frontend code must never contain API secrets or broker access tokens.
- Background jobs must be idempotent where possible and must record state transitions.
- Shared domain types belong in a small common package; avoid creating a large dumping-ground `utils` module.

---

# 4. Repository structure

Use a monorepo. Create directories when their milestone begins; do not generate hundreds of empty files upfront.

```text
quantlab/
├── apps/
│   ├── web/                       # Next.js frontend
│   │   ├── app/
│   │   ├── components/
│   │   ├── features/
│   │   ├── hooks/
│   │   ├── lib/
│   │   └── tests/
│   └── api/                       # FastAPI entry point and HTTP routes
│       ├── main.py
│       ├── routes/
│       ├── middleware/
│       └── tests/
├── packages/
│   └── contracts/                 # Shared API schemas/types if needed
├── quantlab/                      # Python domain/application packages
│   ├── common/
│   ├── data/
│   │   ├── providers/
│   │   ├── ingestion/
│   │   ├── normalization/
│   │   ├── validation/
│   │   ├── corporate_actions/
│   │   └── storage/
│   ├── research/
│   │   ├── hypotheses/
│   │   ├── experiments/
│   │   ├── strategies/
│   │   ├── statistics/
│   │   └── reports/
│   ├── backtesting/
│   │   ├── engine/
│   │   ├── events/
│   │   ├── execution/
│   │   ├── costs/
│   │   ├── portfolio/
│   │   └── metrics/
│   ├── ml/
│   │   ├── features/
│   │   ├── datasets/
│   │   ├── training/
│   │   ├── evaluation/
│   │   └── registry/
│   ├── portfolio/
│   │   ├── optimization/
│   │   └── analytics/
│   ├── risk/
│   │   ├── metrics/
│   │   ├── limits/
│   │   └── stress_testing/
│   ├── ai/
│   │   ├── orchestrator/
│   │   ├── tools/
│   │   ├── prompts/
│   │   ├── evaluation/
│   │   └── sandbox/
│   └── execution/
│       ├── brokers/
│       ├── proposals/
│       ├── approvals/
│       ├── orders/
│       └── reconciliation/
├── workers/
├── database/
│   ├── migrations/
│   ├── seeds/
│   └── schemas/
├── infrastructure/
│   ├── docker/
│   ├── compose/
│   ├── monitoring/
│   └── deployment/
├── notebooks/                     # Exploratory only; production logic lives in packages
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── regression/
│   ├── backtesting/
│   └── security/
├── docs/
│   ├── architecture/
│   ├── adr/
│   ├── api/
│   ├── data_dictionary/
│   ├── research_methodology/
│   ├── operations/
│   └── compliance/
├── scripts/
├── .github/workflows/
├── .env.example
├── .gitignore
├── docker-compose.yml
├── pyproject.toml
├── pnpm-workspace.yaml
├── README.md
└── QUANTLAB_CODEX_MASTER_SPEC.md
```

---

# 5. Data engineering specification

## 5.1 Provider adapter pattern

Never couple ingestion code to one vendor's response format. Define a provider interface and implement one provider at a time.

Illustrative contract:

```python
from datetime import date, datetime
from typing import Protocol


class MarketDataProvider(Protocol):
    def get_instruments(self) -> list[dict]: ...
    def get_daily_bars(
        self,
        instrument_id: str,
        start: date,
        end: date,
    ) -> list[dict]: ...
    def get_corporate_actions(
        self,
        instrument_id: str,
        start: date,
        end: date,
    ) -> list[dict]: ...
```

The exact types should be replaced with validated domain schemas during implementation. Provider-specific identifiers must be mapped to QUANTLAB's stable internal instrument IDs.

## 5.2 Canonical daily bar schema

At minimum:

```text
instrument_id
exchange
trading_date
open
high
low
close
volume
turnover                 # nullable if unavailable
source_id
source_record_id         # nullable if provider has one
retrieved_at
source_as_of              # nullable if provider exposes it
currency
adjustment_basis
schema_version
```

Use decimal-safe representations for prices and money where accounting correctness requires it. Decide on storage precision explicitly and document it. Avoid mixing adjusted and unadjusted prices in the same field without an explicit adjustment basis.

Validation rules include:

- `low <= min(open, close) <= max(open, close) <= high` within documented tolerance.
- Non-negative volume and turnover.
- No duplicate `(instrument_id, exchange, trading_date, source/version)` records.
- Trading date must be valid for the relevant exchange calendar unless a documented exception applies.
- Nulls must be deliberate and visible.
- Currency and unit conventions must be explicit.
- Corporate-action adjustment status must be explicit.

## 5.3 Raw, normalized and curated layers

Use three logical layers:

1. **Raw:** immutable source response or source file, stored with checksum and metadata.
2. **Normalized:** parsed, typed, schema-validated records with provider-specific details mapped to canonical fields.
3. **Curated:** research-ready datasets with documented adjustment and point-in-time rules.

A correction must create a new version or correction record. Do not silently rewrite the raw source.

## 5.4 Point-in-time correctness

Every value that could be unavailable to a historical trader needs an availability timestamp or a documented point-in-time rule.

Examples:

- Index constituents must be effective-dated.
- Company results must be timestamped by public release/availability time, not merely by financial period end.
- Corporate actions must be represented with announcement, ex-date and effective details when available.
- A feature calculated using end-of-day close cannot be used for an order filled earlier that same day.
- Revised or restated data must not leak into earlier historical observations.

When reliable point-in-time data does not exist, label the affected research as limited and do not make an institutional-quality claim.

## 5.5 Dataset snapshots and reproducibility

Each experiment run must reference immutable dataset snapshot IDs. A snapshot manifest should contain:

- Dataset ID and version.
- Provider and source licence reference.
- Extraction timestamp.
- Date range and universe.
- Record count.
- Schema version.
- Adjustment methodology.
- Checksums.
- Known gaps and quality warnings.

Do not commit licensed datasets to Git. Store only code, schema, manifests and permitted metadata in the repository. Respect provider storage, display and redistribution terms.

## 5.6 Initial universe and data sourcing

Begin with one legally usable daily historical data source and one narrow universe. Do not promise a fixed number of years or instruments until the selected provider's product, entitlement and actual coverage have been checked.

Potential sources to evaluate:

- NSE Data & Analytics / official NSE datasets.
- Broker market-data APIs, such as Kite Connect, subject to current plan, exchange coverage, retention and permitted-use terms.
- Additional licensed vendors only after comparing historical depth, adjusted data, corporate actions, point-in-time fundamentals, delivery statistics, cost and licence terms.

Do not rely on unofficial scraping as the foundation of the data platform.

---

# 6. Research methodology and statistical standards

## 6.1 Experiment specification

Every experiment must be defined before execution. Store a versioned specification with:

```text
experiment_id
hypothesis_id
hypothesis_text
universe_id
universe_as_of_rule
benchmark_id
observation_frequency
signal_timestamp_rule
entry_rule
exit_rule
holding_period
rebalance_rule
position_sizing_rule
feature_definitions
target_definition
transaction_cost_model_id
slippage_model_id
liquidity_constraints
validation_plan
training_window
validation_window
final_holdout_window
random_seed
code_commit
software_environment
created_at
```

The specification must be machine-readable and validated before a run starts.

## 6.2 Hypothesis formulation

Convert vague statements into falsifiable hypotheses. For every hypothesis define:

- Population/universe.
- Observation unit.
- Signal and feature definitions.
- Prediction or holding horizon.
- Outcome/target.
- Null and alternative hypotheses where relevant.
- Benchmark or control group.
- Costs and execution assumptions.
- Primary metric.
- Validation and robustness checks.

Prefer one primary outcome metric per experiment. Additional metrics are secondary diagnostics, not opportunities to select whichever number looks best.

## 6.3 Backtesting execution rules

The backtesting engine must be deterministic for fixed data, code, configuration and random seed.

Required rules:

- Use an event-driven timeline with explicit signal, order, fill and portfolio valuation timestamps.
- A signal requiring the official close must not be filled at that same close by default. Use a feasible subsequent execution point, such as the next eligible session, unless a separately modelled execution mechanism justifies another fill.
- Model partial fills and liquidity constraints when supported by available data.
- Model spread and slippage; do not assume fills at a theoretical mid-price.
- Apply a configurable, effective-dated transaction-cost schedule for the applicable instrument, exchange, segment and order type.
- Distinguish price return from total return and include cash dividends/corporate actions consistently.
- Model cash, holdings, settlement assumptions and corporate actions coherently.
- Handle suspensions, missing bars, price bands/circuit constraints and delistings when the data supports it; otherwise surface limitations.
- Do not assume unlimited liquidity or unrestricted short selling.
- Record rejected, unfilled and partially filled orders.
- Use the same execution assumptions when comparing candidate strategies and benchmarks where appropriate.

Transaction-cost components may include brokerage, STT, exchange transaction charges, GST, stamp duty, SEBI charges, applicable duties/levies and slippage. Rates and rules change. Never hardcode current rates as timeless constants. Implement a versioned, effective-dated cost schedule and verify rates from current primary sources before use.

## 6.4 Bias and leakage controls

The engine and research workflow must explicitly test for:

- Look-ahead bias.
- Survivorship bias.
- Data leakage.
- Selection bias.
- Timestamp and publication-time leakage.
- Corporate-action leakage.
- Universe construction bias.
- Parameter mining and repeated hypothesis testing.
- Execution-price optimism.
- Liquidity and capacity assumptions.

Add regression tests that intentionally introduce common leakage patterns and verify that validation catches them where feasible.

## 6.5 Validation design

Default to chronological validation, not random shuffling.

Use:

- Expanding-window or rolling-window walk-forward validation.
- A final untouched holdout period.
- Purging and embargo where labels overlap or information spans adjacent periods.
- Nested validation for model/parameter selection where appropriate.
- A recorded experiment registry to make repeated trials visible.
- Multiple-testing corrections such as Benjamini–Hochberg where suitable.
- Bootstrap or block-bootstrap uncertainty estimates where assumptions permit.
- Sensitivity analysis across reasonable parameter ranges and cost assumptions.

Do not repeatedly tune against the final holdout. Once the holdout is used for decisions, it is no longer an untouched holdout; record that fact and establish a new evaluation protocol if needed.

## 6.6 Required backtest metrics

At minimum:

- CAGR and cumulative return.
- Volatility.
- Sharpe and Sortino ratios, with annualization assumptions documented.
- Maximum drawdown and drawdown duration.
- Calmar ratio.
- Win rate, average win/loss and profit factor.
- Turnover and holding period.
- Exposure and concentration.
- Benchmark-relative return, alpha/beta where statistically appropriate.
- Trading costs as a percentage of gross and net returns.
- Capacity/liquidity diagnostics where supported.

Always show gross and net performance separately. Include sample size, date range, data quality flags and benchmark definition alongside headline metrics.

## 6.7 Research report format

Every report should contain:

1. Executive summary.
2. Hypothesis and pre-registered experiment specification.
3. Data sources, licences, date range and limitations.
4. Universe construction and point-in-time method.
5. Feature and target definitions.
6. Execution and cost assumptions.
7. Validation design.
8. Results with uncertainty and sample size.
9. Benchmark comparison.
10. Robustness and sensitivity analysis.
11. Failure modes and limitations.
12. Reproducibility references: dataset snapshot, code commit, environment and experiment run ID.
13. Research conclusion: supported, not supported, inconclusive or data-limited.

Avoid promotional language such as “guaranteed edge”, “sure-shot strategy” or “AI predicts the market”.

---

# 7. Machine-learning standards

## 7.1 Feature definitions

Store feature metadata:

```text
feature_id
name
description
formula_or_code_version
input_columns
lookback_window
availability_timestamp_rule
null_handling
normalization_method
point_in_time_safe
created_at
```

Feature calculations must be deterministic and have unit tests on small known datasets. Do not calculate features using values later than the prediction timestamp.

## 7.2 Candidate targets

Examples for research—not promises of predictability:

- Forward 5/20-session return relative to a point-in-time sector or market benchmark.
- Probability of outperforming a benchmark over a defined horizon.
- Forward realized volatility.
- Market regime label defined using a documented, non-leaking procedure.
- Cross-sectional ranking of expected relative returns.

Avoid ambiguous labels such as “stock will go up” without a precise horizon, benchmark and treatment of costs.

## 7.3 Metrics

For classification:

- ROC-AUC and PR-AUC where relevant.
- Precision/recall at a defined operating threshold.
- Brier score and calibration diagnostics.
- Confusion matrix with class prevalence.

For regression/ranking:

- MAE/RMSE where useful.
- Rank IC / Spearman correlation.
- Top-k spread and long-short spread only under feasible assumptions.
- Turnover and net portfolio utility.

For volatility:

- Forecast error and calibration.
- Coverage of prediction intervals where implemented.

Model metrics and investment utility must be reported separately. A better prediction score does not automatically imply a better tradable strategy.

## 7.4 Model registry

Each registered model must preserve:

- Model name and version.
- Training code commit.
- Training dataset snapshot.
- Feature schema and feature versions.
- Target definition.
- Training and validation windows.
- Hyperparameters and random seeds.
- Metrics and evaluation artifacts.
- Known limitations.
- Approval state and intended use.

No model may be promoted to a trade-proposal signal solely because it has the highest in-sample score.

---

# 8. Portfolio and risk specification

## 8.1 Initial portfolio methods

Implement in this order:

1. Equal weight.
2. Benchmark or cap-weight baseline where data permits.
3. Minimum variance.
4. Mean-variance with explicit return-estimate limitations.
5. Risk parity.
6. Signal-weighted allocation under risk constraints.

Use constrained optimization and robust failure handling. Show when the optimizer fails, is infeasible or produces unstable weights. Do not silently fall back to arbitrary allocations.

## 8.2 Risk metrics and controls

- Historical volatility.
- Beta and rolling correlation.
- Historical VaR and Expected Shortfall at configured confidence levels.
- Maximum drawdown and duration.
- Sector and instrument concentration.
- Gross/net exposure.
- Liquidity and turnover.
- Stress scenarios.

Stress scenarios should be labelled hypothetical or historical. Example scenarios include a broad-market shock, a sector-specific shock, a single-stock gap and a liquidity deterioration event. Do not imply that a finite scenario set captures every possible loss.

All risk calculations must identify their lookback window, return frequency, missing-data treatment and annualization assumptions.

---

# 9. Broker integration and trading safety

## 9.1 Adapter design

Define a broker-neutral interface. Provider-specific request/response details must remain inside each adapter.

Illustrative interface:

```python
class BrokerAdapter:
    def authenticate(self): ...
    def get_quotes(self, instruments): ...
    def get_holdings(self): ...
    def get_positions(self): ...
    def get_margins(self): ...
    def get_orders(self): ...
    def get_order_status(self, broker_order_id): ...
    def place_order(self, approved_order): ...
    def cancel_order(self, broker_order_id): ...
```

The first implementation should be read-only. Add order placement only after the separate go-live approval gate.

## 9.2 Trade proposal and approval

A proposal must include:

- Account reference (masked in UI and logs).
- Exchange and instrument identity.
- Buy/sell side.
- Quantity.
- Order type and product type.
- Limit/trigger price where applicable.
- Validity and expiry.
- Quote and market-data timestamp.
- Estimated cash/margin impact where supported.
- Cost estimate.
- Portfolio impact and risk-check results.
- Strategy/model and experiment provenance.
- Immutable proposal payload hash.

Approval must be an authenticated human action. The approval record must identify the user, timestamp, proposal hash and outcome. A changed order payload requires a new approval.

## 9.3 Safety gates

Before any order submission:

- Live trading mode must be explicitly enabled by configuration and authorized by the user.
- Broker credentials must be available only on the server through secure secret storage.
- The proposal must be unexpired and approved against its exact payload hash.
- Market data must be fresh under a configurable threshold.
- Pre-trade risk limits must pass.
- Available funds/margin must be checked with the broker where supported.
- Duplicate submission must be prevented using idempotency/reconciliation logic.
- Order rate limits and broker/exchange requirements must be respected.
- Kill switch must be operational.
- Every decision and broker response must be audited.

On timeout after submission, do not blindly resubmit. Query/reconcile broker order state first.

## 9.4 Kill switch and operational states

Support at least:

```text
RESEARCH_ONLY
PAPER_TRADING
BROKER_READ_ONLY
LIVE_APPROVAL_REQUIRED
EXECUTION_DISABLED
EMERGENCY_STOP
```

Default deployment state: `RESEARCH_ONLY`.

A kill switch must block new order submissions independently of the AI agent and frontend. It must not assume that cancelling all existing orders or liquidating positions is always safe; those actions require separately defined controls and broker support.

## 9.5 India-specific regulatory and broker gate

Indian retail API/algo rules, exchange operational standards, broker API policies, order tagging, static-IP requirements, rate limits, registration/empanelment requirements and other conditions may change. The software must not hardcode a legal interpretation as a timeless fact.

Before enabling any broker order placement, create a dated compliance checklist and verify the current primary-source documents and the selected broker's current written requirements. At minimum review:

- SEBI's circular on safer participation of retail investors in algorithmic trading (4 February 2025) and subsequent amendments/extensions.
- Current SEBI implementation timeline and operational standards.
- Current NSE/BSE circulars and exchange procedures relevant to the broker and order pathway.
- Current broker API terms, onboarding rules, authentication requirements, static-IP requirements where applicable, order tagging, rate limits, supported order types and restrictions.
- Whether the proposed use is personal, third-party, distributed or commercial; do not assume the same requirements apply to each.

As of the preparation date of this document (11 November 2026), official NSE material references later operational updates, including an April 2026 circular for Client Direct API/member-front-end retail algo processes. Re-check the latest notices immediately before implementation; this document is not legal advice and does not certify compliance.

Primary-source references to verify:

- SEBI retail algorithmic-trading circular: https://www.sebi.gov.in/legal/circulars/feb-2025/safer-participation-of-retail-investors-in-algorithmic-trading_91614.html
- SEBI September 2025 implementation-timeline extension: https://www.sebi.gov.in/legal/circulars/sep-2025/extension-of-timeline-for-implementation-of-sebi-circular-dated-february-04-2025-on-safer-participation-of-retail-investors-in-algorithmic-trading-_96979.html
- NSE decision-support tools / algorithm-trading information: https://www.nseindia.com/static/trade/platform-services-non-neat-decision-support-tools-algorithm-trading
- NSE empanelled algo provider information: https://www.nseindia.com/static/trade/empanelled-algo-providers-exchange
- Kite Connect historical candle documentation: https://kite.trade/docs/connect/v3/historical/
- Kite Connect order API documentation: https://kite.trade/docs/connect/v3/orders/

Do not infer that a broker API feature means the proposed use is permitted. Confirm the current rules with the broker and, for commercial activity or uncertainty, qualified Indian securities-market counsel/compliance professionals.

---

# 10. Security, privacy and reliability

## 10.1 Security baseline

- Use established authentication; do not invent cryptography.
- Enforce authorization server-side on every sensitive route.
- Store secrets in environment/secret management, never in frontend bundles or Git.
- Encrypt sensitive tokens at rest and use TLS in transit.
- Mask account identifiers and personal details in logs.
- Validate and rate-limit external API requests.
- Protect against SSRF, injection, insecure deserialization and unsafe file uploads.
- Restrict AI tools to allowlisted operations.
- Run AI-generated code only in disposable, resource-limited sandboxes with no broker credentials and no unrestricted network access.
- Keep dependencies pinned/locked and run vulnerability scans where practical.
- Maintain backups and test restoration.

## 10.2 Auditability

Maintain append-only audit events for:

- Authentication and authorization events.
- Data ingestion and corrections.
- Experiment creation, changes and execution.
- Model training, registration and promotion.
- AI prompts, tool calls and generated reports (subject to privacy/security policy).
- Portfolio changes.
- Trade proposals, approvals, rejections and expiry.
- Broker requests, responses and reconciliation.
- Configuration changes and emergency-stop actions.

Do not log secrets, complete access tokens or unnecessary personal data.

## 10.3 Reliability

- Idempotent jobs and job state tracking.
- Retry with bounded exponential backoff for transient provider failures.
- Dead-letter handling for repeatedly failing jobs.
- Database transactions for critical state changes.
- Stale-data indicators and provider health status.
- Structured logs and basic service metrics.
- Health/readiness endpoints.
- Broker reconciliation before retrying uncertain order submissions.
- Backup and recovery procedure.

---

# 11. API surface (initial proposal)

Use versioned routes, typed request/response schemas and consistent error envelopes. Names can change with an ADR, but behaviour must remain documented.

```text
GET    /api/v1/health
GET    /api/v1/instruments
GET    /api/v1/instruments/{instrument_id}
GET    /api/v1/market/bars
GET    /api/v1/market/indices
GET    /api/v1/universes
GET    /api/v1/universes/{universe_id}/constituents

GET    /api/v1/features
POST   /api/v1/experiments
GET    /api/v1/experiments
GET    /api/v1/experiments/{experiment_id}
POST   /api/v1/experiments/{experiment_id}/runs
GET    /api/v1/runs/{run_id}
GET    /api/v1/runs/{run_id}/results
POST   /api/v1/runs/compare

POST   /api/v1/models/train
GET    /api/v1/models
GET    /api/v1/models/{model_id}

POST   /api/v1/portfolios
GET    /api/v1/portfolios/{portfolio_id}
POST   /api/v1/portfolios/{portfolio_id}/optimize
GET    /api/v1/portfolios/{portfolio_id}/risk

POST   /api/v1/ai/research-requests
GET    /api/v1/ai/research-requests/{request_id}

GET    /api/v1/execution/mode
GET    /api/v1/execution/proposals
POST   /api/v1/execution/proposals
POST   /api/v1/execution/proposals/{proposal_id}/approve
POST   /api/v1/execution/proposals/{proposal_id}/reject
```

Do not expose a live order-placement endpoint until the live-execution milestone is explicitly approved and all gates in Section 9 are complete.

---

# 12. User interface specification

## 12.1 Visual direction

Build a clean, high-density professional research terminal. Prefer a dark neutral base with restrained purple/blue accents. Prioritize information hierarchy and legibility over decorative effects.

Avoid copying proprietary terminal branding or protected UI layouts.

## 12.2 Primary navigation

- Overview
- Markets
- Stock Screener
- Strategy Lab
- ML Research
- Portfolio Lab
- Risk Analytics
- AI Researcher
- Paper Trading
- Execution (hidden/disabled until eligible)
- Experiment History
- Settings and Data Sources

## 12.3 Core screens

**Overview:** market snapshot, watchlists, recent experiments, data freshness, paper portfolio summary and system health.

**Markets:** instrument chart, benchmark comparison, corporate-action markers, data source/as-of information.

**Screener:** configurable filters, saved screens, point-in-time universe selection for historical research.

**Strategy Lab:** strategy configuration, run status, equity curve, drawdown, trade list, benchmark comparison, costs and diagnostics.

**ML Research:** dataset/feature selection, target definition, validation configuration, model comparison, calibration and feature diagnostics.

**Portfolio Lab:** holdings, allocations, optimization assumptions, exposures, correlation and scenario analysis.

**AI Researcher:** question input, interpreted hypothesis, proposed specification, approval to run, tool activity and evidence-linked report.

**Paper Trading:** simulated positions, orders, fills, cash, P&L and simulation assumptions.

**Experiment History:** searchable runs, configuration diffs, reproducibility and comparison.

All financial charts must identify units, currency, data frequency and date range. Never show a metric without its relevant definition or context.

---

# 13. Development plan and release gates

The target is approximately 600–900 focused engineering hours over roughly 9 months. This is a planning estimate, not a delivery guarantee. A smaller working product is preferable to a rushed platform with unreliable financial calculations.

## Phase 0 — Repository and engineering foundation

Deliverables:

- Monorepo and dependency management.
- Local development environment with Docker Compose.
- FastAPI health endpoint.
- Next.js shell.
- PostgreSQL migrations.
- CI for lint, type checks and tests.
- `.env.example`, secret hygiene and README.
- Initial ADRs.

Exit criteria:

- Fresh clone can be set up from documented instructions.
- CI passes.
- No secrets or licensed datasets are committed.

## Phase 1 — Market data foundation

Deliverables:

- Instrument master.
- One licensed/provider-backed daily-bar adapter or explicitly synthetic test fixture.
- Raw/normalized/curated ingestion layers.
- Data-quality validation and quarantine.
- Dataset manifests and checksums.
- Historical query API.

Exit criteria:

- Re-ingesting the same source is idempotent.
- Invalid rows are surfaced.
- Source and retrieval provenance can be inspected.
- A dataset snapshot can be reproduced.

## Phase 2 — Market Explorer

Deliverables:

- Instrument search.
- Daily chart.
- Benchmark comparison.
- Watchlist.
- Basic screener.
- Data freshness and gaps.

Exit criteria:

- UI uses the API, not hardcoded sample market values.
- Missing data is visible.
- Data timestamps and units are shown.

## Phase 3 — Deterministic backtesting engine

Deliverables:

- Strategy interface.
- Event-driven simulation.
- Order/position/cash accounting.
- Simple execution and transaction-cost models.
- Benchmark and performance metrics.
- Moving-average baseline strategy.

Exit criteria:

- Tests cover order timing, cash accounting, position accounting, splits/dividends where supported, costs and determinism.
- Results match hand-calculated toy cases.
- No same-close fill shortcut for close-derived signals by default.

## Phase 4 — Quant research and experiment registry

Deliverables:

- Versioned experiment specification.
- Strategy library expansion.
- Statistical diagnostics.
- Walk-forward and holdout orchestration.
- Experiment comparison and report template.

Exit criteria:

- Same run can be reproduced from dataset snapshot, code commit and configuration.
- Failed experiments remain recorded.
- Costs and benchmark are visible in the report.

## Phase 5 — Machine learning

Deliverables:

- Feature registry and point-in-time checks.
- Chronological dataset builder.
- Baseline and tree-based models.
- Walk-forward validation.
- MLflow integration.
- Model registry and evaluation reports.

Exit criteria:

- Leakage tests pass.
- Model evaluation is reproducible.
- Predictive metrics and portfolio metrics are shown separately.

## Phase 6 — Portfolio and risk

Deliverables:

- Portfolio representation.
- Allocation baselines and selected optimizers.
- Exposure and concentration reports.
- VaR/Expected Shortfall and stress scenarios.

Exit criteria:

- Optimizer handles infeasible and unstable cases explicitly.
- Risk assumptions and windows are visible.
- Portfolio calculations have hand-checked unit tests.

## Phase 7 — AI Research Analyst

Deliverables:

- Structured hypothesis parser.
- Experiment specification generator.
- Allowlisted typed tools.
- User approval before execution.
- Evidence-grounded report generator.
- Agent evaluation benchmark.

Exit criteria:

- Agent cannot bypass tool permissions.
- Agent cannot invent numeric results.
- Revisions create new experiment versions.
- Tool calls and provenance are logged.

## Phase 8 — Paper trading and broker read-only integration

Deliverables:

- Simulated order/fill engine.
- Paper portfolio accounting.
- Broker adapter interface.
- One broker read-only adapter, if credentials/API access are available.
- Position and order reconciliation.

Exit criteria:

- Paper trading is clearly separated from live trading.
- Broker credentials remain server-side.
- No live order can be submitted in this phase.

## Phase 9 — Human-approved execution (separate opt-in milestone)

Deliverables:

- Dated compliance checklist.
- Current broker and exchange requirement verification.
- Security review.
- Proposal/approval payload binding.
- Pre-trade checks and limits.
- Idempotent submission and reconciliation.
- Kill switch and audit review.

Exit criteria:

- User explicitly authorizes this milestone.
- Broker confirms the intended use and required configuration.
- Current legal/compliance requirements are reviewed.
- All safety tests pass.
- Live mode is disabled by default and can be disabled independently of the AI system.

---

# 14. Definition of Done

A feature is not complete merely because it renders in the UI. It must satisfy the relevant criteria below.

## Data

- [ ] At least one legally usable data source integrated.
- [ ] Provider adapters isolated from canonical schemas.
- [ ] Raw data preserved immutably.
- [ ] Validation and quarantine implemented.
- [ ] Effective-dated instrument identity and symbol mapping.
- [ ] Data provenance and snapshot manifests.
- [ ] Point-in-time limitations surfaced.

## Quant research

- [ ] Custom deterministic event-driven backtester.
- [ ] At least five strategy families over time.
- [ ] Realistic order timing and configurable costs/slippage.
- [ ] Benchmark comparison.
- [ ] Walk-forward and untouched holdout workflow.
- [ ] Multiple-testing and overfitting diagnostics.
- [ ] Reproducible experiment reports.

## Machine learning

- [ ] Baselines before complex models.
- [ ] Versioned feature definitions.
- [ ] Point-in-time leakage checks.
- [ ] Chronological validation.
- [ ] Model registry and reproducible metrics.
- [ ] Predictive performance separated from investment utility.

## Portfolio/risk

- [ ] Multiple allocation baselines.
- [ ] Concentration and liquidity controls.
- [ ] VaR and Expected Shortfall with documented assumptions.
- [ ] Stress tests.
- [ ] Optimizer failure/instability handling.

## AI

- [ ] Structured hypothesis interpretation.
- [ ] User approval of experiment spec.
- [ ] Allowlisted tools and sandboxed execution.
- [ ] Evidence-grounded reporting.
- [ ] Experiment immutability/versioning.
- [ ] Agent evaluation tests.

## Execution

- [ ] Paper trading independent of live broker.
- [ ] Read-only broker mode before order placement.
- [ ] Exact-payload human approval.
- [ ] Pre-trade checks, idempotency and reconciliation.
- [ ] Kill switch and immutable audit events.
- [ ] Current broker/exchange/compliance review before enabling live orders.

A profitable strategy is not a required acceptance criterion. It is not controllable and would create the wrong incentive.

---

# 15. First 14-day implementation sprint

The first sprint should create a narrow, end-to-end vertical slice. Adjust the order if the existing repository already contains working components.

| Day | Task | Acceptance result |
|---|---|---|
| 1 | Inspect repo; create workspace, Python environment, Next.js shell and Docker setup | Fresh local setup works |
| 2 | Add PostgreSQL and first migrations | Database starts and migrations apply |
| 3 | Define instrument and daily-bar schemas | Typed, documented canonical models |
| 4 | Add first provider adapter or clearly labelled fixture adapter | Provider boundary tested |
| 5 | Implement raw ingestion and metadata | Raw records and provenance saved |
| 6 | Add normalization and validation | Invalid records quarantined |
| 7 | Add idempotent ingestion and dataset manifest | Re-run produces no duplicates |
| 8 | Add historical query service/API | Query by instrument and date range |
| 9 | Calculate basic returns and volume features | Deterministic feature tests pass |
| 10 | Build simple market explorer chart | UI uses API-backed data |
| 11 | Define strategy interface and moving-average example | Strategy emits dated signals |
| 12 | Implement small deterministic backtest slice | Orders, fills, cash and positions tracked |
| 13 | Write hand-calculated toy cases and regression tests | Backtest matches expected results |
| 14 | Documentation, ADR review, CI and v0.1 tag | Reproducible foundation release |

Do not fabricate a historical market dataset to make the UI look complete. For development, use small synthetic fixtures labelled `SYNTHETIC_TEST_DATA`; never mix them with real data or performance reports.

---

# 16. Testing strategy

## 16.1 Test layers

- **Unit tests:** formulas, indicators, cost calculations, validation, portfolio accounting and risk metrics.
- **Property-based tests:** invariants such as cash/position conservation and OHLC constraints.
- **Integration tests:** provider adapter to raw store to normalized store to query API.
- **Backtesting regression tests:** fixed toy datasets with hand-calculated expected results.
- **Leakage tests:** intentionally misaligned features/targets and point-in-time violations.
- **Security tests:** authorization boundaries, secret exposure, unsafe tool execution and injection.
- **End-to-end tests:** important user journeys in the web application.

## 16.2 Important invariants

- Portfolio cash and holdings reconcile with recorded fills and corporate actions under the documented accounting rules.
- No fill occurs before its order is eligible.
- A close-derived signal cannot receive a same-close fill by default.
- Re-running identical deterministic backtest inputs yields identical outputs within documented numerical tolerance.
- A failed ingestion does not partially publish a curated dataset as complete.
- Every experiment run references a fixed dataset snapshot and code version.
- Every broker proposal approved by a user matches the payload submitted.
- A disabled execution state prevents broker order submission regardless of frontend state.

---

# 17. Documentation requirements

Maintain these documents as the project evolves:

- `README.md`: product overview, setup and current status.
- `docs/architecture/system-overview.md`: current architecture.
- `docs/adr/`: architecture decision records with context, decision and consequences.
- `docs/data_dictionary/`: canonical schemas and data semantics.
- `docs/research_methodology/`: experiment design, validation and bias controls.
- `docs/operations/`: local setup, deployment, backup and incident response.
- `docs/compliance/`: dated broker/exchange/SEBI verification checklist and evidence.
- `docs/security/`: threat model, secrets and access-control decisions.

Update documentation when implementation differs from this specification. Do not leave documentation describing functionality that does not exist.

---

# 18. Suggested environment variables

Create `.env.example` with placeholders only. Never add real values.

```dotenv
APP_ENV=development
APP_NAME=QUANTLAB
API_BASE_URL=http://localhost:8000
WEB_BASE_URL=http://localhost:3000

DATABASE_URL=postgresql+psycopg://quantlab:quantlab@localhost:5432/quantlab
REDIS_URL=redis://localhost:6379/0

MARKET_DATA_PROVIDER=fixture
MARKET_DATA_API_KEY=
MARKET_DATA_API_SECRET=

MLFLOW_TRACKING_URI=http://localhost:5000

AI_PROVIDER=
AI_API_KEY=
AI_MODEL=

BROKER_MODE=disabled
BROKER_PROVIDER=
BROKER_API_KEY=
BROKER_API_SECRET=
BROKER_ACCESS_TOKEN=

EXECUTION_MODE=RESEARCH_ONLY
```

The exact database driver and URL scheme should match the selected library. Use separate secrets per environment. Do not use real broker credentials in local tests or CI.

---

# 19. Initial Codex task prompt

After placing this document in the repository root, use the following prompt:

```text
Read QUANTLAB_CODEX_MASTER_SPEC.md completely before making changes.

First inspect the existing repository, Git status, dependency files, tests and current functionality. Do not generate the entire platform at once.

Your first task is Phase 0 only: establish or verify the repository foundation described in Sections 3, 4, 13 and 15. If the repository already has working pieces, preserve and improve them rather than replacing them.

Before coding, report:
1. Current repository structure and what already works.
2. Gaps against Phase 0.
3. A short implementation plan.
4. Any assumptions or blockers.

Then implement only the smallest complete Phase 0 slice. Add tests and CI where appropriate, run the available checks, update README and relevant docs, and report exact commands and results. Do not connect to a real market-data or broker account. Do not create fake performance claims or enable execution.
```

For later work, ask Codex to implement one named phase or one acceptance criterion at a time.

---

# 20. Reference links and verification notes

These are starting points for primary-source verification, not a substitute for checking current terms at implementation time.

## Indian market data and exchange information

- NSE Data & Analytics: https://www.nseindia.com/market-data
- NSE historical reports: https://www.nseindia.com/all-reports
- NSE algorithm-trading / decision-support information: https://www.nseindia.com/static/trade/platform-services-non-neat-decision-support-tools-algorithm-trading

## Broker developer documentation

- Kite Connect product/API: https://zerodha.com/products/api/
- Kite Connect historical data: https://kite.trade/docs/connect/v3/historical/
- Kite Connect orders: https://kite.trade/docs/connect/v3/orders/
- Kite Connect FAQ: https://support.zerodha.com/category/trading-and-markets/general-kite/kite-api/articles/kite-connect-api-faqs

## Indian retail algorithmic trading framework

- SEBI circular, 4 February 2025: https://www.sebi.gov.in/legal/circulars/feb-2025/safer-participation-of-retail-investors-in-algorithmic-trading_91614.html
- SEBI implementation timeline extension, 30 September 2025: https://www.sebi.gov.in/legal/circulars/sep-2025/extension-of-timeline-for-implementation-of-sebi-circular-dated-february-04-2025-on-safer-participation-of-retail-investors-in-algorithmic-trading-_96979.html
- NSE empanelled algo provider information: https://www.nseindia.com/static/trade/empanelled-algo-providers-exchange

## Research and engineering references

- VectorBT documentation: https://vectorbt.dev/
- MLflow documentation: https://mlflow.org/docs/latest/index.html
- scikit-learn documentation: https://scikit-learn.org/stable/
- XGBoost documentation: https://xgboost.readthedocs.io/
- PyTorch documentation: https://pytorch.org/docs/stable/index.html
- FastAPI documentation: https://fastapi.tiangolo.com/
- Polars documentation: https://docs.pola.rs/

---

# 21. Final engineering principles

1. **Correctness before cleverness.** A simple, verified model is better than a sophisticated, unverified one.
2. **Evidence before narrative.** Every report claim must trace to data and a reproducible calculation.
3. **Point-in-time data before predictive modelling.** Do not train on information that was unavailable at the decision time.
4. **Net results before gross results.** Include feasible costs, slippage and liquidity assumptions.
5. **Out-of-sample evidence before promotion.** Training performance is not a trading edge.
6. **Deterministic core, probabilistic assistant.** The AI may propose and explain; deterministic services calculate and validate.
7. **Human authority over live orders.** No LLM may authorize or submit a live trade on its own.
8. **Security by design.** Broker credentials, financial data and execution controls are sensitive assets.
9. **Build in vertical slices.** Integrate and test continuously; do not build a giant disconnected scaffold.
10. **Failed experiments are first-class results.** Preserve them and learn from them; never hide them to manufacture a success story.

**The success criterion for QUANTLAB is not that it predicts the market. It is that it provides a trustworthy, reproducible and technically rigorous environment in which market hypotheses can be tested—and rejected when the evidence does not support them.**
