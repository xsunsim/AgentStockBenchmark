import datetime as dt
import tempfile
from pathlib import Path

import pandas as pd

from agentstockbenchmark.dates import date_id, parse_date
from agentstockbenchmark.manifests import (
    collect_artifacts_for_date,
    verify_artifact_manifest,
    write_artifact_manifest,
)
from agentstockbenchmark.research import (
    generate_strategies_workspace,
    promote_research_strategy,
    research_backtest,
)
from agentstockbenchmark.stage2.market_data import merge_daily_csvs_into_parquets
from agentstockbenchmark.stage2.market_data import ensure_cached_daily_from_parquets
from agentstockbenchmark.stage3.accounting import update_accounting, write_or_append_daily_pnl
from agentstockbenchmark.workflow import backfill, run_daily


def test_date_helper_accepts_iso_but_emits_compact():
    assert parse_date("20260519") == dt.date(2026, 5, 19)
    assert parse_date("2026-05-19") == dt.date(2026, 5, 19)
    assert date_id(dt.date(2026, 5, 19)) == "20260519"


def test_accounting_skips_zero_prices_and_writes_compact_dates():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        data_dir = root / "data" / "parquet"
        portfolio_dir = root / "portfolios" / "20260519"
        data_dir.mkdir(parents=True)
        portfolio_dir.mkdir(parents=True)

        index = pd.to_datetime(["2026-05-19", "2026-05-20", "2026-05-21"])
        close = pd.DataFrame(
            {
                "A": [10.0, 10.0, 11.0],
                "B": [20.0, 0.0, 19.0],
                "C": [30.0, 30.0, 0.0],
            },
            index=index,
        )
        close.to_parquet(data_dir / "close.parquet")
        pd.DataFrame(
            [
                {
                    "ranking_date": "20260519",
                    "strategy_id": "20260519__Fixture",
                    "ticker": "A",
                    "position_dollars": 250.0,
                    "n_portfolio_universe": 3,
                    "n_ranked_in_universe": 3,
                    "n_ranked_ignored": 0,
                    "n_missing_rankings": 0,
                },
                {
                    "ranking_date": "20260519",
                    "strategy_id": "20260519__Fixture",
                    "ticker": "B",
                    "position_dollars": -125.0,
                    "n_portfolio_universe": 3,
                    "n_ranked_in_universe": 3,
                    "n_ranked_ignored": 0,
                    "n_missing_rankings": 0,
                },
                {
                    "ranking_date": "20260519",
                    "strategy_id": "20260519__Fixture",
                    "ticker": "C",
                    "position_dollars": -125.0,
                    "n_portfolio_universe": 3,
                    "n_ranked_in_universe": 3,
                    "n_ranked_ignored": 0,
                    "n_missing_rankings": 0,
                },
            ]
        ).to_csv(portfolio_dir / "20260519__Fixture.csv", index=False)

        counts = update_accounting(root, data_dir=data_dir, through=dt.date(2026, 5, 21))
        pnl = pd.read_csv(root / "accounting" / "daily_pnl" / "20260519__Fixture.csv")

        assert counts == {"20260519": 1}
        assert pnl.loc[0, "ranking_date"] == 20260519
        assert str(pnl.loc[0, "entry_date"]) == "20260520"
        assert str(pnl.loc[0, "exit_date"]) == "20260521"
        assert pnl.loc[0, "n_positions"] == 1
        assert pnl.loc[0, "total_pnl"] == 25.0

        update_accounting(root, data_dir=data_dir, through=dt.date(2026, 5, 21))
        pnl = pd.read_csv(root / "accounting" / "daily_pnl" / "20260519__Fixture.csv")
        assert len(pnl) == 1


