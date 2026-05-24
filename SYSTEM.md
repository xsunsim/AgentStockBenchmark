# AgentStockBenchmark System Design

[中文版本](./SYSTEM_CN.md)

This document describes the production design implemented in `AgentStockBenchmark` and
the result-artifact boundary with `AgentStockBenchmarkResults`. It is meant for maintainers and
coding agents that need to reason about the benchmark without rediscovering the
architecture from source.

## Goals

AgentStockBenchmark evaluates stock ranking strategies produced by coding agents.
The benchmark must make three things explicit:

1. What code and prompt produced each ranking.
2. What market data and universe were available on each ranking date.
3. How frozen rankings became frozen portfolios and realized accounting.

The system is intentionally conservative. Production artifacts are appendable and
restartable, research artifacts are isolated, and dates are canonicalized so that
path matching and audit checks are predictable.

## Repositories

### `AgentStockBenchmark`

This is the engine repository. It owns:

- prompts under `prompts/<prompt_id>/prompt.md`;
- reference prompts under `prompts/reference/`;
- strategy submissions under `strategies/<prompt_id>/<strategy_slug>/strategy.py`;
- strategy metadata under `strategies/<prompt_id>/<strategy_slug>/strategy.json`;
- benchmark CLI entrypoint `agentstockbenchmark`;
- stage modules;
- daily workflow, audit, manifests, and research orchestration;
- local tests.

### `AgentStockBenchmarkResults`

This is the result repository. It owns:

- raw and derived market data;
- frozen ranking CSVs;
- frozen portfolio CSVs;
- accounting outputs;
- metrics and leaderboards;
- run, artifact, audit, strategy, and publish manifests;
- result-side CLI entrypoint `agentstockbenchmark-results`.

The engine writes production result artifacts into `AgentStockBenchmarkResults`; the result
package renders and publishes already-audited artifacts. This split keeps
benchmark logic out of the public result surface.

## Canonical Date Contract

`YYYYMMDD` is the only canonical persisted date format for new artifacts.

Accepted CLI inputs:

- `20260519`
- `2026-05-19`
- `today` where implemented by the shared parser

Persisted outputs:

- path components use `YYYYMMDD`;
- CSV artifact date columns use `YYYYMMDD`;
- JSON manifest date fields use `YYYYMMDD`;
- timestamps such as `generated_at_utc` use ISO 8601 because they are wall-clock
  timestamps, not benchmark dates.

Examples:

```text
data/universe/20260519.txt
data/raw/daily/20260519.csv
rankings/20260519/20260519__OpenAI__O3__LinearNeutral.csv
portfolios/20260519/20260519__OpenAI__O3__LinearNeutral.csv
accounting/metrics/20260519.csv
manifests/runs/20260519.json
manifests/artifacts/20260519.json
manifests/audits/20260519.json
```

The date helper lives in `agentstockbenchmark.dates`. New code should use that
module rather than calling `datetime.date.fromisoformat` directly at artifact
boundaries.

## Artifact Writes

Production writes use atomic temp-file-then-rename helpers from
`agentstockbenchmark.io`:

- `atomic_write_text`
- `atomic_write_json`
- `atomic_write_csv`
- `atomic_write_parquet`

The result package has equivalent text and CSV helpers in
`agentstockbenchmark_results.io`.

Atomic writes protect readers from partially written CSV, JSON, and parquet
files during daily production, resume, or publish operations.

## Stage 1: Prompts And Strategies

Stage 1 owns benchmark instructions and submitted strategy code.

Prompt layout:

```text
prompts/20260517/prompt.md
prompts/20260519/prompt.md
prompts/reference/PROMPT_V12.md
prompts/reference/prompt_history/v16/prompt.md
```

Strategy layout:

```text
strategies/<prompt_id>/<strategy_slug>/strategy.py
strategies/<prompt_id>/<strategy_slug>/strategy.json
strategies/<prompt_id>/<strategy_slug>/prompt.md
strategies/<prompt_id>/<strategy_slug>/meta.json
```

