from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

from agentstockbenchmark.dates import date_id, parse_date
from agentstockbenchmark.settings import DEFAULT_RESULTS_REPO, STRATEGIES_DIR


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="agentstockbenchmark",
        description="Three-stage agent stock benchmark engine",
    )
    sub = parser.add_subparsers(dest="stage")

    daily = sub.add_parser("daily-run", help="Run production workflow for one date")
    add_workflow_args(daily, require_date=True)

    resume = sub.add_parser("resume", help="Resume an idempotent production run")
    add_workflow_args(resume, require_date=True, include_overwrite=False)

    backfill = sub.add_parser("backfill", help="Restartable date range backfill")
    backfill.add_argument("--start", type=parse_date, required=True)
    backfill.add_argument("--end", type=parse_date, required=True)
    backfill.add_argument(
        "--step",
        choices=["data", "rankings", "portfolios", "accounting", "all"],
        default="all",
    )
    add_workflow_args(backfill, require_date=False)

    audit = sub.add_parser("audit", help="Audit production artifacts for one date")
    audit.add_argument("--date", type=parse_date, required=True)
    audit.add_argument("--results-repo", type=Path, default=DEFAULT_RESULTS_REPO)
    audit.add_argument("--data-dir", type=Path, default=None)

    research = sub.add_parser("research", help="Isolated strategy research workflows")
    research_sub = research.add_subparsers(dest="command")
    research_gen = research_sub.add_parser(
        "generate-strategies",
        help="Create an isolated research generation workspace",
    )
    research_gen.add_argument("--prompt-id", required=True)
    research_gen.add_argument("--run-id", default=None)
    research_gen.add_argument("--results-repo", type=Path, default=DEFAULT_RESULTS_REPO)
    research_gen.add_argument("--reference-root", type=Path, default=None)

    research_bt = research_sub.add_parser(
        "backtest",
        help="Backtest strategies under research/<prompt_id>/<run_id>",
    )
    research_bt.add_argument("--prompt-id", required=True)
    research_bt.add_argument("--start", type=parse_date, required=True)
    research_bt.add_argument("--end", type=parse_date, required=True)
    research_bt.add_argument("--run-id", default=None)
    research_bt.add_argument("--strategy", default=None)
    research_bt.add_argument("--strategies-dir", type=Path, default=None)
    research_bt.add_argument("--data-dir", type=Path, default=None)
    research_bt.add_argument("--results-repo", type=Path, default=DEFAULT_RESULTS_REPO)
    research_bt.add_argument("--overwrite", action="store_true")

    research_analyze = research_sub.add_parser("analyze", help="Summarize a research run")
    research_analyze.add_argument("--run-id", required=True)
    research_analyze.add_argument("--results-repo", type=Path, default=DEFAULT_RESULTS_REPO)

    research_promote = research_sub.add_parser(
        "promote",
        help="Explicitly copy one research strategy into live strategies/",
    )
    research_promote.add_argument("--run-id", required=True)
    research_promote.add_argument("--strategy-id", required=True)
    research_promote.add_argument("--results-repo", type=Path, default=DEFAULT_RESULTS_REPO)
    research_promote.add_argument("--overwrite", action="store_true")

    stage1 = sub.add_parser("stage1", help="Prompt and strategy artifacts")
    stage1_sub = stage1.add_subparsers(dest="command")

    stage1_sub.add_parser("list-prompts", help="List prompt artifacts")

    list_strategies = stage1_sub.add_parser("list-strategies", help="List strategies")
    list_strategies.add_argument("--prompt-id", default=None)

    validate_strategies = stage1_sub.add_parser(
        "validate-strategies",
        help="Import strategy modules and report syntax/interface failures",
    )
    validate_strategies.add_argument("--prompt-id", default=None)

    migrate = stage1_sub.add_parser(
        "migrate-cached-strategies",
        help="One-way import of cached strategy folders",
    )
    migrate.add_argument("--source-dir", type=Path, required=True)
    migrate.add_argument("--prompt-id", required=True)
    migrate.add_argument("--glob", default="*")
    migrate.add_argument("--overwrite", action="store_true")

    copy_prompt = stage1_sub.add_parser("copy-prompt", help="Copy a prompt into prompts/")
    copy_prompt.add_argument("--source-prompt", type=Path, required=True)
    copy_prompt.add_argument("--prompt-id", required=True)
    copy_prompt.add_argument("--overwrite", action="store_true")

    stage2 = sub.add_parser("stage2", help="Market data and frozen rankings")
    stage2_sub = stage2.add_subparsers(dest="command")

    build_data = stage2_sub.add_parser(
        "build-data",
        help="Build field-level parquets from the seeded wide raw CSV",
    )
    build_data.add_argument("--raw-csv", type=Path, required=True)
    build_data.add_argument("--output-dir", type=Path, required=True)

    universe = stage2_sub.add_parser(
        "download-universe",
        help="Download and cache the S&P 500 universe for a date",
    )
    universe.add_argument("--date", type=parse_date, required=True)
    universe.add_argument("--results-repo", type=Path, default=DEFAULT_RESULTS_REPO)
    universe.add_argument("--overwrite", action="store_true")

    daily_csv = stage2_sub.add_parser(
        "download-daily-csv",
        help="Download and cache one daily OHLCV CSV plus its universe list",
    )
    daily_csv.add_argument("--date", type=parse_date, required=True)
    daily_csv.add_argument("--results-repo", type=Path, default=DEFAULT_RESULTS_REPO)
    daily_csv.add_argument("--overwrite", action="store_true")

    merge_data = stage2_sub.add_parser(
        "merge-data",
        help="Merge downloaded daily CSVs into field-level parquets",
    )
    merge_data.add_argument("--results-repo", type=Path, default=DEFAULT_RESULTS_REPO)
    merge_data.add_argument("--output-dir", type=Path, default=None)

    verify_data = stage2_sub.add_parser(
        "verify-merge",
        help="Verify downloaded daily CSV values are present in parquets",
    )
    verify_data.add_argument("--date", type=parse_date, default=None)
    verify_data.add_argument("--results-repo", type=Path, default=DEFAULT_RESULTS_REPO)
    verify_data.add_argument("--data-dir", type=Path, default=None)

    refresh_data = stage2_sub.add_parser(
        "refresh-data",
        help="Download universe, download daily CSV, then merge into parquets",
    )
    refresh_data.add_argument("--date", type=parse_date, required=True)
    refresh_data.add_argument("--results-repo", type=Path, default=DEFAULT_RESULTS_REPO)
    refresh_data.add_argument("--output-dir", type=Path, default=None)
    refresh_data.add_argument("--overwrite", action="store_true")

    rankings = stage2_sub.add_parser(
        "generate-rankings",
        help="Run strategy code and freeze ranking artifacts",
    )
    rankings.add_argument("--date", type=parse_date, default=None)
    rankings.add_argument("--start", type=parse_date, default=None)
    rankings.add_argument("--end", type=parse_date, default=None)
    rankings.add_argument("--prompt-id", default=None)
    rankings.add_argument("--strategy", default=None)
    rankings.add_argument("--data-dir", type=Path, required=True)
    rankings.add_argument("--results-repo", type=Path, default=DEFAULT_RESULTS_REPO)
    rankings.add_argument("--strategies-dir", type=Path, default=STRATEGIES_DIR)
    rankings.add_argument("--overwrite", action="store_true")

    stage3 = sub.add_parser("stage3", help="Accounting and metrics")
    stage3_sub = stage3.add_subparsers(dest="command")

    accounting = stage3_sub.add_parser(
        "update-accounting",
        help="Compute realized PnL from frozen portfolios",
    )
    accounting.add_argument("--ranking-date", type=parse_date, default=None)
    accounting.add_argument("--through", type=parse_date, default=None)
    accounting.add_argument("--data-dir", type=Path, default=None)
    accounting.add_argument("--results-repo", type=Path, default=DEFAULT_RESULTS_REPO)
    accounting.add_argument(
        "--strict-universe",
        action="store_true",
        help="Require an exact data/universe/YYYYMMDD.txt file for each ranking date",
    )
    accounting.add_argument(
        "--rebuild-portfolios",
        action="store_true",
        help="Rebuild Stage 3 portfolio artifacts from rankings before accounting",
    )

    portfolios = stage3_sub.add_parser(
        "build-portfolios",
        help="Build frozen portfolio artifacts from rankings and S&P universe",
    )
    portfolios.add_argument("--ranking-date", type=parse_date, default=None)
    portfolios.add_argument("--through", type=parse_date, default=None)
    portfolios.add_argument("--data-dir", type=Path, default=None)
    portfolios.add_argument("--results-repo", type=Path, default=DEFAULT_RESULTS_REPO)
    portfolios.add_argument("--strict-universe", action="store_true")
    portfolios.add_argument("--overwrite", action="store_true")

    metrics = stage3_sub.add_parser("build-metrics", help="Build latest metrics")
    metrics.add_argument("--as-of", type=parse_date, default=None)
    metrics.add_argument("--results-repo", type=Path, default=DEFAULT_RESULTS_REPO)

    leaderboard = stage3_sub.add_parser(
        "build-leaderboard",
        help="Build CSV, Markdown, and HTML leaderboard files",
    )
    leaderboard.add_argument("--results-repo", type=Path, default=DEFAULT_RESULTS_REPO)

    args = parser.parse_args(argv)
    if args.stage is None:
        parser.print_help()
        return 2

    if args.stage == "daily-run":
        return run_daily_command(args)
    if args.stage == "resume":
        return run_resume_command(args)
    if args.stage == "backfill":
        return run_backfill_command(args)
    if args.stage == "audit":
        return run_audit_command(args)
    if args.stage == "research":
        return run_research(args, research)
    if args.stage == "stage1":
        return run_stage1(args, stage1)
    if args.stage == "stage2":
        return run_stage2(args, stage2)
    if args.stage == "stage3":
        return run_stage3(args, stage3)

    parser.print_help()
    return 2