def test_accounting_append_normalizes_existing_numeric_dates_before_sort():
    with tempfile.TemporaryDirectory() as temp_dir:
        path = Path(temp_dir) / "daily_pnl" / "Fixture.csv"
        path.parent.mkdir(parents=True)
        pd.DataFrame(
            [
                {
                    "ranking_date": 20260501,
                    "entry_date": 20260504,
                    "exit_date": 20260505,
                    "strategy_id": "Fixture",
                    "total_pnl": 1.0,
                    "long_pnl": 2.0,
                    "short_pnl": -1.0,
                    "n_positions": 10,
                    "n_portfolio_universe": 500,
                    "n_ranked_in_universe": 500,
                    "n_ranked_ignored": 0,
                    "n_missing_rankings": 0,
                }
            ]
        ).to_csv(path, index=False)

        write_or_append_daily_pnl(
            path,
            [
                {
                    "ranking_date": "20260502",
                    "entry_date": "20260505",
                    "exit_date": "20260506",
                    "strategy_id": "Fixture",
                    "total_pnl": 3.0,
                    "long_pnl": 1.0,
                    "short_pnl": 2.0,
                    "n_positions": 9,
                    "n_portfolio_universe": 500,
                    "n_ranked_in_universe": 499,
                    "n_ranked_ignored": 1,
                    "n_missing_rankings": 1,
                }
            ],
        )

        pnl = pd.read_csv(path, dtype={"ranking_date": str})
        assert pnl["ranking_date"].tolist() == ["20260501", "20260502"]


def test_daily_run_dry_run_uses_compact_date():
    with tempfile.TemporaryDirectory() as temp_dir:
        report = run_daily(
            dt.date(2026, 5, 19),
            results_repo=Path(temp_dir),
            skip_download=True,
            dry_run=True,
        )

    assert report["run_date"] == "20260519"
    assert report["status"] == "DRY_RUN"
    assert "generate-rankings" in report["planned_steps"]


def test_daily_run_fake_source_builds_live_artifacts_with_compact_paths():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        strategies_dir = root / "strategies"
        strategy_dir = strategies_dir / "20260519" / "Fixture"
        strategy_dir.mkdir(parents=True)
        (strategy_dir / "strategy.py").write_text(
            "def generate_signal(data):\n"
            "    return {ticker: float(frame['close'].iloc[-1]) "
            "for ticker, frame in data.items()}\n"
        )

        universe_dir = root / "data" / "universe"
        daily_dir = root / "data" / "raw" / "daily"
        universe_dir.mkdir(parents=True)
        daily_dir.mkdir(parents=True)
        (universe_dir / "20260519.txt").write_text("A\nB\nC\n")

        for idx, day in enumerate(pd.bdate_range(end="2026-05-21", periods=24)):
            rows = []
            for offset, ticker in enumerate(["A", "B", "C"]):
                close = 10.0 + idx + offset
                rows.append(
                    {
                        "date": day.strftime("%Y%m%d"),
                        "ticker": ticker,
                        "open": close - 0.2,
                        "high": close + 0.5,
                        "low": close - 0.5,
                        "close": close,
                        "volume": 1000 + idx + offset,
                    }
                )
            pd.DataFrame(rows).to_csv(daily_dir / f"{day:%Y%m%d}.csv", index=False)

        report = run_daily(
            dt.date(2026, 5, 19),
            results_repo=root,
            strategies_dir=strategies_dir,
            prompt_id="20260519",
            skip_download=True,
        )

        assert report["status"] == "PASS"
        assert (root / "rankings" / "20260519" / "20260519__Fixture.csv").exists()
        assert (root / "portfolios" / "20260519" / "20260519__Fixture.csv").exists()
        assert (root / "manifests" / "runs" / "20260519.json").exists()
        audit = root / "manifests" / "audits" / "20260519.json"
        assert audit.exists()