`strategy_id` is derived as:

```text
<prompt_id>__<strategy_slug>
```

Example:

```text
```

Cached strategy migration is one-way. It copies cached strategy folders into the
dated strategy layout and removes only trailing cache version suffixes such as
`_202605` or `_v16` from the slug. It should not silently repair agent output.
If a submitted strategy has a syntax error, that error is part of the benchmark
submission unless the owner explicitly requests a repair.

Important modules:

- `agentstockbenchmark.stage1.prompts`
- `agentstockbenchmark.stage1.strategies`
- `agentstockbenchmark.stage1.migration`

## Stage 2: Market Data And Frozen Rankings

Stage 2 has two responsibilities:

1. Prepare OHLCV data for strategy execution.
2. Run strategy code and freeze ranking artifacts before any portfolio or
   accounting step.

### Market Data Layout

Result repository paths:

```text
data/universe/20260519.txt
data/raw/daily/20260519.csv
data/parquet/open.parquet
data/parquet/high.parquet
data/parquet/low.parquet
data/parquet/close.parquet
data/parquet/volume.parquet
```

Daily raw CSV schema:

```text
date,ticker,open,high,low,close,volume
20260519,AAPL,100.0,101.0,99.0,100.5,123456
```

Derived parquets are field-level wide tables:

- index: trading dates;
- columns: tickers;
- values: numeric OHLCV field values.

Missing OHLCV values in derived parquets are encoded as `0`. Valid adjusted
prices and volumes for traded S&P 500 constituents should be positive, so `0`
is the missing-value sentinel in strategy-facing data.

### Universe Drift

The S&P 500 universe changes over time. Each production date has a universe
file. Portfolio construction uses the dated universe file for that ranking date.
If strict universe mode is disabled and an exact file is missing, the portfolio
builder can fall back to the latest universe file or close-parquet columns.
Production audit expects the exact dated universe file.

### Strategy Snapshot Contract

Strategies receive:

```python
dict[str, pandas.DataFrame]
```

Each key is a ticker. Each value has columns:

```text
Date, open, high, low, close, volume
```

The data includes all available history through the ranking date, inclusive.
Missing OHLCV cells are filled with `0` before being handed to strategy code.
Strategies should treat `0` as missing.

### Ranking Artifact Contract

Ranking CSV path:

```text
rankings/<YYYYMMDD>/<strategy_id>.csv
```

Ranking CSV columns:

```text
ranking_date
prompt_id
strategy_slug
strategy_id
ticker
score
strategy_rank
```

Rank semantics:

- higher score is better;
- ties are broken by ticker ascending;
- `strategy_rank` starts at `1`;
- non-finite scores are ignored.

Ranking metadata path:

```text
rankings/<YYYYMMDD>/<strategy_id>.meta.json
```

The metadata captures strategy hash, input ticker count, number of finite scores,
entry and exit dates when available, and status.

Important modules:

- `agentstockbenchmark.stage2.market_data`
- `agentstockbenchmark.stage2.rankings`

## Stage 3: Frozen Portfolios, Accounting, Metrics

Stage 3 starts from frozen ranking artifacts. It does not call strategy code.

### Portfolio Construction

Portfolio CSV path:

```text
portfolios/<YYYYMMDD>/<strategy_id>.csv
```

Portfolio CSV columns:

```text
ranking_date
strategy_id
ticker
score
portfolio_rank
position_dollars
ranking_status
strategy_rank
portfolio_universe_source
portfolio_universe_date
n_portfolio_universe
n_ranked_in_universe
n_ranked_ignored
n_missing_rankings
```

Construction rules:

- portfolio universe is the S&P 500 universe for the ranking date;
- ranked tickers outside the universe are ignored;
- universe tickers missing from the ranking are inserted into the middle in
  ticker-sorted order;