def add_workflow_args(
    parser: argparse.ArgumentParser,
    require_date: bool,
    include_overwrite: bool = True,
) -> None:
    if require_date:
        parser.add_argument("--date", type=parse_date, required=True)
    parser.add_argument("--results-repo", type=Path, default=DEFAULT_RESULTS_REPO)
    parser.add_argument("--data-dir", type=Path, default=None)
    parser.add_argument("--prompt-id", default=None)
    parser.add_argument("--strategy", default=None)
    parser.add_argument("--strategies-dir", type=Path, default=STRATEGIES_DIR)
    if include_overwrite:
        parser.add_argument("--overwrite", action="store_true")
    parser.add_argument(
        "--skip-download",
        action="store_true",
        help="Use existing data/raw/daily and data/universe artifacts",
    )
    parser.add_argument("--dry-run", action="store_true")


def run_daily_command(args: argparse.Namespace) -> int:
    from agentstockbenchmark.workflow import run_daily

    report = run_daily(
        run_date=args.date,
        results_repo=args.results_repo,
        data_dir=args.data_dir,
        prompt_id=args.prompt_id,
        strategy_selector=args.strategy,
        strategies_dir=args.strategies_dir,
        overwrite=args.overwrite,
        skip_download=args.skip_download,
        dry_run=args.dry_run,
    )
    print(f"{date_id(args.date)}\t{report['status']}")
    for step in report.get("steps", []):
        print(f"{step['name']}\t{step['status']}")
    if report.get("planned_steps"):
        for step in report["planned_steps"]:
            print(f"planned\t{step}")
    return 0


