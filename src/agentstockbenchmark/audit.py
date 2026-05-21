from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pandas as pd

from agentstockbenchmark.dates import date_id
from agentstockbenchmark.io import atomic_write_json
from agentstockbenchmark.manifests import utc_now, verify_artifact_manifest
from agentstockbenchmark.settings import DEFAULT_RESULTS_REPO, OHLCV_FIELDS
from agentstockbenchmark.stage2.market_data import validate_daily_csv, verify_daily_merge
from agentstockbenchmark.stage2.rankings import next_two_trading_dates, trading_dates
from agentstockbenchmark.stage3.portfolio import build_portfolio_book
from agentstockbenchmark.universe import read_universe_file


RANKING_COLUMNS = {
    "ranking_date",
    "prompt_id",
    "strategy_slug",
    "strategy_id",
    "ticker",
    "score",
    "strategy_rank",
}
PORTFOLIO_COLUMNS = {
    "ranking_date",
    "strategy_id",
    "ticker",
    "score",
    "portfolio_rank",
    "position_dollars",
    "ranking_status",
    "strategy_rank",
    "portfolio_universe_source",
    "portfolio_universe_date",
    "n_portfolio_universe",
    "n_ranked_in_universe",
    "n_ranked_ignored",
    "n_missing_rankings",
}
PNL_COLUMNS = {
    "ranking_date",
    "entry_date",
    "exit_date",
    "strategy_id",
    "total_pnl",
    "long_pnl",
    "short_pnl",
    "n_positions",
}


def audit_date(
    run_date: dt.date,
    results_repo: Path = DEFAULT_RESULTS_REPO,
    data_dir: Path | None = None,
    write_manifest: bool = True,
) -> dict:
    if data_dir is None:
        data_dir = results_repo / "data" / "parquet"

    did = date_id(run_date)
    failures: list[str] = []
    warnings: list[str] = []

    universe_path = results_repo / "data" / "universe" / f"{did}.txt"
    raw_path = results_repo / "data" / "raw" / "daily" / f"{did}.csv"
    ranking_dir = results_repo / "rankings" / did
    portfolio_dir = results_repo / "portfolios" / did

    universe = _check_universe(universe_path, failures)
    _check_raw_daily(raw_path, did, failures)
    _check_parquets(data_dir, failures)
    _check_merge(results_repo, data_dir, run_date, failures)
    ranking_paths = _check_rankings(ranking_dir, did, failures)
    portfolio_paths = _check_portfolios(
        portfolio_dir,
        ranking_dir,
        universe,
        did,
        failures,
    )
    _check_accounting(
        results_repo=results_repo,
        data_dir=data_dir,
        run_date=run_date,
        strategy_ids=[path.stem for path in portfolio_paths],
        failures=failures,
        warnings=warnings,
    )

    failures.extend(verify_artifact_manifest(results_repo, run_date))

    payload = {
        "schema_version": 1,
        "audit_date": did,
        "generated_at_utc": utc_now(),
        "status": "PASS" if not failures else "FAIL",
        "failures": failures,
        "warnings": warnings,
        "counts": {
            "rankings": len(ranking_paths),
            "portfolios": len(portfolio_paths),
            "universe_tickers": len(universe),
        },
    }
    if write_manifest:
        path = results_repo / "manifests" / "audits" / f"{did}.json"
        atomic_write_json(path, payload)
    if failures:
        raise ValueError(
            f"audit failed for {did}: {len(failures)} issue(s); first: {failures[0]}"
        )
    return payload


def _check_universe(path: Path, failures: list[str]) -> list[str]:
    if not path.exists():
        failures.append(f"missing universe file: {path}")
        return []
    tickers = read_universe_file(path)
    if not tickers:
        failures.append(f"empty universe file: {path}")
    return tickers


def _check_raw_daily(path: Path, did: str, failures: list[str]) -> None:
    if not path.exists():
        failures.append(f"missing daily raw CSV: {path}")
        return
    try:
        frame = pd.read_csv(path)
        validate_daily_csv(frame, path)
        bad_dates = sorted(set(frame["date"].astype(str)) - {did})
        if bad_dates:
            failures.append(f"{path} has noncanonical date values: {bad_dates[:3]}")
    except Exception as exc:
        failures.append(f"invalid daily raw CSV {path}: {exc}")


def _check_parquets(data_dir: Path, failures: list[str]) -> None:
    for field in OHLCV_FIELDS:
        path = data_dir / f"{field}.parquet"
        if not path.exists():
            failures.append(f"missing parquet: {path}")


def _check_merge(
    results_repo: Path,
    data_dir: Path,
    run_date: dt.date,
    failures: list[str],
) -> None:
    try:
        verify_daily_merge(results_repo, data_dir, date=run_date)
    except Exception as exc:
        failures.append(f"merge verification failed: {exc}")


