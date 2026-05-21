from __future__ import annotations

import datetime as dt
import math
from pathlib import Path

import pandas as pd

from agentstockbenchmark.dates import date_id, parse_date_id
from agentstockbenchmark.io import atomic_write_csv
from agentstockbenchmark.settings import DEFAULT_RESULTS_REPO, POSITION_MAX_DOLLARS
from agentstockbenchmark.universe import latest_universe_file, read_universe_file


class PortfolioUniverse:
    def __init__(self, tickers: list[str], source: str, date: dt.date | None) -> None:
        self.tickers = tickers
        self.source = source
        self.date = date


class PortfolioBook:
    def __init__(
        self,
        rows: list[dict],
        n_ranked_in_universe: int,
        n_ranked_ignored: int,
        n_missing_rankings: int,
    ) -> None:
        self.rows = rows
        self.n_ranked_in_universe = n_ranked_in_universe
        self.n_ranked_ignored = n_ranked_ignored
        self.n_missing_rankings = n_missing_rankings


def build_portfolios(
    results_repo: Path = DEFAULT_RESULTS_REPO,
    ranking_date: dt.date | None = None,
    through: dt.date | None = None,
    data_dir: Path | None = None,
    strict_universe: bool = False,
    overwrite: bool = False,
) -> dict[str, int]:
    ranking_root = results_repo / "rankings"
    if data_dir is None:
        data_dir = results_repo / "data" / "parquet"
    close = load_close_or_none(data_dir)

    if ranking_date:
        dates = [ranking_date]
    else:
        if not ranking_root.exists():
            return {}
        dates = sorted(
            parse_date_id(path.name)
            for path in ranking_root.iterdir()
            if path.is_dir() and path.name[:4].isdigit()
        )
        if through:
            dates = [date for date in dates if date <= through]

    counts: dict[str, int] = {}
    for date in dates:
        counts[date_id(date)] = build_portfolios_for_date(
            results_repo=results_repo,
            ranking_date=date,
            close=close,
            strict_universe=strict_universe,
            overwrite=overwrite,
        )
    return counts


def build_portfolios_for_date(
    results_repo: Path,
    ranking_date: dt.date,
    close: pd.DataFrame | None = None,
    strict_universe: bool = False,
    overwrite: bool = False,
) -> int:
    ranking_dir = results_repo / "rankings" / date_id(ranking_date)
    if not ranking_dir.exists():
        return 0

    universe = load_portfolio_universe(
        results_repo=results_repo,
        ranking_date=ranking_date,
        close=close,
        strict=strict_universe,
    )

    portfolio_dir = results_repo / "portfolios" / date_id(ranking_date)
    portfolio_dir.mkdir(parents=True, exist_ok=True)

    built = 0
    for ranking_path in sorted(ranking_dir.glob("*.csv")):
        ranking_df = pd.read_csv(ranking_path)
        if ranking_df.empty:
            continue

        strategy_id = str(ranking_df["strategy_id"].iloc[0])
        portfolio_path = portfolio_dir / f"{strategy_id}.csv"
        if portfolio_path.exists() and not overwrite:
            built += 1
            continue

        book = build_portfolio_book(ranking_df, universe.tickers)
        rows = [
            {
                "ranking_date": date_id(ranking_date),
                "strategy_id": strategy_id,
                "ticker": row["ticker"],
                "score": row["score"],
                "portfolio_rank": row["portfolio_rank"],
                "position_dollars": round(row["position_dollars"], 2),
                "ranking_status": row["ranking_status"],
                "strategy_rank": row["strategy_rank"],
                "portfolio_universe_source": universe.source,
                "portfolio_universe_date": date_id(universe.date)
                if universe.date
                else "",
                "n_portfolio_universe": len(universe.tickers),
                "n_ranked_in_universe": book.n_ranked_in_universe,
                "n_ranked_ignored": book.n_ranked_ignored,
                "n_missing_rankings": book.n_missing_rankings,
            }
            for row in book.rows
        ]
        atomic_write_csv(portfolio_path, pd.DataFrame(rows))
        built += 1
    return built


def build_portfolio_book(
    ranking_df: pd.DataFrame,
    portfolio_universe: list[str],
) -> PortfolioBook:
    universe = sorted({str(ticker) for ticker in portfolio_universe})
    universe_set = set(universe)
    rankings: dict[str, tuple[float, int | None]] = {}
    ranked_tickers: set[str] = set()

    for _, row in ranking_df.iterrows():
        ticker = str(row["ticker"])
        ranked_tickers.add(ticker)
        if ticker not in universe_set:
            continue

        try:
            score = float(row["score"])
        except (TypeError, ValueError):
            continue
        if not math.isfinite(score):
            continue

        strategy_rank = None
        if "strategy_rank" in row and pd.notna(row["strategy_rank"]):
            strategy_rank = int(row["strategy_rank"])
        rankings[ticker] = (score, strategy_rank)

    ignored = ranked_tickers.difference(universe_set)
    missing = sorted(universe_set.difference(rankings))
    ranked_items = sorted(rankings.items(), key=lambda item: (-item[1][0], item[0]))

    center_start = (len(universe) - len(missing) + 1) // 2
    insert_at = min(center_start, len(ranked_items))
    ordered_items = (
        ranked_items[:insert_at]
        + [(ticker, (None, None)) for ticker in missing]
        + ranked_items[insert_at:]
    )

    rows = []
    n = len(ordered_items)
    for idx, (ticker, (score, strategy_rank)) in enumerate(ordered_items):
        if n < 2:
            position = 0.0
        else:
            position = POSITION_MAX_DOLLARS - idx * (2 * POSITION_MAX_DOLLARS) / (n - 1)
        rows.append(
            {
                "ticker": ticker,
                "score": score,
                "strategy_rank": strategy_rank,
                "portfolio_rank": idx + 1,
                "position_dollars": position,
                "ranking_status": "missing" if score is None else "ranked",
            }
        )

    return PortfolioBook(
        rows=rows,
        n_ranked_in_universe=len(rankings),
        n_ranked_ignored=len(ignored),
        n_missing_rankings=len(missing),
    )


def load_portfolio_universe(
    results_repo: Path,
    ranking_date: dt.date,
    close: pd.DataFrame | None = None,
    strict: bool = False,
) -> PortfolioUniverse:
    universe_dir = results_repo / "data" / "universe"
    exact_path = universe_dir / f"{date_id(ranking_date)}.txt"
    if exact_path.exists():
        return PortfolioUniverse(
            tickers=read_universe_file(exact_path),
            source=str(exact_path),
            date=ranking_date,
        )

    if strict:
        raise FileNotFoundError(f"missing portfolio universe: {exact_path}")

    latest = latest_universe_file(universe_dir)
    if latest is not None:
        return PortfolioUniverse(
            tickers=read_universe_file(latest),
            source=str(latest),
            date=parse_date_id(latest.stem),
        )

    if close is not None:
        return PortfolioUniverse(
            tickers=sorted(str(ticker) for ticker in close.columns),
            source="close_parquet_columns",
            date=None,
        )

    raise FileNotFoundError(
        f"no universe file in {universe_dir} and no close table fallback"
    )


def load_close_or_none(data_dir: Path) -> pd.DataFrame | None:
    close_path = data_dir / "close.parquet"
    if not close_path.exists():
        return None
    close = pd.read_parquet(close_path)
    close.index = pd.to_datetime(close.index)
    return close
