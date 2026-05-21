import datetime as dt
import tempfile
from pathlib import Path
from unittest import mock

import pandas as pd

from agentstockbenchmark.stage2.market_data import (
    download_universe,
    fetch_sp500_tickers,
    merge_daily_csvs_into_parquets,
    parse_sp500_tickers_from_html,
    update_table,
    validate_daily_csv,
    verify_daily_merge,
)


def test_update_table_overwrites_new_values_without_erasing_old_columns():
    existing = pd.DataFrame(
        {"A": [1.0], "B": [2.0]},
        index=pd.to_datetime(["2026-05-19"]),
    )
    existing.columns.name = "Ticker"
    new = pd.DataFrame(
        {"A": [3.0]},
        index=pd.to_datetime(["2026-05-19"]),
    )
    new.columns.name = "Ticker"

    combined = update_table(existing, new)

    assert combined.loc[pd.Timestamp("2026-05-19"), "A"] == 3.0
    assert combined.loc[pd.Timestamp("2026-05-19"), "B"] == 2.0
    assert combined.columns.name == "Ticker"


def test_update_table_overwrites_existing_value_with_missing_value():
    existing = pd.DataFrame(
        {"A": [2.0], "B": [5.0]},
        index=pd.to_datetime(["2026-05-19"]),
    )
    existing.columns.name = "Ticker"
    new = pd.DataFrame(
        {"A": [None]},
        index=pd.to_datetime(["2026-05-19"]),
    )
    new.columns.name = "Ticker"

    combined = update_table(existing, new)

    assert pd.isna(combined.loc[pd.Timestamp("2026-05-19"), "A"])
    assert combined.loc[pd.Timestamp("2026-05-19"), "B"] == 5.0


def test_validate_daily_csv_accepts_expected_schema():
    frame = pd.DataFrame(
        {
            "date": ["20260519"],
            "ticker": ["AAPL"],
            "open": [1.0],
            "high": [2.0],
            "low": [0.5],
            "close": [1.5],
            "volume": [100],
        }
    )

    validate_daily_csv(frame, path="dummy.csv")


def test_fetch_sp500_tickers_uses_user_agent_and_normalizes_symbols():
    html = b"""
    <table>
      <tr><th>Symbol</th><th>Security</th></tr>
      <tr><td>BRK.B</td><td>Berkshire Hathaway</td></tr>
      <tr><td>AAPL</td><td>Apple</td></tr>
    </table>
    """

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return html

    captured = {}

    def fake_urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return FakeResponse()

    with mock.patch("urllib.request.urlopen", fake_urlopen):
        tickers = fetch_sp500_tickers()

    assert tickers == ["AAPL", "BRK-B"]
    assert captured["request"].headers["User-agent"]
    assert captured["timeout"] == 30


def test_parse_sp500_tickers_from_html_finds_symbol_table_without_lxml():
    html = """
    <html><body>
      <table><tr><th>Other</th></tr><tr><td>Ignore</td></tr></table>
      <table>
        <tr><th>Symbol</th><th>Security</th></tr>
        <tr><td>MSFT</td><td>Microsoft</td></tr>
        <tr><td>BRK.B</td><td>Berkshire Hathaway</td></tr>
      </table>
    </body></html>
    """

    assert parse_sp500_tickers_from_html(html) == ["BRK-B", "MSFT"]


def test_parse_sp500_tickers_from_html_handles_footnote_header():
    html = """
    <html><body>
      <table>
        <tr><th colspan="2">S&P 500 components</th></tr>
        <tr><th>Security</th><th>Symbol[1]</th></tr>
        <tr><td>Apple</td><td>AAPL</td></tr>
        <tr><td>Berkshire Hathaway</td><td>BRK.B</td></tr>
      </table>
    </body></html>
    """

    assert parse_sp500_tickers_from_html(html) == ["AAPL", "BRK-B"]


def test_download_universe_falls_back_to_latest_cached_universe():
    with tempfile.TemporaryDirectory() as temp_dir:
        results_repo = Path(temp_dir)
        universe_dir = results_repo / "data" / "universe"
        universe_dir.mkdir(parents=True)
        (universe_dir / "20260501.txt").write_text("B\nA\n")

        with mock.patch(
            "agentstockbenchmark.stage2.market_data.fetch_sp500_tickers",
            side_effect=ValueError("blocked html"),
        ):
            path = download_universe(dt.date(2026, 5, 20), results_repo)

        assert path == universe_dir / "20260520.txt"
        assert path.read_text() == "A\nB\n"