def _check_rankings(ranking_dir: Path, did: str, failures: list[str]) -> list[Path]:
    if not ranking_dir.exists():
        failures.append(f"missing ranking directory: {ranking_dir}")
        return []

    paths = sorted(path for path in ranking_dir.glob("*.csv") if path.is_file())
    if not paths:
        failures.append(f"no ranking CSVs in {ranking_dir}")
        return []

    for path in paths:
        try:
            frame = pd.read_csv(path)
            missing = RANKING_COLUMNS.difference(frame.columns)
            if missing:
                failures.append(f"{path} missing ranking columns: {sorted(missing)}")
                continue
            if set(frame["ranking_date"].astype(str)) != {did}:
                failures.append(f"{path} has noncanonical ranking_date values")
            if frame["ticker"].astype(str).duplicated().any():
                failures.append(f"{path} has duplicate ranking tickers")
            ranks = sorted(frame["strategy_rank"].astype(int).tolist())
            if ranks != list(range(1, len(ranks) + 1)):
                failures.append(f"{path} strategy_rank is not contiguous")
        except Exception as exc:
            failures.append(f"invalid ranking CSV {path}: {exc}")
    return paths


def _check_portfolios(
    portfolio_dir: Path,
    ranking_dir: Path,
    universe: list[str],
    did: str,
    failures: list[str],
) -> list[Path]:
    if not portfolio_dir.exists():
        failures.append(f"missing portfolio directory: {portfolio_dir}")
        return []

    paths = sorted(path for path in portfolio_dir.glob("*.csv") if path.is_file())
    if not paths:
        failures.append(f"no portfolio CSVs in {portfolio_dir}")
        return []

    universe_set = set(universe)
    for path in paths:
        try:
            frame = pd.read_csv(path)
            missing = PORTFOLIO_COLUMNS.difference(frame.columns)
            if missing:
                failures.append(f"{path} missing portfolio columns: {sorted(missing)}")
                continue
            if set(frame["ranking_date"].astype(str)) != {did}:
                failures.append(f"{path} has noncanonical ranking_date values")
            if frame["ticker"].astype(str).duplicated().any():
                failures.append(f"{path} has duplicate portfolio tickers")
            if set(frame["ticker"].astype(str)) != universe_set:
                failures.append(f"{path} ticker set does not match dated universe")
            if abs(float(frame["position_dollars"].sum())) > 0.01:
                failures.append(f"{path} portfolio is not dollar neutral")
            ranks = sorted(frame["portfolio_rank"].astype(int).tolist())
            if ranks != list(range(1, len(ranks) + 1)):
                failures.append(f"{path} portfolio_rank is not contiguous")

            ranking_path = ranking_dir / path.name
            if ranking_path.exists():
                expected = build_portfolio_book(pd.read_csv(ranking_path), universe)
                expected_tickers = [row["ticker"] for row in expected.rows]
                expected_statuses = [row["ranking_status"] for row in expected.rows]
                if frame["ticker"].astype(str).tolist() != expected_tickers:
                    failures.append(f"{path} is not ordered from its ranking artifact")
                if frame["ranking_status"].astype(str).tolist() != expected_statuses:
                    failures.append(f"{path} missing ranking placement changed")
        except Exception as exc:
            failures.append(f"invalid portfolio CSV {path}: {exc}")
    return paths


def _check_accounting(
    results_repo: Path,
    data_dir: Path,
    run_date: dt.date,
    strategy_ids: list[str],
    failures: list[str],
    warnings: list[str],
) -> None:
    try:
        close = pd.read_parquet(data_dir / "close.parquet")
        close.index = pd.to_datetime(close.index)
        entry_date, exit_date = next_two_trading_dates(trading_dates(close.index), run_date)
    except ValueError:
        warnings.append(f"accounting not yet scoreable for {date_id(run_date)}")
        return
    except Exception as exc:
        failures.append(f"could not inspect accounting dates: {exc}")
        return

    pnl_dir = results_repo / "accounting" / "daily_pnl"
    for strategy_id in strategy_ids:
        path = pnl_dir / f"{strategy_id}.csv"
        if not path.exists():
            failures.append(f"missing daily PnL for {strategy_id}: {path}")
            continue
        try:
            frame = pd.read_csv(path)
            missing = PNL_COLUMNS.difference(frame.columns)
            if missing:
                failures.append(f"{path} missing PnL columns: {sorted(missing)}")
                continue
            rows = frame[frame["ranking_date"].astype(str) == date_id(run_date)]
            if rows.empty:
                failures.append(f"{path} missing row for {date_id(run_date)}")
                continue
            if set(rows["entry_date"].astype(str)) != {date_id(entry_date)}:
                failures.append(f"{path} has wrong entry_date for {date_id(run_date)}")
            if set(rows["exit_date"].astype(str)) != {date_id(exit_date)}:
                failures.append(f"{path} has wrong exit_date for {date_id(run_date)}")
        except Exception as exc:
            failures.append(f"invalid daily PnL {path}: {exc}")


def load_audit_manifest(results_repo: Path, run_date: dt.date) -> dict | None:
    path = results_repo / "manifests" / "audits" / f"{date_id(run_date)}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text())