def run_resume_command(args: argparse.Namespace) -> int:
    from agentstockbenchmark.workflow import resume_daily

    report = resume_daily(
        run_date=args.date,
        results_repo=args.results_repo,
        data_dir=args.data_dir,
        prompt_id=args.prompt_id,
        strategy_selector=args.strategy,
        strategies_dir=args.strategies_dir,
        skip_download=args.skip_download,
        dry_run=args.dry_run,
    )
    print(f"{date_id(args.date)}\t{report['status']}")
    for step in report.get("steps", []):
        print(f"{step['name']}\t{step['status']}")
    if report.get("planned_steps"):
        for step in report["planned_steps"]:
            print(f"planned\t{step}")
    return 0


def run_backfill_command(args: argparse.Namespace) -> int:
    from agentstockbenchmark.workflow import backfill

    report = backfill(
        start=args.start,
        end=args.end,
        step=args.step,
        results_repo=args.results_repo,
        data_dir=args.data_dir,
        prompt_id=args.prompt_id,
        strategy_selector=args.strategy,
        strategies_dir=args.strategies_dir,
        overwrite=args.overwrite,
        skip_download=args.skip_download,
        dry_run=args.dry_run,
    )
    print(f"{date_id(args.start)}..{date_id(args.end)}\t{report['step']}")
    dates = report.get("dates", {})
    if isinstance(dates, dict):
        for day, status in dates.items():
            print(f"{day}\t{status}")
    elif isinstance(dates, list):
        for day in dates:
            print(f"planned\t{day}")
    return 0