- linear dollar-neutral ladder ranges from `+250` to `-250`;
- portfolios are frozen once written unless `--overwrite` is explicit.

The middle insertion rule avoids implicitly putting missing names at the very
long or very short edge. Missing names still receive positions according to
their portfolio rank, preserving neutrality and full-universe accounting.

### Accounting

Accounting uses the close-price contract:

```text
ranking date t
entry at close t+1
exit at close t+2
```

Daily PnL path:

```text
accounting/daily_pnl/<strategy_id>.csv
```

Daily PnL columns:

```text
ranking_date
entry_date
exit_date
strategy_id
total_pnl
long_pnl
short_pnl
n_positions
n_portfolio_universe
n_ranked_in_universe
n_ranked_ignored
n_missing_rankings
```

Accounting skips positions where entry or exit price is `0`, missing, or
non-finite. This is required because `0` is the missing OHLCV sentinel.

### Metrics And Leaderboard

Metrics are computed from `accounting/daily_pnl/*.csv`.

Outputs:

```text
accounting/latest_metrics.csv
accounting/metrics/<YYYYMMDD>.csv
leaderboard/leaderboard.csv
leaderboard/leaderboard.md
leaderboard/leaderboard.html
```

Metrics include:

- Sharpe;
- cumulative PnL;
- max drawdown;
- win rate;
- average daily PnL;
- number of scored days.

Important modules:

- `agentstockbenchmark.stage3.portfolio`
- `agentstockbenchmark.stage3.accounting`
- `agentstockbenchmark.stage3.metrics`
- `agentstockbenchmark.stage3.leaderboard`

## Daily Production Workflow

The top-level `daily-run` command executes:

1. download universe;
2. download daily CSV;
3. merge daily CSVs into parquets;
4. verify merge;
5. generate rankings for selected or active strategies;
6. build portfolios from rankings and universe;
7. update accounting for scoreable portfolios;
8. rebuild metrics;
9. rebuild leaderboard;
10. write strategy, run, artifact, and audit manifests.

The workflow is implemented in `agentstockbenchmark.workflow`.

Idempotency:

- default behavior skips existing ranking and portfolio artifacts where the
  underlying stage supports skipping;
- `--overwrite` must be explicit to replace artifacts;
- `resume` is an idempotent re-entry point for a date;
- `backfill` runs selected boundaries across a date range.

Network access:

- `download-universe` reads Wikipedia S&P 500 constituents;
- `download-daily-csv` uses `yfinance`;
- tests and dry-runs avoid network calls.

## Backfill And Recovery Boundaries

Backfill steps:

```text
data
rankings
portfolios
accounting
all
```

The boundaries match the artifact graph:

- `data`: `data/universe`, `data/raw/daily`, `data/parquet`;
- `rankings`: frozen strategy rankings;
- `portfolios`: frozen accounting portfolios;
- `accounting`: daily PnL, metrics, leaderboard;
- `all`: daily production workflow for each date.

Backfill defaults are conservative. Use `--overwrite` only when intentionally
replacing artifacts.

## Research Workflow

Research commands are deliberately isolated under:

```text
AgentStockBenchmarkResults/research/<prompt_id>/<run_id>/
```

Research can:

- create a generation workspace with the official prompt and reference prompts;
- backtest strategies into a research namespace;
- summarize a research run;
- promote one strategy into live `strategies/` only when explicitly requested.

Generated research strategies should be placed under:

```text
AgentStockBenchmarkResults/research/<prompt_id>/<run_id>/strategies/<prompt_id>/<strategy_slug>/strategy.py
```

`research backtest` uses that run-local strategy root when it contains strategy
files. If not, it can read the live strategy directory for comparison, but still
writes all rankings, portfolios, and accounting under the research run directory.
`research promote` never falls back to live strategies; promotion requires a
strategy file produced by the research run.

Research commands must not write live production paths:

```text
rankings/
portfolios/
accounting/
```

