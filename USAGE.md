# AgentStockBenchmark Usage

[中文版本](./USAGE_CN.md)

This is the command cookbook for maintainers and coding agents. Commands are
shown with `PYTHONPATH=src python -m ...` so they work from an uninstalled local
checkout. If the package is installed, replace that prefix with
`agentstockbenchmark` or `agentstockbenchmark-results`.

Use compact dates such as `20260519`. Most commands also accept ISO dates such
as `2026-05-19`, but new artifacts are written as `YYYYMMDD`.

## Environment

Benchmark engine:

```bash
cd AgentStockBenchmark
export PYTHONPATH=src
python -m agentstockbenchmark --help
```

Result tooling:

```bash
cd AgentStockBenchmarkResults
export PYTHONPATH=src
python -m agentstockbenchmark_results --help
```

Default result repository:

```text
AgentStockBenchmarkResults
```

Default market data parquets:

```text
AgentStockBenchmarkResults/data/parquet
```

## Daily Production

Run the full daily workflow:

```bash
cd AgentStockBenchmark
PYTHONPATH=src python -m agentstockbenchmark daily-run \
  --date 20260519 \
  --results-repo ../AgentStockBenchmarkResults
```

Run only one strategy:

```bash
PYTHONPATH=src python -m agentstockbenchmark daily-run \
  --date 20260519 \
  --results-repo ../AgentStockBenchmarkResults \
  --strategy 20260519__OpenAI__O3__LinearNeutral
```

Run strategies for one prompt ID:

```bash
PYTHONPATH=src python -m agentstockbenchmark daily-run \
  --date 20260519 \
  --results-repo ../AgentStockBenchmarkResults \
  --prompt-id 20260519
```

Plan a run without writing artifacts or downloading data:

```bash
PYTHONPATH=src python -m agentstockbenchmark daily-run \
  --date 20260519 \
  --results-repo ../AgentStockBenchmarkResults \
  --skip-download \
  --dry-run
```

Use existing `data/raw/daily/<date>.csv` and `data/universe/<date>.txt` instead
of downloading:

```bash
PYTHONPATH=src python -m agentstockbenchmark daily-run \
  --date 20260519 \
  --results-repo ../AgentStockBenchmarkResults \
  --skip-download
```

Overwrite existing artifacts intentionally:

```bash
PYTHONPATH=src python -m agentstockbenchmark daily-run \
  --date 20260519 \
  --results-repo ../AgentStockBenchmarkResults \
  --overwrite
```

Use `--overwrite` sparingly. Existing rankings and portfolios are frozen
benchmark artifacts.

## Resume A Failed Or Partial Day

Resume is idempotent and skips existing artifacts where supported:

```bash
cd AgentStockBenchmark
PYTHONPATH=src python -m agentstockbenchmark resume \
  --date 20260519 \
  --results-repo ../AgentStockBenchmarkResults
```

Resume with a strategy filter:

```bash
PYTHONPATH=src python -m agentstockbenchmark resume \
  --date 20260519 \
  --results-repo ../AgentStockBenchmarkResults \
  --strategy 20260519__OpenAI__O3__LinearNeutral
```

Dry-run resume planning:

```bash
PYTHONPATH=src python -m agentstockbenchmark resume \
  --date 20260519 \
  --results-repo ../AgentStockBenchmarkResults \
  --dry-run
```

## Backfill

Backfill all stages:

```bash
cd AgentStockBenchmark
PYTHONPATH=src python -m agentstockbenchmark backfill \
  --start 20260501 \
  --end 20260519 \
  --step all \
  --results-repo ../AgentStockBenchmarkResults
```

Backfill only data:

```bash
PYTHONPATH=src python -m agentstockbenchmark backfill \
  --start 20260501 \
  --end 20260519 \
  --step data \
  --results-repo ../AgentStockBenchmarkResults
```

Backfill only rankings:

```bash
PYTHONPATH=src python -m agentstockbenchmark backfill \
  --start 20260501 \
  --end 20260519 \
  --step rankings \
  --data-dir ../AgentStockBenchmarkResults/data/parquet \
  --results-repo ../AgentStockBenchmarkResults
```

