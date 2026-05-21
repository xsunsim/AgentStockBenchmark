from __future__ import annotations

import datetime as dt
import re
import time
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

import pandas as pd
    
from agentstockbenchmark.dates import date_id, parse_date
from agentstockbenchmark.io import (
    atomic_write_csv,
    atomic_write_parquet,
    atomic_write_text,
)
from agentstockbenchmark.settings import OHLCV_FIELDS, RAW_CSV_FIELD_NAMES
from agentstockbenchmark.universe import latest_universe_file, read_universe_file
    
    
DAILY_RAW_DIRNAME = "daily"
UNIVERSE_DIRNAME = "universe"
SP500_WIKIPEDIA_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
WIKIPEDIA_USER_AGENT = (
    "Mozilla/5.0 (compatible; AgentStockBenchmark/0.1; "
    "+https://github.com/openai/codex)"
)   
    

def build_parquets_from_wide_csv(raw_csv: Path, output_dir: Path) -> dict[str, Path]:
    """Build field-level OHLCV parquets from the seeded Yahoo-style CSV."""
    if not raw_csv.exists():
        raise FileNotFoundError(f"raw CSV not found: {raw_csv}")
    
    output_dir.mkdir(parents=True, exist_ok=True)
    raw = pd.read_csv(raw_csv, header=[0, 1], index_col=0)
    raw.index = pd.to_datetime(raw.index)
    raw.index.name = "Date"
    
    written: dict[str, Path] = {}
    for source_field, field in RAW_CSV_FIELD_NAMES.items():
        if source_field not in raw.columns.get_level_values(0):
            raise ValueError(f"raw CSV missing field {source_field!r}")
        table = raw[source_field].sort_index()
        table = table.loc[:, sorted(table.columns)]
        table = table.apply(pd.to_numeric, errors="coerce")
        table = table.fillna(0)
        out_path = output_dir / f"{field}.parquet"
        atomic_write_parquet(out_path, table)
        written[field] = out_path
    return written

def download_universe(
    date: dt.date,
    results_repo: Path,
    overwrite: bool = False,
) -> Path:
    out_dir = results_repo / "data" / UNIVERSE_DIRNAME
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{date_id(date)}.txt"
    if out_path.exists() and not overwrite:
        return out_path

    try:
        tickers = fetch_sp500_tickers()
    except Exception as exc:
        tickers = fallback_universe_tickers(results_repo, cause=exc)
    atomic_write_text(out_path, "\n".join(tickers) + "\n")
    return out_path


def download_daily_csv(
    date: dt.date,
    results_repo: Path,
    overwrite: bool = False,
) -> tuple[Path, Path]:
    universe_path = download_universe(date, results_repo, overwrite=overwrite)
    tickers = [
        line.strip()
        for line in universe_path.read_text().splitlines()
        if line.strip()
    ]

    raw_dir = results_repo / "data" / "raw" / DAILY_RAW_DIRNAME
    raw_dir.mkdir(parents=True, exist_ok=True)
    csv_path = raw_dir / f"{date_id(date)}.csv"
    if csv_path.exists() and not overwrite:
        return csv_path, universe_path

    df = fetch_daily_ohlcv(tickers, date)
    if df.empty:
        raise ValueError(f"no OHLCV rows downloaded for {date}")
    atomic_write_csv(csv_path, df)
    return csv_path, universe_path

def refresh_daily_data(
    date: dt.date,
    results_repo: Path,
    data_dir: Path | None = None,
    overwrite: bool = False,
) -> dict[str, Path]:
    csv_path, universe_path = download_daily_csv(
        date=date,
        results_repo=results_repo,
        overwrite=overwrite,
    )
    written = merge_daily_csvs_into_parquets(results_repo, data_dir)
    verify_daily_merge(results_repo, data_dir, date=date)
    return {
        "daily_csv": csv_path,
        "universe": universe_path,
        **{f"parquet_{field}": path for field, path in written.items()},
    }

