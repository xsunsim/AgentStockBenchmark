from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Literal

from agentstockbenchmark.audit import audit_date
from agentstockbenchmark.dates import date_id, iter_dates
from agentstockbenchmark.manifests import (
    utc_now,
    write_artifact_manifest,
    write_run_manifest,
    write_strategy_manifest,
)
from agentstockbenchmark.settings import DEFAULT_RESULTS_REPO, STRATEGIES_DIR
from agentstockbenchmark.stage2.market_data import (
    download_daily_csv,
    ensure_cached_daily_from_parquets,
    merge_daily_csvs_into_parquets,
    verify_daily_merge,
)
from agentstockbenchmark.stage2.rankings import generate_rankings
from agentstockbenchmark.stage3.accounting import update_accounting
from agentstockbenchmark.stage3.leaderboard import build_leaderboard
from agentstockbenchmark.stage3.metrics import build_metrics
from agentstockbenchmark.stage3.portfolio import build_portfolios


BackfillStep = Literal["data", "rankings", "portfolios", "accounting", "all"]


def default_data_dir(results_repo: Path) -> Path:
    return results_repo / "data" / "parquet"


def run_daily(
    run_date: dt.date,
    results_repo: Path = DEFAULT_RESULTS_REPO,
    data_dir: Path | None = None,
    prompt_id: str | None = None,
    strategy_selector: str | None = None,
    strategies_dir: Path = STRATEGIES_DIR,
    overwrite: bool = False,
    skip_download: bool = False,
    dry_run: bool = False,
) -> dict:
    if data_dir is None:
        data_dir = default_data_dir(results_repo)

    steps: list[dict] = []
    started_at = utc_now()
    if dry_run:
        planned = [
            "download-daily-csv",
            "ensure-cached-daily",
            "merge-data",
            "verify-merge",
            "generate-rankings",
            "build-portfolios",
            "update-accounting",
            "build-metrics",
            "build-leaderboard",
            "audit",
            "write-manifests",
        ]
        if skip_download:
            planned = planned[1:]
        else:
            planned.remove("ensure-cached-daily")
        return {
            "run_date": date_id(run_date),
            "status": "DRY_RUN",
            "planned_steps": planned,
            "results_repo": str(results_repo),
            "data_dir": str(data_dir),
        }

    try:
        if not skip_download:
            csv_path, universe_path = download_daily_csv(
                run_date,
                results_repo,
                overwrite=overwrite,
            )
            steps.append(
                _step(
                    "download-daily-csv",
                    "PASS",
                    daily_csv=str(csv_path),
                    universe=str(universe_path),
                )
            )
        else:
            csv_path, universe_path = ensure_cached_daily_from_parquets(
                run_date,
                results_repo,
                data_dir=data_dir,
                overwrite=overwrite,
            )
            steps.append(
                _step(
                    "ensure-cached-daily",
                    "PASS",
                    daily_csv=str(csv_path),
                    universe=str(universe_path),
                )
            )

        written = merge_daily_csvs_into_parquets(results_repo, data_dir)
        steps.append(
            _step(
                "merge-data",
                "PASS",
                artifacts={field: str(path) for field, path in written.items()},
            )
        )

        merge_report = verify_daily_merge(results_repo, data_dir, date=run_date)
        steps.append(_step("verify-merge", "PASS", report=merge_report))

        rankings_report = generate_rankings(
            start=run_date,
            end=run_date,
            data_dir=data_dir,
            results_repo=results_repo,
            prompt_id=prompt_id,
            strategy_selector=strategy_selector,
            strategies_dir=strategies_dir,
            overwrite=overwrite,
        )
        steps.append(_step("generate-rankings", "PASS", report=rankings_report))

        portfolio_counts = build_portfolios(
            results_repo=results_repo,
            ranking_date=run_date,
            data_dir=data_dir,
            overwrite=overwrite,
        )
        steps.append(_step("build-portfolios", "PASS", counts=portfolio_counts))

        accounting_counts = update_accounting(
            results_repo=results_repo,
            data_dir=data_dir,
            through=run_date,
        )
        steps.append(_step("update-accounting", "PASS", counts=accounting_counts))

        metrics = build_metrics(results_repo=results_repo, as_of=run_date)
        steps.append(_step("build-metrics", "PASS", n_strategies=int(len(metrics))))

        if metrics.empty:
            steps.append(_step("build-leaderboard", "SKIPPED", reason="no metrics"))
        else:
            leaderboard_paths = build_leaderboard(results_repo=results_repo)
            steps.append(
                _step(
                    "build-leaderboard",
                    "PASS",
                    artifacts={
                        kind: str(path) for kind, path in leaderboard_paths.items()
                    },
                )
            )

        write_strategy_manifest(results_repo=results_repo, strategies_dir=strategies_dir)
        artifact_manifest_path = write_artifact_manifest(results_repo, run_date)
        audit_report = audit_date(run_date, results_repo, data_dir)
        steps.append(_step("audit", "PASS", report=audit_report))
        steps.append(
            _step(
                "write-manifests",
                "PASS",
                artifact_manifest=str(artifact_manifest_path),
            )
        )
        status = "PASS"
        error = None
    except Exception as exc:
        status = "FAIL"
        error = str(exc)
        steps.append(_step("error", "FAIL", error=error))
        write_run_manifest(
            results_repo,
            run_date,
            {
                "status": status,
                "started_at_utc": started_at,
                "completed_at_utc": utc_now(),
                "steps": steps,
                "error": error,
            },
        )
        raise

    run_manifest = {
        "status": status,
        "started_at_utc": started_at,
        "completed_at_utc": utc_now(),
        "results_repo": str(results_repo),
        "data_dir": str(data_dir),
        "prompt_id": prompt_id,
        "strategy_selector": strategy_selector,
        "steps": steps,
        "error": error,
    }
    write_run_manifest(results_repo, run_date, run_manifest)
    return run_manifest


