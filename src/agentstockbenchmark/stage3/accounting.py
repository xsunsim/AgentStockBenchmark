from __future__ import annotations

import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd

from agentstockbenchmark.dates import date_id, parse_date, parse_date_id
from agentstockbenchmark.io import atomic_write_csv
from agentstockbenchmark.settings import DEFAULT_RESULTS_REPO
from agentstockbenchmark.stage3.portfolio import build_portfolios_for_date


PNL_DATE_COLUMNS = ("ranking_date", "entry_date", "exit_date")


def update_accounting(
    results_repo: Path = DEFAULT_RESULTS_REPO,
    data_dir: Path | None = None,
    ranking_date: dt.date | None = None,
    through: dt.date | None = None,
    strict_universe: bool = False,
    rebuild_portfolios: bool = False,
) -> dict[str, int]:
    if data_dir is None:
        data_dir = results_repo / "data" / "parquet"

    close = pd.read_parquet(data_dir / "close.parquet")
    close.index = pd.to_datetime(close.index)
    all_dates = trading_dates(close.index)

    portfolio_root = results_repo / "portfolios"
    ranking_root = results_repo / "rankings"
    pnl_dir = results_repo / "accounting" / "daily_pnl"
    pnl_dir.mkdir(parents=True, exist_ok=True)

    if ranking_date:
        dates = [ranking_date]
    else:
        source_root = ranking_root if rebuild_portfolios else portfolio_root
        if not source_root.exists():
            return {}
        dates = sorted(
            parse_date_id(path.name)
            for path in source_root.iterdir()
            if path.is_dir() and path.name[:4].isdigit()
        )
        if through:
            dates = [date for date in dates if date <= through]

    rows_by_strategy: dict[str, list[dict]] = {}
    evaluated_by_date: dict[str, int] = {}
    for date in dates:
        if rebuild_portfolios or not (portfolio_root / date_id(date)).exists():
            build_portfolios_for_date(
                results_repo=results_repo,
                ranking_date=date,
                close=close,
                strict_universe=strict_universe,
                overwrite=rebuild_portfolios,
            )

        rows = evaluate_portfolio_date(
            ranking_date=date,
            portfolio_root=portfolio_root,
            close=close,
            all_dates=all_dates,
        )
        evaluated_by_date[date_id(date)] = len(rows)
        for row in rows:
            rows_by_strategy.setdefault(row["strategy_id"], []).append(row)

    for strategy_id, rows in rows_by_strategy.items():
        write_or_append_daily_pnl(pnl_dir / f"{strategy_id}.csv", rows)

    return evaluated_by_date


def evaluate_portfolio_date(
    ranking_date: dt.date,
    portfolio_root: Path,
    close: pd.DataFrame,
    all_dates: list[dt.date],
) -> list[dict]:
    try:
        entry_date, exit_date = next_two_trading_dates(all_dates, ranking_date)
    except ValueError:
        return []

    date_dir = portfolio_root / date_id(ranking_date)
    if not date_dir.exists():
        return []

    try:
        entry_prices = close_row_for_date(close, entry_date)
        exit_prices = close_row_for_date(close, exit_date)
    except ValueError:
        return []

    rows = []
    for csv_path in sorted(date_dir.glob("*.csv")):
        portfolio_df = pd.read_csv(csv_path)
        if portfolio_df.empty:
            continue

        strategy_id = str(portfolio_df["strategy_id"].iloc[0])
        total_pnl = 0.0
        long_pnl = 0.0
        short_pnl = 0.0
        n_positions = 0

        for _, row in portfolio_df.iterrows():
            ticker = row["ticker"]
            position = float(row["position_dollars"])
            if ticker not in entry_prices or ticker not in exit_prices:
                continue
            entry_price = entry_prices[ticker]
            exit_price = exit_prices[ticker]
            if (
                entry_price > 0
                and exit_price > 0
                and np.isfinite(entry_price)
                and np.isfinite(exit_price)
            ):
                pnl = position * (exit_price / entry_price - 1.0)
                total_pnl += pnl
                if position > 0:
                    long_pnl += pnl
                else:
                    short_pnl += pnl
                n_positions += 1

        rows.append(
            {
                "ranking_date": date_id(ranking_date),
                "entry_date": date_id(entry_date),
                "exit_date": date_id(exit_date),
                "strategy_id": strategy_id,
                "total_pnl": round(total_pnl, 2),
                "long_pnl": round(long_pnl, 2),
                "short_pnl": round(short_pnl, 2),
                "n_positions": n_positions,
                "n_portfolio_universe": int(
                    portfolio_df["n_portfolio_universe"].iloc[0]
                )
                if "n_portfolio_universe" in portfolio_df
                else n_positions,
                "n_ranked_in_universe": int(
                    portfolio_df["n_ranked_in_universe"].iloc[0]
                )
                if "n_ranked_in_universe" in portfolio_df
                else n_positions,
                "n_ranked_ignored": int(portfolio_df["n_ranked_ignored"].iloc[0])
                if "n_ranked_ignored" in portfolio_df
                else 0,
                "n_missing_rankings": int(portfolio_df["n_missing_rankings"].iloc[0])
                if "n_missing_rankings" in portfolio_df
                else 0,
            }
        )
    return rows


def write_or_append_daily_pnl(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    new_df = normalize_daily_pnl_dates(pd.DataFrame(rows))
    new_df = new_df.sort_values("ranking_date")
    if path.exists():
        existing = normalize_daily_pnl_dates(pd.read_csv(path))
        existing_dates = set(existing["ranking_date"])
        new_df = new_df[~new_df["ranking_date"].isin(existing_dates)]
        if new_df.empty:
            return
        combined = pd.concat([existing, new_df], ignore_index=True)
        combined = combined.sort_values("ranking_date").reset_index(drop=True)
    else:
        combined = new_df.reset_index(drop=True)
    atomic_write_csv(path, combined)


def normalize_daily_pnl_dates(frame: pd.DataFrame) -> pd.DataFrame:
    normalized = frame.copy()
    for column in PNL_DATE_COLUMNS:
        if column in normalized.columns:
            normalized[column] = normalized[column].map(normalize_date_cell)
    return normalized


def normalize_date_cell(value) -> str:
    if pd.isna(value):
        return ""
    if isinstance(value, float) and value.is_integer():
        return f"{int(value):08d}"
    text = str(value).strip()
    if not text:
        return ""
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    return date_id(parse_date(text))

def trading_dates(index_or_dates) -> list[dt.date]:
    return sorted({_to_date(value) for value in index_or_dates})


def next_two_trading_dates(
    ordered_dates: list[dt.date],
    ranking_date: dt.date,
) -> tuple[dt.date, dt.date]:
    ordered = sorted(ordered_dates)
    try:
        idx = ordered.index(ranking_date)
    except ValueError as exc:
        raise ValueError(f"ranking_date {ranking_date} is not a trading date") from exc
    if idx + 2 >= len(ordered):
        raise ValueError(f"ranking_date {ranking_date} has no realized exit date")
    return ordered[idx + 1], ordered[idx + 2]


def close_row_for_date(close: pd.DataFrame, date: dt.date) -> pd.Series:
    matches = close.loc[close.index.date == date]
    if matches.empty:
        raise ValueError(f"date {date} not found in close table")
    return matches.iloc[0]


def _to_date(value) -> dt.date:
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    return pd.Timestamp(value).date()