def test_merge_daily_csv_encodes_missing_as_zero_with_compact_path():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        daily_dir = root / "data" / "raw" / "daily"
        daily_dir.mkdir(parents=True)
        pd.DataFrame(
            [
                {
                    "date": "20260519",
                    "ticker": "A",
                    "open": 10.0,
                    "high": 11.0,
                    "low": 9.0,
                    "close": 10.5,
                    "volume": None,
                }
            ]
        ).to_csv(daily_dir / "20260519.csv", index=False)

        written = merge_daily_csvs_into_parquets(root)
        volume = pd.read_parquet(written["volume"])

        assert volume.loc[pd.Timestamp("2026-05-19"), "A"] == 0


def test_skip_download_can_materialize_daily_cache_from_parquets():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        data_dir = root / "data" / "parquet"
        data_dir.mkdir(parents=True)

        index = pd.to_datetime(["2026-05-01"])
        close = pd.DataFrame({"A": [10.0], "B": [20.0]}, index=index)
        tables = {
            "close": close,
            "open": close - 0.1,
            "high": close + 0.2,
            "low": close - 0.2,
            "volume": close * 100,
        }
        for field, table in tables.items():
            table.to_parquet(data_dir / f"{field}.parquet")

        daily_path, universe_path = ensure_cached_daily_from_parquets(
            dt.date(2026, 5, 1),
            root,
            data_dir=data_dir,
        )
        daily = pd.read_csv(daily_path)

        assert daily_path == root / "data" / "raw" / "daily" / "20260501.csv"
        assert universe_path == root / "data" / "universe" / "20260501.txt"
        assert daily["date"].astype(str).unique().tolist() == ["20260501"]
        assert daily["ticker"].astype(str).tolist() == ["A", "B"]
        assert universe_path.read_text() == "A\nB\n"


def test_research_backtest_stays_in_research_namespace():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        data_dir = root / "data" / "parquet"
        strategies_dir = root / "strategies"
        strategy_dir = strategies_dir / "20260519" / "Fixture"
        data_dir.mkdir(parents=True)
        strategy_dir.mkdir(parents=True)
        (strategy_dir / "strategy.py").write_text(
            "def generate_signal(data):\n"
            "    return {ticker: float(frame['close'].iloc[-1]) "
            "for ticker, frame in data.items()}\n"
        )

        index = pd.bdate_range(end="2026-05-21", periods=24)
        close = pd.DataFrame(
            {
                "A": [10.0 + i for i in range(len(index))],
                "B": [20.0 + i for i in range(len(index))],
                "C": [30.0 + i for i in range(len(index))],
            },
            index=index,
        )
        tables = {
            "close": close,
            "open": close - 0.2,
            "high": close + 0.5,
            "low": close - 0.5,
            "volume": close * 100,
        }
        for field, table in tables.items():
            table.to_parquet(data_dir / f"{field}.parquet")

        run_dir = research_backtest(
            prompt_id="20260519",
            start=dt.date(2026, 5, 19),
            end=dt.date(2026, 5, 19),
            data_dir=data_dir,
            results_repo=root,
            strategies_dir=strategies_dir,
            run_id="testrun",
        )

        assert run_dir == root / "research" / "20260519" / "testrun"
        assert (run_dir / "rankings" / "20260519" / "20260519__Fixture.csv").exists()
        assert not (root / "rankings").exists()

def test_artifact_manifest_excludes_mutable_aggregate_outputs():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        for rel in [
            "data/universe/20260519.txt",
            "data/raw/daily/20260519.csv",
            "rankings/20260519/S.csv",
            "portfolios/20260519/S.csv",
            "accounting/metrics/20260519.csv",
            "accounting/daily_pnl/S.csv",
            "accounting/latest_metrics.csv",
            "leaderboard/leaderboard.csv",
        ]:
            path = root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("original\n")

        paths = [
            path.relative_to(root).as_posix()
            for path in collect_artifacts_for_date(root, dt.date(2026, 5, 19))
        ]
        assert "accounting/daily_pnl/S.csv" not in paths
        assert "accounting/latest_metrics.csv" not in paths
        assert "leaderboard/leaderboard.csv" not in paths

        write_artifact_manifest(root, dt.date(2026, 5, 19))
        (root / "accounting" / "daily_pnl" / "S.csv").write_text("changed\n")
        (root / "accounting" / "latest_metrics.csv").write_text("changed\n")

        assert verify_artifact_manifest(root, dt.date(2026, 5, 19)) == []