def test_download_universe_falls_back_to_close_parquet_columns():
    with tempfile.TemporaryDirectory() as temp_dir:
        results_repo = Path(temp_dir)
        data_dir = results_repo / "data" / "parquet"
        data_dir.mkdir(parents=True)
        close = pd.DataFrame(
            {"MSFT": [1.0], "AAPL": [2.0]},
            index=pd.to_datetime(["2026-05-20"]),
        )
        close.to_parquet(data_dir / "close.parquet")

        with mock.patch(
            "agentstockbenchmark.stage2.market_data.fetch_sp500_tickers",
            side_effect=ValueError("blocked html"),
        ):
            path = download_universe(dt.date(2026, 5, 20), results_repo)

        assert path.read_text() == "AAPL\nMSFT\n"


def test_verify_daily_merge_checks_downloaded_values():
    with tempfile.TemporaryDirectory() as temp_dir:
        results_repo = Path(temp_dir)
        data_dir = results_repo / "data" / "parquet"
        daily_dir = results_repo / "data" / "raw" / "daily"
        data_dir.mkdir(parents=True)
        daily_dir.mkdir(parents=True)

        daily = pd.DataFrame(
            {
                "date": ["20260519"],
                "ticker": ["AAPL"],
                "open": [10.0],
                "high": [12.0],
                "low": [9.0],
                "close": [11.0],
                "volume": [123],
            }
        )
        daily.to_csv(daily_dir / "20260519.csv", index=False)

        index = pd.to_datetime(["2026-05-19"])
        values = {
            "open": 10.0,
            "high": 12.0,
            "low": 9.0,
            "close": 11.0,
            "volume": 123,
        }
        for field, value in values.items():
            table = pd.DataFrame({"AAPL": [value]}, index=index)
            table.index.name = "Date"
            table.columns.name = "Ticker"
            table.to_parquet(data_dir / f"{field}.parquet")

        report = verify_daily_merge(
            results_repo,
            data_dir,
            date=pd.Timestamp("2026-05-19").date(),
        )

        assert report["rows_checked"] == 1
        assert report["values_checked"] == 5
        assert report["null_values_encoded"] == 0
        assert report["failures"] == []


def test_verify_daily_merge_checks_expected_null_values_are_encoded_as_zero():
    with tempfile.TemporaryDirectory() as temp_dir:
        results_repo = Path(temp_dir)
        data_dir = results_repo / "data" / "parquet"
        daily_dir = results_repo / "data" / "raw" / "daily"
        data_dir.mkdir(parents=True)
        daily_dir.mkdir(parents=True)

        daily = pd.DataFrame(
            {
                "date": ["20260519"],
                "ticker": ["AAPL"],
                "open": [10.0],
                "high": [12.0],
                "low": [9.0],
                "close": [11.0],
                "volume": [None],
            }
        )
        daily.to_csv(daily_dir / "20260519.csv", index=False)

        index = pd.to_datetime(["2026-05-19"])
        values = {
            "open": 10.0,
            "high": 12.0,
            "low": 9.0,
            "close": 11.0,
            "volume": 0,
        }
        for field, value in values.items():
            table = pd.DataFrame({"AAPL": [value]}, index=index)
            table.index.name = "Date"
            table.columns.name = "Ticker"
            table.to_parquet(data_dir / f"{field}.parquet")

        report = verify_daily_merge(
            results_repo,
            data_dir,
            date=pd.Timestamp("2026-05-19").date(),
        )

        assert report["values_checked"] == 4
        assert report["null_values_encoded"] == 1
        assert report["failures"] == []


def test_merge_preserves_new_ticker_with_null_field():
    with tempfile.TemporaryDirectory() as temp_dir:
        results_repo = Path(temp_dir)
        data_dir = results_repo / "data" / "parquet"
        daily_dir = results_repo / "data" / "raw" / "daily"
        data_dir.mkdir(parents=True)
        daily_dir.mkdir(parents=True)

        old_index = pd.to_datetime(["2026-05-18"])
        for field, value in {
            "open": 10.0,
            "high": 11.0,
            "low": 9.0,
            "close": 10.5,
            "volume": 1000,
        }.items():
            table = pd.DataFrame({"A": [value]}, index=old_index)
            table.index.name = "Date"
            table.columns.name = "Ticker"
            table.to_parquet(data_dir / f"{field}.parquet")

        daily = pd.DataFrame(
            [
                {
                    "date": "20260519",
                    "ticker": "B",
                    "open": 20.0,
                    "high": 21.0,
                    "low": 19.0,
                    "close": 20.5,
                    "volume": None,
                }
            ]
        )
        daily.to_csv(daily_dir / "20260519.csv", index=False)

        merge_daily_csvs_into_parquets(results_repo)
        volume = pd.read_parquet(data_dir / "volume.parquet")

        assert "B" in volume.columns
        assert volume.loc[pd.Timestamp("2026-05-19"), "B"] == 0