def resume_daily(
    run_date: dt.date,
    results_repo: Path = DEFAULT_RESULTS_REPO,
    data_dir: Path | None = None,
    prompt_id: str | None = None,
    strategy_selector: str | None = None,
    strategies_dir: Path = STRATEGIES_DIR,
    skip_download: bool = False,
    dry_run: bool = False,
) -> dict:
    return run_daily(
        run_date=run_date,
        results_repo=results_repo,
        data_dir=data_dir,
        prompt_id=prompt_id,
        strategy_selector=strategy_selector,
        strategies_dir=strategies_dir,
        overwrite=False,
        skip_download=skip_download,
        dry_run=dry_run,
    )


def backfill(
    start: dt.date,
    end: dt.date,
    step: BackfillStep,
    results_repo: Path = DEFAULT_RESULTS_REPO,
    data_dir: Path | None = None,
    prompt_id: str | None = None,
    strategy_selector: str | None = None,
    strategies_dir: Path = STRATEGIES_DIR,
    overwrite: bool = False,
    skip_download: bool = False,
    dry_run: bool = False,
) -> dict:
    if data_dir is None:
        data_dir = default_data_dir(results_repo)

    if dry_run:
        return {
            "status": "DRY_RUN",
            "start": date_id(start),
            "end": date_id(end),
            "step": step,
            "dates": [date_id(day) for day in iter_dates(start, end)],
        }

    report: dict[str, object] = {"step": step, "dates": {}}
    if step == "all":
        for day in iter_dates(start, end):
            report["dates"][date_id(day)] = run_daily(
                run_date=day,
                results_repo=results_repo,
                data_dir=data_dir,
                prompt_id=prompt_id,
                strategy_selector=strategy_selector,
                strategies_dir=strategies_dir,
                overwrite=overwrite,
                skip_download=skip_download,
            )["status"]
        return report

    if step == "data":
        for day in iter_dates(start, end):
            if not skip_download:
                download_daily_csv(day, results_repo, overwrite=overwrite)
            merge_daily_csvs_into_parquets(results_repo, data_dir)
            verify_daily_merge(results_repo, data_dir, date=day)
            report["dates"][date_id(day)] = "PASS"
        return report

    if step == "rankings":
        report["dates"] = generate_rankings(
            start=start,
            end=end,
            data_dir=data_dir,
            results_repo=results_repo,
            prompt_id=prompt_id,
            strategy_selector=strategy_selector,
            strategies_dir=strategies_dir,
            overwrite=overwrite,
        )
        return report

    if step == "portfolios":
        counts: dict[str, int] = {}
        for day in iter_dates(start, end):
            counts.update(
                build_portfolios(
                    results_repo=results_repo,
                    ranking_date=day,
                    data_dir=data_dir,
                    overwrite=overwrite,
                )
            )
        report["dates"] = counts
        return report

    if step == "accounting":
        counts: dict[str, int] = {}
        for day in iter_dates(start, end):
            counts.update(
                update_accounting(
                    results_repo=results_repo,
                    data_dir=data_dir,
                    ranking_date=day,
                )
            )
        report["dates"] = counts
        metrics = build_metrics(results_repo=results_repo, as_of=end)
        if not metrics.empty:
            build_leaderboard(results_repo=results_repo)
        return report

    raise ValueError(f"unknown backfill step: {step}")


def _step(name: str, status: str, **details) -> dict:
    return {
        "name": name,
        "status": status,
        "completed_at_utc": utc_now(),
        **details,
    }