Backfill rankings for one prompt:

```bash
PYTHONPATH=src python -m agentstockbenchmark backfill \
  --start 20260501 \
  --end 20260519 \
  --step rankings \
  --prompt-id 20260519 \
  --data-dir ../AgentStockBenchmarkResults/data/parquet \
  --results-repo ../AgentStockBenchmarkResults
```

Backfill rankings for one strategy:

```bash
PYTHONPATH=src python -m agentstockbenchmark backfill \
  --start 20260501 \
  --end 20260519 \
  --step rankings \
  --strategy 20260519__OpenAI__O3__LinearNeutral \
  --data-dir ../AgentStockBenchmarkResults/data/parquet \
  --results-repo ../AgentStockBenchmarkResults
```

Backfill only portfolios:

```bash
PYTHONPATH=src python -m agentstockbenchmark backfill \
  --start 20260501 \
  --end 20260519 \
  --step portfolios \
  --data-dir ../AgentStockBenchmarkResults/data/parquet \
  --results-repo ../AgentStockBenchmarkResults
```

Backfill only accounting, metrics, and leaderboard:

```bash
PYTHONPATH=src python -m agentstockbenchmark backfill \
  --start 20260501 \
  --end 20260519 \
  --step accounting \
  --data-dir ../AgentStockBenchmarkResults/data/parquet \
  --results-repo ../AgentStockBenchmarkResults
```

Plan a backfill:

```bash
PYTHONPATH=src python -m agentstockbenchmark backfill \
  --start 20260501 \
  --end 20260519 \
  --step all \
  --results-repo ../AgentStockBenchmarkResults \
  --dry-run
```

## Stage 1: Prompts And Strategies

List prompts:

```bash
cd AgentStockBenchmark
PYTHONPATH=src python -m agentstockbenchmark stage1 list-prompts
```

List strategies for a prompt:

```bash
PYTHONPATH=src python -m agentstockbenchmark stage1 list-strategies \
  --prompt-id 20260519
```

Validate strategy imports for a prompt:

```bash
PYTHONPATH=src python -m agentstockbenchmark stage1 validate-strategies \
  --prompt-id 20260519
```

Validate migrated v5 strategies:

```bash
PYTHONPATH=src python -m agentstockbenchmark stage1 validate-strategies \
  --prompt-id 20260517
```

Validate migrated v13 strategies:

```bash
PYTHONPATH=src python -m agentstockbenchmark stage1 validate-strategies \
```

Copy a prompt into the dated prompt layout:

```bash
PYTHONPATH=src python -m agentstockbenchmark stage1 copy-prompt \
  --source-prompt ~/bm/PROMPT_V12.md \
  --prompt-id 20260519
```

Overwrite an existing prompt intentionally:

```bash
PYTHONPATH=src python -m agentstockbenchmark stage1 copy-prompt \
  --source-prompt ~/bm/PROMPT_V12.md \
  --prompt-id 20260519 \
  --overwrite
```

## Cached Strategy Migration

Migrate cached v5 strategies:

```bash
cd AgentStockBenchmark
PYTHONPATH=src python -m agentstockbenchmark stage1 migrate-cached-strategies \
  --source-dir ~/strategies \
  --prompt-id 20260517 \
  --glob '*_202605'
```

Migrate cached v13 strategies:

```bash
PYTHONPATH=src python -m agentstockbenchmark stage1 migrate-cached-strategies \
  --source-dir ~/bm/strategies \
  --glob '*_202605'
```

Re-copy one cached strategy exactly from source:

```bash
PYTHONPATH=src python -m agentstockbenchmark stage1 migrate-cached-strategies \
  --source-dir ~/bm/strategies \
  --glob 'Google__Gemini2_5Flash__LinearNeutral_202605' \
  --overwrite
```

Do not repair invalid migrated strategy code unless explicitly requested. This
benchmark judges coding agent submissions, so syntax errors and runtime errors
are meaningful outcomes.

## Stage 2: Data