under the root result repository. They may write those same relative paths only
inside `research/<prompt_id>/<run_id>/`.

## Audit Design

Audit is implemented in `agentstockbenchmark.audit`.

Audit checks:

- dated universe file exists and is non-empty;
- raw daily CSV exists and has expected schema;
- raw daily CSV date values are canonical `YYYYMMDD`;
- required parquet files exist;
- daily CSV values were merged into parquets correctly;
- null daily CSV values are encoded as `0`;
- ranking schemas and rank contiguity;
- portfolio schemas;
- portfolio ticker set equals the dated universe;
- portfolios are dollar neutral;
- portfolio order and missing-name placement match the ranking and universe;
- accounting rows use expected entry and exit dates when returns are scoreable;
- manifest checksums still match files where artifact manifests exist.

Audit output:

```text
manifests/audits/<YYYYMMDD>.json
```

Publish requires a passed audit manifest.

## Manifests

Manifest outputs:

```text
manifests/strategies.json
manifests/runs/<YYYYMMDD>.json
manifests/artifacts/<YYYYMMDD>.json
manifests/audits/<YYYYMMDD>.json
manifests/published/<YYYYMMDD>.json
```

`strategies.json` records known strategy submissions and hashes.

`runs/<date>.json` records daily workflow steps, status, timestamps, selected
prompt or strategy filters, and error text on failure.

`artifacts/<date>.json` records paths, sizes, and SHA-256 checksums for
date-scoped artifacts such as dated raw data, rankings, portfolios, and dated
metrics snapshots. It intentionally excludes mutable aggregate outputs such as
`accounting/daily_pnl/*.csv`, `accounting/latest_metrics.csv`, and
`leaderboard/*`, because those files change as later dates are appended.

`audits/<date>.json` records audit status, failures, warnings, and counts.

`published/<date>.json` is written by the result package after audit-gated
publishing.

## Publish Design

Publish lives in `AgentStockBenchmarkResults` because it is result-facing:

```text
agentstockbenchmark_results.publish
```

Publish requires:

```text
manifests/audits/<YYYYMMDD>.json
```

with status `PASS`. It then renders public leaderboard artifacts. Optional Git
push is best-effort and reports `MANUAL_REQUIRED` on failure.

## Failure Model

Failures are expected and should be visible.

Examples:

- a strategy syntax error should show up in `stage1 validate-strategies`;
- a strategy runtime error should show up in ranking generation status;
- missing data should fail merge verification or audit;
- a non-neutral portfolio should fail audit;
- unscoreable dates without t+2 close prices should not produce accounting rows
  and should surface as audit warnings rather than fabricated returns.

Do not hide agent strategy failures by default. This project judges coding agent
submissions, so invalid code is a meaningful benchmark outcome.

## Testing Policy

The local test suite is designed to run directly with Python and does not depend
on `pytest` being installed.

The direct tests cover:

- date helper parsing and canonical output;
- merge verification;
- null OHLCV encoding as `0`;
- ranking rank order and stable ties;
- snapshot missing-value handling;
- portfolio universe filtering and missing-name insertion;
- accounting skip behavior for `0` prices;
- daily-run dry-run planning;
- fake-source daily production path;
- research namespace isolation.

Cannot be fully tested locally without external state:

- real S&P 500 universe download;
- real Yahoo OHLCV download;
- actual GitHub push.

For those paths, the CLI has clear failure messages and dry/fake-source tests
exercise the rest of the pipeline.

## Important Invariants

- Persisted benchmark dates are `YYYYMMDD`.
- Stage 2 rankings are frozen before Stage 3 portfolios.
- Stage 3 never calls strategy code.
- Research artifacts stay under `research/<prompt_id>/<run_id>/`.
- `0` means missing OHLCV in strategy-facing data and derived parquets.
- Atomic writes are used for production artifacts.
- Cached strategy migration is one-way and should preserve agent mistakes.
- Publish requires a passed audit.