def test_backfill_portfolios_and_accounting_respect_start_date():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        data_dir = root / "data" / "parquet"
        data_dir.mkdir(parents=True)
        (root / "data" / "universe").mkdir(parents=True)
        (root / "data" / "universe" / "20260518.txt").write_text("A\nB\n")
        (root / "data" / "universe" / "20260519.txt").write_text("A\nB\n")

        close = pd.DataFrame(
            {"A": [10.0, 11.0, 12.0, 13.0], "B": [20.0, 19.0, 18.0, 17.0]},
            index=pd.to_datetime(
                ["2026-05-18", "2026-05-19", "2026-05-20", "2026-05-21"]
            ),
        )
        close.to_parquet(data_dir / "close.parquet")

        for did in ["20260518", "20260519"]:
            ranking_dir = root / "rankings" / did
            ranking_dir.mkdir(parents=True)
            pd.DataFrame(
                [
                    {
                        "ranking_date": did,
                        "prompt_id": "20260519",
                        "strategy_slug": "Fixture",
                        "strategy_id": "20260519__Fixture",
                        "ticker": "A",
                        "score": 2.0,
                        "strategy_rank": 1,
                    },
                    {
                        "ranking_date": did,
                        "prompt_id": "20260519",
                        "strategy_slug": "Fixture",
                        "strategy_id": "20260519__Fixture",
                        "ticker": "B",
                        "score": 1.0,
                        "strategy_rank": 2,
                    },
                ]
            ).to_csv(ranking_dir / "20260519__Fixture.csv", index=False)

        backfill(
            start=dt.date(2026, 5, 19),
            end=dt.date(2026, 5, 19),
            step="portfolios",
            results_repo=root,
            data_dir=data_dir,
        )
        assert not (root / "portfolios" / "20260518").exists()
        assert (root / "portfolios" / "20260519").exists()

        report = backfill(
            start=dt.date(2026, 5, 19),
            end=dt.date(2026, 5, 19),
            step="accounting",
            results_repo=root,
            data_dir=data_dir,
        )
        assert report["dates"] == {"20260519": 1}
        pnl = pd.read_csv(root / "accounting" / "daily_pnl" / "20260519__Fixture.csv")
        assert pnl["ranking_date"].astype(str).tolist() == ["20260519"]


def test_research_workspace_and_promote_do_not_fall_back_to_live_strategy():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        run_dir = generate_strategies_workspace(
            prompt_id="20260519",
            results_repo=root,
            run_id="testrun",
            reference_root=root / "missing_reference",
        )
        assert (run_dir / "strategies" / "20260519").is_dir()

        try:
            promote_research_strategy(
                run_id="testrun",
                strategy_id="20260519__DoesNotExist",
                results_repo=root,
            )
        except FileNotFoundError:
            pass
        else:
            raise AssertionError("promotion unexpectedly fell back to live strategies")


if __name__ == "__main__":
    test_date_helper_accepts_iso_but_emits_compact()
    test_accounting_skips_zero_prices_and_writes_compact_dates()
    test_accounting_append_normalizes_existing_numeric_dates_before_sort()
    test_daily_run_dry_run_uses_compact_date()
    test_daily_run_fake_source_builds_live_artifacts_with_compact_paths()
    test_merge_daily_csv_encodes_missing_as_zero_with_compact_path()
    test_skip_download_can_materialize_daily_cache_from_parquets()
    test_research_backtest_stays_in_research_namespace()
    test_artifact_manifest_excludes_mutable_aggregate_outputs()
