from __future__ import annotations

import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd

from agentstockbenchmark.dates import date_id
from agentstockbenchmark.io import atomic_write_csv
from agentstockbenchmark.settings import DEFAULT_RESULTS_REPO


def build_metrics(
    results_repo: Path = DEFAULT_RESULTS_REPO,
    as_of: dt.date | None = None,
) -> pd.DataFrame:
    pnl_dir = results_repo / "accounting" / "daily_pnl"
    metrics_dir = results_repo / "accounting" / "metrics"
    metrics_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    if not pnl_dir.exists():
        return pd.DataFrame()

    for pnl_path in sorted(pnl_dir.glob("*.csv")):
        df = pd.read_csv(pnl_path)
        if df.empty:
            continue
        if as_of is not None:
            df = df[df["ranking_date"].astype(str) <= date_id(as_of)]
        if df.empty:
            continue

        metrics = compute_strategy_metrics(df["total_pnl"])
        metrics["strategy_id"] = pnl_path.stem
        rows.append(metrics)

    if not rows:
        return pd.DataFrame()

    result = pd.DataFrame(rows).sort_values("sharpe", ascending=False)
    
    # Calculate standardized PnL to allow fair comparison between models with different start dates
    # We normalize to the maximum n_days observed in the current set.
    max_days = result["n_days"].max() if not result.empty else 0
    result["standardized_pnl"] = round(result["avg_daily_pnl"] * max_days, 2)
    
    result = result.reset_index(drop=True)
    result = result[
        [
            "strategy_id",
            "sharpe",
            "standardized_pnl",
            "cumulative_pnl",
            "avg_daily_pnl",
            "max_drawdown",
            "win_rate",
            "n_days",
        ]
    ]

    latest_path = results_repo / "accounting" / "latest_metrics.csv"
    latest_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_csv(latest_path, result)

    if as_of is not None:
        atomic_write_csv(metrics_dir / f"{date_id(as_of)}.csv", result)
    return result


def compute_strategy_metrics(pnl_series: pd.Series) -> dict:
    pnl = pd.to_numeric(pnl_series, errors="coerce").dropna()
    if len(pnl) == 0:
        return _empty_metrics(0)
    if len(pnl) == 1:
        return {
            **_empty_metrics(1),
            "cumulative_pnl": round(float(pnl.iloc[0]), 2),
            "avg_daily_pnl": round(float(pnl.iloc[0]), 2),
            "win_rate": float(pnl.iloc[0] > 0),
        }

    cumulative = pnl.cumsum()
    drawdown = cumulative - cumulative.cummax()
    mean_daily = pnl.mean()
    std_daily = pnl.std()
    sharpe = mean_daily / std_daily * np.sqrt(252) if std_daily > 0 else 0.0

    return {
        "sharpe": round(float(sharpe), 3),
        "cumulative_pnl": round(float(cumulative.iloc[-1]), 2),
        "max_drawdown": round(float(drawdown.min()), 2),
        "win_rate": round(float((pnl > 0).mean()), 3),
        "avg_daily_pnl": round(float(mean_daily), 2),
        "n_days": int(len(pnl)),
    }


def _empty_metrics(n_days: int) -> dict:
    return {
        "sharpe": 0.0,
        "cumulative_pnl": 0.0,
        "max_drawdown": 0.0,
        "win_rate": 0.0,
        "avg_daily_pnl": 0.0,
        "n_days": n_days,
    }
