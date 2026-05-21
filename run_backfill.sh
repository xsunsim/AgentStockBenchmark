#!/bin/bash
export PYTHONPATH=AgentStockBenchmark/src

# Results repo path
RESULTS_REPO=AgentStockBenchmarkResults

# Run the backfill until today (2026-05-20)
# This script automatically identifies valid trading dates from the price data.
# 
# Now that we have historical data from 2025-01-01, we can support 
# strategies requiring up to 252 days of history starting from roughly 2026-01-01.

echo "Starting full backfill (using cached historical data)..."

python3 -c '
import datetime as dt
from pathlib import Path
import pandas as pd
import sys, os

sys.path.append(os.path.join(os.getcwd(), "AgentStockBenchmark/src"))
from agentstockbenchmark.workflow import run_daily

results_repo = Path("AgentStockBenchmarkResults")
close_path = results_repo / "data" / "parquet" / "close.parquet"

if not close_path.exists():
    print(f"Error: {close_path} not found.")
    sys.exit(1)

close = pd.read_parquet(close_path)
trading_dates = sorted(set(close.index.date))

# Start backfill from 2026-04-01 to give all models enough history
start_date = dt.date(2026, 4, 1)
end_date = dt.date(2026, 5, 20)

for day in trading_dates:
    if start_date <= day <= end_date:
        print(f"\n>>> PROCESSING DATE: {day} <<<")
        try:
            # skip_download=True uses our newly seeded historical data
            run_daily(day, results_repo=results_repo, overwrite=True, skip_download=True)
        except Exception as e:
            print(f"FAILED {day}: {e}")

print("\nBackfill complete.")
'