def ensure_cached_daily_from_parquets(
    date: dt.date,
    results_repo: Path,
    data_dir: Path | None = None,
    overwrite: bool = False,
) -> tuple[Path, Path]:
    """Ensure skip-download has dated raw daily and universe artifacts.

    Historical/local runs may already have complete field-level parquets but no
    normalized daily CSV cache. This materializes the canonical cache artifacts
    from those parquets so merge verification and audit still inspect normal
    production paths.
    """
    if data_dir is None:
        data_dir = results_repo / "data" / "parquet"

    did = date_id(date)
    daily_path = results_repo / "data" / "raw" / DAILY_RAW_DIRNAME / f"{did}.csv"
    universe_path = results_repo / "data" / UNIVERSE_DIRNAME / f"{did}.txt"
    if daily_path.exists() and universe_path.exists() and not overwrite:
        return daily_path, universe_path

    tables = load_ohlcv_tables(data_dir)
    timestamp = pd.Timestamp(date)
    close = tables["close"]
    if timestamp not in close.index:
        raise FileNotFoundError(
            "skip-download requires cached daily/universe artifacts or parquets "
            f"containing {did}; missing {timestamp.date()} in "
            f"{data_dir / 'close.parquet'}"
        )

    tickers = sorted(str(ticker) for ticker in close.columns)
    rows = []
    for ticker in tickers:
        row = {"date": did, "ticker": ticker}
        for field in OHLCV_FIELDS:
            table = tables[field]
            value = 0.0
            if ticker in table.columns and timestamp in table.index:
                value = table.loc[timestamp, ticker]
            row[field] = 0.0 if pd.isna(value) else float(value)
        rows.append(row)

    if overwrite or not daily_path.exists():
        atomic_write_csv(daily_path, pd.DataFrame(rows))
    if overwrite or not universe_path.exists():
        atomic_write_text(universe_path, "\n".join(tickers) + "\n")
    return daily_path, universe_path

def fetch_sp500_tickers() -> list[str]:
    request = urllib.request.Request(
        SP500_WIKIPEDIA_URL,
        headers={"User-Agent": WIKIPEDIA_USER_AGENT},
    )
    backoff = 10
    while True:
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                html = response.read()
            return parse_sp500_tickers_from_html(html.decode("utf-8", errors="replace"))
        except Exception as exc:
            print(f"Error fetching SP500 tickers from Wikipedia: {exc}. Retrying in {backoff}s...")
            time.sleep(backoff)
            backoff = min(backoff * 2, 300)


def fallback_universe_tickers(results_repo: Path, cause: Exception) -> list[str]:
    universe_dir = results_repo / "data" / UNIVERSE_DIRNAME
    latest = latest_universe_file(universe_dir)
    if latest is not None:
        tickers = read_universe_file(latest)
        if tickers:
            return tickers

    close_path = results_repo / "data" / "parquet" / "close.parquet"
    if close_path.exists():
        close = pd.read_parquet(close_path)
        tickers = sorted(
            {
                str(ticker).strip()
                for ticker in close.columns
                if str(ticker).strip()
            }
        )
        if tickers:
            return tickers

    raise RuntimeError(
        "could not fetch S&P 500 universe from Wikipedia and no cached universe "
        f"or close parquet fallback exists under {results_repo}"
    ) from cause

def parse_sp500_tickers_from_html(html: str) -> list[str]:
    parser = HtmlTableParser()
    parser.feed(html)
    for rows in parser.tables:
        if not rows:
            continue
        header_idx, symbol_idx = find_symbol_column(rows)
        if symbol_idx is None:
            continue
        tickers = []
        for row in rows[header_idx + 1 :]:
            if symbol_idx >= len(row):
                continue
            ticker = normalize_ticker_cell(row[symbol_idx])
            if ticker:
                tickers.append(ticker)
        if tickers:
            return sorted(set(tickers))
    raise ValueError("could not find S&P 500 Symbol table in Wikipedia HTML")


def find_symbol_column(rows: list[list[str]]) -> tuple[int, int | None]:
    for row_idx, row in enumerate(rows):
        headers = [normalize_header_cell(cell) for cell in row]
        for symbol_name in ("symbol", "ticker", "tickersymbol"):
            if symbol_name in headers:
                return row_idx, headers.index(symbol_name)
        for col_idx, header in enumerate(headers):
            if header.endswith("symbol") and "industry" not in header:
                return row_idx, col_idx
    return 0, None


def normalize_header_cell(value: str) -> str:
    text = re.sub(r"\[[^\]]*\]", "", value.lower())
    return re.sub(r"[^a-z0-9]+", "", text)


def normalize_ticker_cell(value: str) -> str:
    text = " ".join(value.replace("\xa0", " ").split())
    if not text:
        return ""
    text = text.split("[", 1)[0].strip()
    text = text.split(" ", 1)[0].strip()
    return text.replace(".", "-")

class HtmlTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tables: list[list[list[str]]] = []
        self._table_depth = 0
        self._current_table: list[list[str]] | None = None
        self._current_row: list[str] | None = None
        self._current_cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag == "table":
            self._table_depth += 1
            if self._table_depth == 1:
                self._current_table = []
        elif tag == "tr" and self._table_depth == 1:
            self._current_row = []
        elif tag in {"th", "td"} and self._table_depth == 1:
            self._current_cell = []

    def handle_data(self, data: str) -> None:
        if self._current_cell is not None:
            self._current_cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"th", "td"} and self._current_cell is not None:
            if self._current_row is not None:
                text = " ".join("".join(self._current_cell).split())
                self._current_row.append(text)
            self._current_cell = None
        elif tag == "tr" and self._current_row is not None:
            if self._current_table is not None and self._current_row:
                self._current_table.append(self._current_row)
            self._current_row = None
        elif tag == "table" and self._table_depth:
            if self._table_depth == 1 and self._current_table is not None:
                self.tables.append(self._current_table)
                self._current_table = None
            self._table_depth -= 1