Build parquets from the seeded wide raw CSV:

```bash
cd AgentStockBenchmark
PYTHONPATH=src python -m agentstockbenchmark stage2 build-data \
  --raw-csv ../AgentStockBenchmarkResults/data/raw/sp500_ohlcv.csv \
  --output-dir ../AgentStockBenchmarkResults/data/parquet
```

Download only the S&P 500 universe:

```bash
PYTHONPATH=src python -m agentstockbenchmark stage2 download-universe \
  --date 20260519 \
  --results-repo ../AgentStockBenchmarkResults
```

Download one daily OHLCV CSV and universe:

```bash
PYTHONPATH=src python -m agentstockbenchmark stage2 download-daily-csv \
  --date 20260519 \
  --results-repo ../AgentStockBenchmarkResults
```

Merge downloaded daily CSVs into parquets:

```bash
PYTHONPATH=src python -m agentstockbenchmark stage2 merge-data \
  --results-repo ../AgentStockBenchmarkResults \
  --output-dir ../AgentStockBenchmarkResults/data/parquet
```

Verify one daily CSV was merged into parquets:

```bash
PYTHONPATH=src python -m agentstockbenchmark stage2 verify-merge \
  --date 20260519 \
  --results-repo ../AgentStockBenchmarkResults \
  --data-dir ../AgentStockBenchmarkResults/data/parquet
```

Download, merge, and verify data for one date:

```bash
PYTHONPATH=src python -m agentstockbenchmark stage2 refresh-data \
  --date 20260519 \
  --results-repo ../AgentStockBenchmarkResults \
  --output-dir ../AgentStockBenchmarkResults/data/parquet
```

Refresh data and replace existing raw artifacts:

```bash
PYTHONPATH=src python -m agentstockbenchmark stage2 refresh-data \
  --date 20260519 \
  --results-repo ../AgentStockBenchmarkResults \
  --output-dir ../AgentStockBenchmarkResults/data/parquet \
  --overwrite
```

## Stage 2: Rankings

Generate rankings for one date:

```bash
cd AgentStockBenchmark
PYTHONPATH=src python -m agentstockbenchmark stage2 generate-rankings \
  --date 20260519 \
  --data-dir ../AgentStockBenchmarkResults/data/parquet \
  --results-repo ../AgentStockBenchmarkResults
```

Generate rankings for a date range:

```bash
PYTHONPATH=src python -m agentstockbenchmark stage2 generate-rankings \
  --start 20260501 \
  --end 20260519 \
  --data-dir ../AgentStockBenchmarkResults/data/parquet \
  --results-repo ../AgentStockBenchmarkResults
```

Generate rankings for one prompt:

```bash
PYTHONPATH=src python -m agentstockbenchmark stage2 generate-rankings \
  --date 20260519 \
  --prompt-id 20260519 \
  --data-dir ../AgentStockBenchmarkResults/data/parquet \
  --results-repo ../AgentStockBenchmarkResults
```

Generate rankings for one strategy:

```bash
PYTHONPATH=src python -m agentstockbenchmark stage2 generate-rankings \
  --date 20260519 \
  --prompt-id 20260519 \
  --strategy OpenAI__O3__LinearNeutral \
  --data-dir ../AgentStockBenchmarkResults/data/parquet \
  --results-repo ../AgentStockBenchmarkResults
```

Use a full strategy ID selector:

```bash
PYTHONPATH=src python -m agentstockbenchmark stage2 generate-rankings \
  --date 20260519 \
  --strategy 20260519__OpenAI__O3__LinearNeutral \
  --data-dir ../AgentStockBenchmarkResults/data/parquet \
  --results-repo ../AgentStockBenchmarkResults
```

Overwrite existing ranking artifacts intentionally:

```bash
PYTHONPATH=src python -m agentstockbenchmark stage2 generate-rankings \
  --date 20260519 \
  --prompt-id 20260519 \
  --data-dir ../AgentStockBenchmarkResults/data/parquet \
  --results-repo ../AgentStockBenchmarkResults \
  --overwrite
```

