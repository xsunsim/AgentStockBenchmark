from __future__ import annotations

import datetime as dt
import math
from pathlib import Path

import pandas as pd

from agentstockbenchmark.dates import date_id
from agentstockbenchmark.io import atomic_write_csv, atomic_write_json
from agentstockbenchmark.settings import (
    DEFAULT_RESULTS_REPO,
    MIN_HISTORY_DAYS,
    STRATEGIES_DIR,
)
from agentstockbenchmark.stage1.strategies import (
    StrategyRef,
    file_sha256,
    find_strategy,
    list_strategies,
    load_strategy,
)
from agentstockbenchmark.stage2.market_data import load_ohlcv_tables


def generate_rankings(
    start: dt.date,
    end: dt.date,
    data_dir: Path,
    results_repo: Path = DEFAULT_RESULTS_REPO,
    prompt_id: str | None = None,
    strategy_selector: str | None = None,
    strategies_dir: Path = STRATEGIES_DIR,
    overwrite: bool = False,
) -> dict[str, dict[str, str]]:
    tables = load_ohlcv_tables(data_dir)
    all_dates = trading_dates(tables["close"].index)
    ranking_dates = [date for date in all_dates if start <= date <= end]

    if strategy_selector:
        strategies = [
            find_strategy(
                strategy_selector,
                strategies_dir=strategies_dir,
                prompt_id=prompt_id,
            )
        ]
    else:
        strategies = list_strategies(strategies_dir=strategies_dir, prompt_id=prompt_id)

    if not strategies:
        raise ValueError("no strategies found")

    report: dict[str, dict[str, str]] = {}
    for ranking_date in ranking_dates:
        report[date_id(ranking_date)] = generate_rankings_for_date(
            ranking_date=ranking_date,
            tables=tables,
            all_dates=all_dates,
            strategies=strategies,
            results_repo=results_repo,
            overwrite=overwrite,
        )
    return report


def generate_rankings_for_date(
    ranking_date: dt.date,
    tables: dict[str, pd.DataFrame],
    all_dates: list[dt.date],
    strategies: list[StrategyRef],
    results_repo: Path,
    overwrite: bool = False,
) -> dict[str, str]:
    out_dir = results_repo / "rankings" / date_id(ranking_date)
    out_dir.mkdir(parents=True, exist_ok=True)

    tickers = list(tables["close"].columns)
    snapshot = build_snapshot(tables, ranking_date, tickers)
    try:
        entry_date, exit_date = next_two_trading_dates(all_dates, ranking_date)
    except ValueError:
        entry_date = exit_date = None

    report: dict[str, str] = {}
    for ref in strategies:
        csv_path = out_dir / f"{ref.strategy_id}.csv"
        meta_path = out_dir / f"{ref.strategy_id}.meta.json"
        if csv_path.exists() and not overwrite:
            report[ref.strategy_id] = "skipped"
            continue

        try:
            predict = load_strategy(ref.path)
            raw_scores = predict(snapshot)
            scores = validate_strategy_scores(raw_scores)
            ranked = scores_to_ranked_rows(scores)
            if not ranked:
                report[ref.strategy_id] = "error:no_rankings"
                continue

            rows = [
                {
                    "ranking_date": date_id(ranking_date),
                    "prompt_id": ref.prompt_id,
                    "strategy_slug": ref.strategy_slug,
                    "strategy_id": ref.strategy_id,
                    "ticker": row["ticker"],
                    "score": round(row["score"], 8),
                    "strategy_rank": row["strategy_rank"],
                }
                for row in ranked
            ]
            atomic_write_csv(csv_path, pd.DataFrame(rows))

            meta = {
                "schema_version": 1,
                "artifact_type": "ranking",
                "ranking_date": date_id(ranking_date),
                "entry_date": date_id(entry_date) if entry_date else None,
                "exit_date": date_id(exit_date) if exit_date else None,
                "prompt_id": ref.prompt_id,
                "strategy_slug": ref.strategy_slug,
                "strategy_id": ref.strategy_id,
                "strategy_sha256": file_sha256(ref.path),
                "n_input_tickers": len(snapshot),
                "n_scores": len(scores),
                "n_ranked": len(ranked),
                "status": "PASS",
            }
            atomic_write_json(meta_path, meta)
            report[ref.strategy_id] = "PASS"
        except Exception as exc:
            report[ref.strategy_id] = f"error:{exc}"

    atomic_write_json(out_dir / "run_report.json", report)
    return report


def build_snapshot(
    tables: dict[str, pd.DataFrame],
    ranking_date: dt.date,
    tickers: list[str],
    min_history: int = MIN_HISTORY_DAYS,
) -> dict[str, pd.DataFrame]:
    """Build strategy inputs, encoding missing OHLCV values as 0.

    Market-data parquets keep true NaNs. The strategy-facing API uses 0 as the
    missing-value sentinel because valid adjusted prices and volumes should be
    positive for traded S&P 500 constituents.
    """
    close = tables["close"]
    mask = close.index.date <= ranking_date
    snapshot: dict[str, pd.DataFrame] = {}

    for ticker in tickers:
        try:
            frame = pd.DataFrame(
                {
                    "Date": close.index[mask],
                    "open": tables["open"][ticker].to_numpy()[mask],
                    "high": tables["high"][ticker].to_numpy()[mask],
                    "low": tables["low"][ticker].to_numpy()[mask],
                    "close": close[ticker].to_numpy()[mask],
                    "volume": tables["volume"][ticker].to_numpy()[mask],
                }
            )
        except KeyError:
            continue

        value_cols = ["open", "high", "low", "close", "volume"]
        numeric_values = frame[value_cols].apply(pd.to_numeric, errors="coerce")
        has_any_data = bool((numeric_values > 0).any().any())
        if len(frame) >= min_history and has_any_data:
            snapshot[ticker] = frame.fillna(0).reset_index(drop=True)
    return snapshot


def validate_strategy_scores(output, min_count: int = 2) -> dict[str, float]:
    if not isinstance(output, dict):
        raise TypeError(f"generate_signal must return dict, got {type(output)}")

    scores: dict[str, float] = {}
    for ticker, score in output.items():
        if not isinstance(ticker, str):
            raise TypeError(f"score key must be str, got {type(ticker)}")
        try:
            value = float(score)
        except (TypeError, ValueError) as exc:
            raise TypeError(f"score for {ticker} is not numeric: {score!r}") from exc
        if math.isfinite(value):
            scores[ticker] = value

    if len(scores) < min_count:
        raise ValueError(f"expected at least {min_count} finite scores, got {len(scores)}")
    return scores


def scores_to_ranked_rows(scores: dict[str, float]) -> list[dict]:
    ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    return [
        {"ticker": ticker, "score": score, "strategy_rank": idx + 1}
        for idx, (ticker, score) in enumerate(ranked)
    ]


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


def _to_date(value) -> dt.date:
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    return pd.Timestamp(value).date()