def fetch_daily_ohlcv(tickers: list[str], date: dt.date) -> pd.DataFrame:
    import yfinance as yf

    start = date.isoformat()
    end = (date + dt.timedelta(days=1)).isoformat()
    
    backoff = 10
    while True:
        try:
            raw = yf.download(
                tickers,
                start=start,
                end=end,
                auto_adjust=True,
                threads=True,
                progress=False,
            )
            if raw.empty:
                print(f"Warning: yfinance returned empty data for {date}. Retrying in {backoff}s...")
                time.sleep(backoff)
                backoff = min(backoff * 2, 300)
                continue
            
            rows = []
            for ticker in tickers:
                row = _extract_download_row(raw, ticker, date)
                if row is not None:
                    rows.append(row)
            
            if not rows:
                print(f"Warning: No valid rows extracted for {date}. Retrying in {backoff}s...")
                time.sleep(backoff)
                backoff = min(backoff * 2, 300)
                continue
                
            return pd.DataFrame(rows)
        except Exception as exc:
            print(f"Error downloading data for {date}: {exc}. Retrying in {backoff}s...")
            time.sleep(backoff)
            backoff = min(backoff * 2, 300)

def merge_daily_csvs_into_parquets(
    results_repo: Path,
    output_dir: Path | None = None,
) -> dict[str, Path]:
    if output_dir is None:
        output_dir = results_repo / "data" / "parquet"

    daily_dir = results_repo / "data" / "raw" / DAILY_RAW_DIRNAME
    daily = load_daily_csvs(daily_dir)
    daily_dates = sorted(pd.to_datetime(daily["date"]).dt.normalize().unique())
    daily_tickers = sorted(daily["ticker"].astype(str).unique())
    output_dir.mkdir(parents=True, exist_ok=True)

    written: dict[str, Path] = {}
    for field in OHLCV_FIELDS:
        new_table = daily.pivot_table(
            index="date",
            columns="ticker",
            values=field,
            aggfunc="last",
        )
        new_table = new_table.reindex(index=daily_dates, columns=daily_tickers)
        new_table.index = pd.to_datetime(new_table.index)
        new_table.index.name = "Date"
        new_table.columns.name = "Ticker"
        new_table = new_table.apply(pd.to_numeric, errors="coerce")

        path = output_dir / f"{field}.parquet"
        if path.exists():
            combined = pd.read_parquet(path)
            combined.index = pd.to_datetime(combined.index)
            combined = update_table(combined, new_table)
        else:
            combined = new_table

        combined = combined.sort_index()
        combined = combined.loc[:, sorted(combined.columns)]
        combined.index.name = "Date"
        combined.columns.name = "Ticker"
        combined = combined.fillna(0)
        atomic_write_parquet(path, combined)
        written[field] = path
    return written

def verify_daily_merge(
    results_repo: Path,
    data_dir: Path | None = None,
    date: dt.date | None = None,
    rtol: float = 1e-9,
    atol: float = 1e-9,
) -> dict:
    if data_dir is None:
        data_dir = results_repo / "data" / "parquet"

    daily_dir = results_repo / "data" / "raw" / DAILY_RAW_DIRNAME
    daily = load_daily_csvs(daily_dir)
    daily["date"] = pd.to_datetime(daily["date"])
    if date is not None:
        daily = daily[daily["date"].dt.date == date]
    if daily.empty:
        raise ValueError(f"no daily CSV rows to verify for date={date}")

    tables = load_ohlcv_tables(data_dir)
    failures: list[dict] = []
    checked_values = 0
    null_values_encoded = 0

    for _, row in daily.iterrows():
        row_date = pd.Timestamp(row["date"]).normalize()
        ticker = str(row["ticker"])
        for field in OHLCV_FIELDS:
            expected = row[field]
            table = tables[field]
            if row_date not in table.index:
                failures.append(
                    {
                        "date": date_id(row_date.date()),
                        "ticker": ticker,
                        "field": field,
                        "error": "missing_date",
                    }
                )
                continue
            if ticker not in table.columns:
                failures.append(
                    {
                        "date": date_id(row_date.date()),
                        "ticker": ticker,
                        "field": field,
                        "error": "missing_ticker",
                    }
                )
                continue

            actual = table.loc[row_date, ticker]
            if pd.isna(expected):
                null_values_encoded += 1
                if not values_match(actual, 0, rtol=rtol, atol=atol):
                    failures.append(
                        {
                            "date": date_id(row_date.date()),
                            "ticker": ticker,
                            "field": field,
                            "error": "missing_value_not_encoded_as_zero",
                            "expected": 0,
                            "actual": actual,
                        }
                    )
                continue

            checked_values += 1
            if not values_match(actual, expected, rtol=rtol, atol=atol):
                failures.append(
                    {
                        "date": date_id(row_date.date()),
                        "ticker": ticker,
                        "field": field,
                        "error": "value_mismatch",
                        "expected": expected,
                        "actual": actual,
                    }
                )

    report = {
        "dates_checked": sorted(
            date_id(pd.Timestamp(d).date()) for d in daily["date"].unique()
        ),
        "rows_checked": int(len(daily)),
        "values_checked": int(checked_values),
        "null_values_encoded": int(null_values_encoded),
        "failures": failures,
    }
    if failures:
        raise ValueError(
            f"daily merge verification failed: {len(failures)} mismatches; "
            f"first failure: {failures[0]}"
        )
    return report