## Stage 3: Portfolios

Build portfolios for one ranking date:

```bash
cd AgentStockBenchmark
PYTHONPATH=src python -m agentstockbenchmark stage3 build-portfolios \
  --ranking-date 20260519 \
  --data-dir ../AgentStockBenchmarkResults/data/parquet \
  --results-repo ../AgentStockBenchmarkResults
```

Build portfolios through a date:

```bash
PYTHONPATH=src python -m agentstockbenchmark stage3 build-portfolios \
  --through 20260519 \
  --data-dir ../AgentStockBenchmarkResults/data/parquet \
  --results-repo ../AgentStockBenchmarkResults
```

Require exact dated universe files:

```bash
PYTHONPATH=src python -m agentstockbenchmark stage3 build-portfolios \
  --ranking-date 20260519 \
  --data-dir ../AgentStockBenchmarkResults/data/parquet \
  --results-repo ../AgentStockBenchmarkResults \
  --strict-universe
```

Overwrite existing portfolios intentionally:

```bash
PYTHONPATH=src python -m agentstockbenchmark stage3 build-portfolios \
  --ranking-date 20260519 \
  --data-dir ../AgentStockBenchmarkResults/data/parquet \
  --results-repo ../AgentStockBenchmarkResults \
  --overwrite
```

## Stage 3: Accounting

Update accounting for one ranking date:

```bash
cd AgentStockBenchmark
PYTHONPATH=src python -m agentstockbenchmark stage3 update-accounting \
  --ranking-date 20260519 \
  --data-dir ../AgentStockBenchmarkResults/data/parquet \
  --results-repo ../AgentStockBenchmarkResults
```

Update accounting through a date:

```bash
PYTHONPATH=src python -m agentstockbenchmark stage3 update-accounting \
  --through 20260519 \
  --data-dir ../AgentStockBenchmarkResults/data/parquet \
  --results-repo ../AgentStockBenchmarkResults
```

Rebuild portfolios before accounting:

```bash
PYTHONPATH=src python -m agentstockbenchmark stage3 update-accounting \
  --through 20260519 \
  --data-dir ../AgentStockBenchmarkResults/data/parquet \
  --results-repo ../AgentStockBenchmarkResults \
  --rebuild-portfolios
```

Require exact universe files while rebuilding:

```bash
PYTHONPATH=src python -m agentstockbenchmark stage3 update-accounting \
  --through 20260519 \
  --data-dir ../AgentStockBenchmarkResults/data/parquet \
  --results-repo ../AgentStockBenchmarkResults \
  --rebuild-portfolios \
  --strict-universe
```

## Stage 3: Metrics And Leaderboard

Build latest metrics:

```bash
cd AgentStockBenchmark
PYTHONPATH=src python -m agentstockbenchmark stage3 build-metrics \
  --results-repo ../AgentStockBenchmarkResults
```

Build metrics as of a date:

```bash
PYTHONPATH=src python -m agentstockbenchmark stage3 build-metrics \
  --as-of 20260519 \
  --results-repo ../AgentStockBenchmarkResults
```

Build leaderboard files:

```bash
PYTHONPATH=src python -m agentstockbenchmark stage3 build-leaderboard \
  --results-repo ../AgentStockBenchmarkResults
```

## Audit

Audit one date:

```bash
cd AgentStockBenchmark
PYTHONPATH=src python -m agentstockbenchmark audit \
  --date 20260519 \
  --results-repo ../AgentStockBenchmarkResults \
  --data-dir ../AgentStockBenchmarkResults/data/parquet
```

Audit output:

```text
AgentStockBenchmarkResults/manifests/audits/20260519.json
```

If audit fails, inspect the first failure printed by the CLI and the JSON
manifest for the full failure list.

## Repair Data

If a daily run was performed too early (resulting in incomplete data) or if
there was a network failure during download, use `repair-date` to force-refresh
market data and update all affected historical PnL:

```bash
cd AgentStockBenchmark
PYTHONPATH=src python -m agentstockbenchmark repair-date \
  --date 20260521 \
  --results-repo ../AgentStockBenchmarkResults
```