def run_audit_command(args: argparse.Namespace) -> int:
    from agentstockbenchmark.audit import audit_date

    report = audit_date(
        run_date=args.date,
        results_repo=args.results_repo,
        data_dir=args.data_dir,
    )
    print(f"{report['audit_date']}\t{report['status']}")
    print(f"rankings\t{report['counts']['rankings']}")
    print(f"portfolios\t{report['counts']['portfolios']}")
    return 0


def run_research(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    if args.command == "generate-strategies":
        from agentstockbenchmark.research import generate_strategies_workspace

        run_dir = generate_strategies_workspace(
            prompt_id=args.prompt_id,
            results_repo=args.results_repo,
            run_id=args.run_id,
            reference_root=args.reference_root,
        )
        print(run_dir)
        return 0

    if args.command == "backtest":
        from agentstockbenchmark.research import research_backtest
        from agentstockbenchmark.workflow import default_data_dir

        data_dir = args.data_dir or default_data_dir(args.results_repo)
        run_dir = research_backtest(
            prompt_id=args.prompt_id,
            start=args.start,
            end=args.end,
            data_dir=data_dir,
            results_repo=args.results_repo,
            strategies_dir=args.strategies_dir,
            run_id=args.run_id,
            strategy_selector=args.strategy,
            overwrite=args.overwrite,
        )
        print(run_dir)
        return 0

    if args.command == "analyze":
        from agentstockbenchmark.research import analyze_research_run

        path = analyze_research_run(args.run_id, args.results_repo)
        print(path)
        return 0

    if args.command == "promote":
        from agentstockbenchmark.research import promote_research_strategy

        path = promote_research_strategy(
            run_id=args.run_id,
            strategy_id=args.strategy_id,
            results_repo=args.results_repo,
            overwrite=args.overwrite,
        )
        print(path)
        return 0

    parser.print_help()
    return 2


def run_stage1(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    if args.command == "list-prompts":
        from agentstockbenchmark.stage1.prompts import list_prompts

        prompts = list_prompts()
        for prompt in prompts:
            print(f"{prompt.prompt_id}\t{prompt.path}")
        print(f"{len(prompts)} prompts")
        return 0

    if args.command == "list-strategies":
        from agentstockbenchmark.stage1.strategies import list_strategies

        strategies = list_strategies(prompt_id=args.prompt_id)
        for strategy in strategies:
            print(f"{strategy.strategy_id}\t{strategy.path}")
        print(f"{len(strategies)} strategies")
        return 0

    if args.command == "validate-strategies":
        from agentstockbenchmark.stage1.strategies import validate_strategy_imports

        statuses = validate_strategy_imports(prompt_id=args.prompt_id)
        failed = 0
        for strategy_id, status in statuses.items():
            print(f"{strategy_id}\t{status}")
            if status != "PASS":
                failed += 1
        print(f"{len(statuses) - failed}/{len(statuses)} strategies import cleanly")
        return 1 if failed else 0

    if args.command == "copy-prompt":
        from agentstockbenchmark.stage1.migration import copy_prompt

        dest = copy_prompt(
            source_prompt=args.source_prompt,
            prompt_id=args.prompt_id,
            overwrite=args.overwrite,
        )
        print(dest)
        return 0

    if args.command == "migrate-cached-strategies":
        from agentstockbenchmark.stage1.migration import migrate_cached_strategies

        migrated = migrate_cached_strategies(
            source_dir=args.source_dir,
            prompt_id=args.prompt_id,
            glob_pattern=args.glob,
            overwrite=args.overwrite,
        )
        for path in migrated:
            print(path)
        print(f"{len(migrated)} strategies migrated")
        return 0

    parser.print_help()
    return 2


def run_stage2(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    if args.command == "build-data":
        from agentstockbenchmark.stage2.market_data import build_parquets_from_wide_csv

        written = build_parquets_from_wide_csv(args.raw_csv, args.output_dir)
        for field, path in written.items():
            print(f"{field}\t{path}")
        return 0

    if args.command == "download-universe":
        from agentstockbenchmark.stage2.market_data import download_universe

        print(download_universe(args.date, args.results_repo, args.overwrite))
        return 0

    if args.command == "download-daily-csv":
        from agentstockbenchmark.stage2.market_data import download_daily_csv

        csv_path, universe_path = download_daily_csv(
            args.date,
            args.results_repo,
            args.overwrite,
        )
        print(f"daily_csv\t{csv_path}")
        print(f"universe\t{universe_path}")
        return 0

    if args.command == "merge-data":
        from agentstockbenchmark.stage2.market_data import merge_daily_csvs_into_parquets

        written = merge_daily_csvs_into_parquets(args.results_repo, args.output_dir)
        for field, path in written.items():
            print(f"{field}\t{path}")
        return 0

    if args.command == "verify-merge":
        from agentstockbenchmark.stage2.market_data import verify_daily_merge

        report = verify_daily_merge(args.results_repo, args.data_dir, args.date)
        for date in report["dates_checked"]:
            print(f"date\t{date}")
        print(f"rows_checked\t{report['rows_checked']}")
        print(f"values_checked\t{report['values_checked']}")
        print(f"null_values_encoded\t{report['null_values_encoded']}")
        print("status\tPASS")
        return 0

    if args.command == "refresh-data":
        from agentstockbenchmark.stage2.market_data import refresh_daily_data

        written = refresh_daily_data(
            args.date,
            args.results_repo,
            args.output_dir,
            args.overwrite,
        )
        for kind, path in written.items():
            print(f"{kind}\t{path}")
        return 0

    if args.command == "generate-rankings":
        from agentstockbenchmark.stage2.rankings import generate_rankings

        start, end = resolve_date_range(args.date, args.start, args.end)
        report = generate_rankings(
            start=start,
            end=end,
            data_dir=args.data_dir,
            results_repo=args.results_repo,
            prompt_id=args.prompt_id,
            strategy_selector=args.strategy,
            strategies_dir=args.strategies_dir,
            overwrite=args.overwrite,
        )
        for date, statuses in report.items():
            passed = sum(1 for status in statuses.values() if status == "PASS")
            print(f"{date}: {passed}/{len(statuses)} PASS")
            for strategy_id, status in statuses.items():
                print(f"  {strategy_id}: {status}")
        return 0

    parser.print_help()
    return 2


def run_stage3(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    if args.command == "build-portfolios":
        from agentstockbenchmark.stage3.portfolio import build_portfolios

        counts = build_portfolios(
            results_repo=args.results_repo,
            ranking_date=args.ranking_date,
            through=args.through,
            data_dir=args.data_dir,
            strict_universe=args.strict_universe,
            overwrite=args.overwrite,
        )
        for date, count in counts.items():
            print(f"{date}: {count} portfolios built")
        return 0

    if args.command == "update-accounting":
        from agentstockbenchmark.stage3.accounting import update_accounting

        counts = update_accounting(
            results_repo=args.results_repo,
            data_dir=args.data_dir,
            ranking_date=args.ranking_date,
            through=args.through,
            strict_universe=args.strict_universe,
            rebuild_portfolios=args.rebuild_portfolios,
        )
        for date, count in counts.items():
            print(f"{date}: {count} strategies evaluated")
        return 0

    if args.command == "build-metrics":
        from agentstockbenchmark.stage3.metrics import build_metrics

        df = build_metrics(results_repo=args.results_repo, as_of=args.as_of)
        if df.empty:
            print("no metrics")
        else:
            print(df.to_string(index=False))
        return 0

    if args.command == "build-leaderboard":
        from agentstockbenchmark.stage3.leaderboard import build_leaderboard

        paths = build_leaderboard(results_repo=args.results_repo)
        for kind, path in paths.items():
            print(f"{kind}\t{path}")
        return 0

    parser.print_help()
    return 2


def resolve_date_range(
    date: dt.date | None,
    start: dt.date | None,
    end: dt.date | None,
) -> tuple[dt.date, dt.date]:
    if date is not None:
        return date, date
    if start is not None and end is not None:
        return start, end
    raise ValueError("provide --date or both --start and --end")


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