def values_match(actual, expected, rtol: float, atol: float) -> bool:
    if pd.isna(actual) and pd.isna(expected):
        return True
    if pd.isna(actual) or pd.isna(expected):
        return False
    actual_float = float(actual)
    expected_float = float(expected)
    return abs(actual_float - expected_float) <= atol + rtol * abs(expected_float)


def load_daily_csvs(daily_dir: Path) -> pd.DataFrame:
    csv_paths = sorted(daily_dir.glob("*.csv"))
    if not csv_paths:
        raise FileNotFoundError(f"no downloaded daily CSVs found in {daily_dir}")

    frames = []
    for path in csv_paths:
        frame = pd.read_csv(path)
        validate_daily_csv(frame, path)
        frames.append(frame)

    combined = pd.concat(frames, ignore_index=True)
    combined["date"] = combined["date"].map(
        lambda value: pd.Timestamp(parse_date(value))
    )
    combined["ticker"] = combined["ticker"].astype(str)
    combined = combined.drop_duplicates(subset=["date", "ticker"], keep="last")
    return combined.sort_values(["date", "ticker"]).reset_index(drop=True)


def validate_daily_csv(frame: pd.DataFrame, path: Path) -> None:
    required = {"date", "ticker", *OHLCV_FIELDS}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"{path} missing columns: {sorted(missing)}")


def update_table(existing: pd.DataFrame, new: pd.DataFrame) -> pd.DataFrame:
    dates = existing.index.union(new.index)
    columns = existing.columns.union(new.columns)
    combined = existing.reindex(index=dates, columns=columns)

    new_values = new.apply(pd.to_numeric, errors="coerce")
    combined.loc[new_values.index, new_values.columns] = new_values
    combined.index.name = existing.index.name or new.index.name
    combined.columns.name = existing.columns.name or new.columns.name
    return combined


def load_ohlcv_tables(data_dir: Path) -> dict[str, pd.DataFrame]:
    tables: dict[str, pd.DataFrame] = {}
    for field in OHLCV_FIELDS:
        path = data_dir / f"{field}.parquet"
        if not path.exists():
            raise FileNotFoundError(f"missing market data parquet: {path}")
        table = pd.read_parquet(path)
        table.index = pd.to_datetime(table.index)
        tables[field] = table.sort_index()
    return tables


def _extract_download_row(
    raw: pd.DataFrame,
    ticker: str,
    date: dt.date,
) -> dict | None:
    try:
        values = {
            field: _download_value(raw, source_field, ticker)
            for source_field, field in RAW_CSV_FIELD_NAMES.items()
        }
    except (KeyError, IndexError):
        return None

    close = values["close"]
    if pd.isna(close):
        return None

    return {
        "date": date_id(date),
        "ticker": ticker,
        "open": float(values["open"]),
        "high": float(values["high"]),
        "low": float(values["low"]),
        "close": float(close),
        "volume": int(values["volume"]) if pd.notna(values["volume"]) else 0,
    }

def _download_value(raw: pd.DataFrame, source_field: str, ticker: str):
    if isinstance(raw.columns, pd.MultiIndex):
        if (source_field, ticker) in raw.columns:
            return raw[(source_field, ticker)].iloc[0]
        if (ticker, source_field) in raw.columns:
            return raw[(ticker, source_field)].iloc[0]
    if source_field in raw.columns:
        return raw[source_field].iloc[0]
    raise KeyError((source_field, ticker))