This command:
1.  **Force Refreshes Data**: Re-downloads the full market data for that date,
    overwriting any previous incomplete CSV.
2.  **Synchronizes Parquets**: Re-merges the repaired CSV into the global
    Parquet files.
3.  **Refreshes Accounting**: Recalculates PnL for all historical ranking dates
    that use this date as an entry or exit price.
4.  **Updates Leaderboard**: Regenerates the metrics and cumulative PnL chart.

## Publish

Publish is run from the result repository after audit passes:

```bash
cd AgentStockBenchmarkResults
PYTHONPATH=src python -m agentstockbenchmark_results publish \
  --date 20260519 \
  --results-repo .
```

Publish and attempt Git add, commit, and push:

```bash
PYTHONPATH=src python -m agentstockbenchmark_results publish \
  --date 20260519 \
  --results-repo . \
  --push
```

The Git push path is best-effort. If it returns `MANUAL_REQUIRED`, inspect the
result repository and push manually.

Render leaderboard without publish gating:

```bash
PYTHONPATH=src python -m agentstockbenchmark_results render-leaderboard \
  --results-repo .
```

## Research

Create a strategy-generation workspace:

```bash
cd AgentStockBenchmark
PYTHONPATH=src python -m agentstockbenchmark research generate-strategies \
  --prompt-id 20260519 \
  --results-repo ../AgentStockBenchmarkResults
```

Put generated strategy files in the workspace layout:

```text
AgentStockBenchmarkResults/research/<prompt_id>/<run_id>/strategies/<prompt_id>/<strategy_slug>/strategy.py
```

Use a specific research run ID:

```bash
PYTHONPATH=src python -m agentstockbenchmark research generate-strategies \
  --prompt-id 20260519 \
  --run-id 20260519T120000Z \
  --results-repo ../AgentStockBenchmarkResults
```

Backtest a research run:

```bash
PYTHONPATH=src python -m agentstockbenchmark research backtest \
  --prompt-id 20260519 \
  --run-id 20260519T120000Z \
  --start 20260501 \
  --end 20260519 \
  --data-dir ../AgentStockBenchmarkResults/data/parquet \
  --results-repo ../AgentStockBenchmarkResults
```

Backtest one strategy selector:

```bash
PYTHONPATH=src python -m agentstockbenchmark research backtest \
  --prompt-id 20260519 \
  --run-id 20260519T120000Z \
  --strategy OpenAI__O3__LinearNeutral \
  --start 20260501 \
  --end 20260519 \
  --data-dir ../AgentStockBenchmarkResults/data/parquet \
  --results-repo ../AgentStockBenchmarkResults
```

Backtest strategies from an explicit strategy directory instead of the run-local
workspace or live strategy directory:

```bash
PYTHONPATH=src python -m agentstockbenchmark research backtest \
  --prompt-id 20260519 \
  --run-id 20260519T120000Z \
  --strategies-dir AgentStockBenchmark/strategies \
  --start 20260501 \
  --end 20260519 \
  --data-dir ../AgentStockBenchmarkResults/data/parquet \
  --results-repo ../AgentStockBenchmarkResults
```

Analyze a research run:

```bash
PYTHONPATH=src python -m agentstockbenchmark research analyze \
  --run-id 20260519T120000Z \
  --results-repo ../AgentStockBenchmarkResults
```

Promote a strategy explicitly:

```bash
PYTHONPATH=src python -m agentstockbenchmark research promote \
  --run-id 20260519T120000Z \
  --strategy-id 20260519__OpenAI__O3__LinearNeutral \
  --results-repo ../AgentStockBenchmarkResults
```

Research artifacts stay under:

```text
AgentStockBenchmarkResults/research/<prompt_id>/<run_id>/
```

They do not contaminate live production paths unless `research promote` is run.
Promotion requires the strategy file to exist inside the research run; it does
not silently copy a live strategy.

## Manifests

Daily run manifest:

```text
AgentStockBenchmarkResults/manifests/runs/20260519.json
```

