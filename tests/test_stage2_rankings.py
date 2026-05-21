import datetime as dt

import pandas as pd

from agentstockbenchmark.stage2.rankings import (
    build_snapshot,
    next_two_trading_dates,
    scores_to_ranked_rows,
)


def test_scores_to_ranked_rows_is_descending_and_tie_stable():
    rows = scores_to_ranked_rows({"B": 1.0, "A": 1.0, "C": -2.0})

    assert [row["ticker"] for row in rows] == ["A", "B", "C"]
    assert [row["strategy_rank"] for row in rows] == [1, 2, 3]


def test_next_two_trading_dates_uses_ranking_date_contract():
    dates = [
        dt.date(2026, 5, 11),
        dt.date(2026, 5, 12),
        dt.date(2026, 5, 13),
    ]

    assert next_two_trading_dates(dates, dt.date(2026, 5, 11)) == (
        dt.date(2026, 5, 12),
        dt.date(2026, 5, 13),
    )


def test_build_snapshot_encodes_missing_ohlcv_as_zero():
    index = pd.to_datetime(["2026-05-18", "2026-05-19"])
    tables = {
        "open": pd.DataFrame({"A": [1.0, None]}, index=index),
        "high": pd.DataFrame({"A": [2.0, None]}, index=index),
        "low": pd.DataFrame({"A": [0.5, None]}, index=index),
        "close": pd.DataFrame({"A": [1.5, None]}, index=index),
        "volume": pd.DataFrame({"A": [100.0, None]}, index=index),
    }

    snapshot = build_snapshot(
        tables,
        ranking_date=dt.date(2026, 5, 19),
        tickers=["A"],
        min_history=1,
    )

    assert snapshot["A"].loc[1, "open"] == 0
    assert snapshot["A"].loc[1, "high"] == 0
    assert snapshot["A"].loc[1, "low"] == 0
    assert snapshot["A"].loc[1, "close"] == 0
    assert snapshot["A"].loc[1, "volume"] == 0


def test_build_snapshot_excludes_all_zero_ticker_history():
    index = pd.to_datetime(["2026-05-18", "2026-05-19"])
    tables = {
        field: pd.DataFrame({"A": [0.0, 0.0]}, index=index)
        for field in ["open", "high", "low", "close", "volume"]
    }

    snapshot = build_snapshot(
        tables,
        ranking_date=dt.date(2026, 5, 19),
        tickers=["A"],
        min_history=1,
    )

    assert snapshot == {}