Artifact checksum manifest:

```text
AgentStockBenchmarkResults/manifests/artifacts/20260519.json
```

This manifest is date-scoped. It does not checksum mutable aggregate outputs
such as `accounting/daily_pnl/*.csv`, `accounting/latest_metrics.csv`, or
`leaderboard/*`.

Strategy manifest:

```text
AgentStockBenchmarkResults/manifests/strategies.json
```

Audit manifest:

```text
AgentStockBenchmarkResults/manifests/audits/20260519.json
```

Publish manifest:

```text
AgentStockBenchmarkResults/manifests/published/20260519.json
```

## Verification Commands

Compile benchmark engine:

```bash
cd AgentStockBenchmark
PYTHONPATH=src python -m compileall src/agentstockbenchmark
```

Compile result tooling:

```bash
cd AgentStockBenchmarkResults
PYTHONPATH=src python -m compileall src/agentstockbenchmark_results
```

Run direct tests without `pytest`:

```bash
cd AgentStockBenchmark
PYTHONPATH=src python - <<'PY'
import importlib

modules = [
    "tests.test_stage1_migration",
    "tests.test_stage2_market_data",
    "tests.test_stage2_rankings",
    "tests.test_stage3_metrics",
    "tests.test_stage3_portfolio",
    "tests.test_workflow_support",
]

count = 0
for name in modules:
    mod = importlib.import_module(name)
    for attr in sorted(dir(mod)):
        if attr.startswith("test_"):
            fn = getattr(mod, attr)
            if callable(fn):
                fn()
                count += 1
print(f"{count} direct tests passed")
PY
```

Run the workflow support tests directly:

```bash
cd AgentStockBenchmark
PYTHONPATH=src python tests/test_workflow_support.py
```

Smoke test daily-run planning:

```bash
cd AgentStockBenchmark
PYTHONPATH=src python -m agentstockbenchmark daily-run \
  --date 20260519 \
  --results-repo /tmp/asb-smoke \
  --skip-download \
  --dry-run
```

Smoke test result publish without Git push:

```bash
tmp=$(mktemp -d)
mkdir -p "$tmp/manifests/audits" "$tmp/accounting"
printf '{"status":"PASS"}\n' > "$tmp/manifests/audits/20260519.json"
printf 'strategy_id,sharpe,cumulative_pnl,max_drawdown,win_rate,n_days\nS,1.0,2.0,-1.0,0.5,2\n' \
  > "$tmp/accounting/latest_metrics.csv"
cd AgentStockBenchmarkResults
PYTHONPATH=src python -m agentstockbenchmark_results publish \
  --date 20260519 \
  --results-repo "$tmp"
```

## Common Problems

No `pytest` installed:

Use the direct Python test command above.

Strategy import fails:

Run:

```bash
PYTHONPATH=src python -m agentstockbenchmark stage1 validate-strategies \
  --prompt-id <prompt_id>
```

If the failure is in submitted strategy code, preserve it unless the benchmark
owner explicitly asks for a repair.

No accounting row appears:

Check that the close parquet has both t+1 and t+2 trading dates after the
ranking date. The benchmark does not fabricate returns for unscoreable dates.

Audit fails on missing universe:

Create or download:

```text
AgentStockBenchmarkResults/data/universe/<YYYYMMDD>.txt
```

Audit fails on merge verification:

Check:

```text
AgentStockBenchmarkResults/data/raw/daily/<YYYYMMDD>.csv
AgentStockBenchmarkResults/data/parquet/*.parquet
```

If the data is incomplete (e.g. downloaded too early), use `repair-date`.
Otherwise, re-run the manual merge:

```bash
PYTHONPATH=src python -m agentstockbenchmark stage2 merge-data \
  --results-repo ../AgentStockBenchmarkResults \
  --output-dir ../AgentStockBenchmarkResults/data/parquet
```

Publish refuses to run:

Run audit first and confirm:

```text
../AgentStockBenchmarkResults/manifests/audits/<YYYYMMDD>.json
```

has:

```json
{"status": "PASS"}
```
```
