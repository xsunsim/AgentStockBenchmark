from __future__ import annotations

import datetime as dt
import shutil
from pathlib import Path

from agentstockbenchmark.dates import date_id
from agentstockbenchmark.io import atomic_write_json, atomic_write_text, sha256_file
from agentstockbenchmark.manifests import utc_now
from agentstockbenchmark.settings import (
    DEFAULT_RESULTS_REPO,
    STRATEGIES_DIR,
)
from agentstockbenchmark.stage1.prompts import load_prompt
from agentstockbenchmark.stage2.rankings import generate_rankings
from agentstockbenchmark.stage3.accounting import update_accounting
from agentstockbenchmark.stage3.leaderboard import build_leaderboard
from agentstockbenchmark.stage3.metrics import build_metrics
from agentstockbenchmark.stage3.portfolio import build_portfolios


def new_run_id() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def research_run_dir(
    results_repo: Path,
    prompt_id: str,
    run_id: str,
) -> Path:
    return results_repo / "research" / prompt_id / run_id


def generate_strategies_workspace(
    prompt_id: str,
    results_repo: Path = DEFAULT_RESULTS_REPO,
    run_id: str | None = None,
    reference_root: Path | None = None,
) -> Path:
    run_id = run_id or new_run_id()
    run_dir = research_run_dir(results_repo, prompt_id, run_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    strategy_root = run_dir / "strategies" / prompt_id
    strategy_root.mkdir(parents=True, exist_ok=True)

    prompt_text = load_prompt(prompt_id)
    atomic_write_text(run_dir / "prompt.txt", prompt_text)
    copied_refs = copy_reference_prompts(reference_root=reference_root)
    payload = {
        "schema_version": 1,
        "run_type": "generate-strategies",
        "status": "READY_FOR_AGENT_GENERATION",
        "prompt_id": prompt_id,
        "run_id": run_id,
        "created_at_utc": utc_now(),
        "workspace": str(run_dir),
        "strategy_root": str(strategy_root),
        "prompt_sha256": sha256_file(run_dir / "prompt.txt"),
        "reference_prompts": [str(path) for path in copied_refs],
        "note": (
            "Strategy generation is intentionally isolated under research/. "
            "Place generated strategy.py files under "
            "strategies/<prompt_id>/<strategy_slug>/ before backtesting or "
            "promotion."
        ),
    }
    atomic_write_json(run_dir / "run.json", payload)
    return run_dir


def research_backtest(
    prompt_id: str,
    start: dt.date,
    end: dt.date,
    data_dir: Path,
    results_repo: Path = DEFAULT_RESULTS_REPO,
    strategies_dir: Path | None = None,
    run_id: str | None = None,
    strategy_selector: str | None = None,
    overwrite: bool = False,
) -> Path:
    run_id = run_id or new_run_id()
    run_dir = research_run_dir(results_repo, prompt_id, run_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    copy_universe_files(results_repo, run_dir, start, end)
    strategy_root = resolve_research_strategies_dir(
        run_dir=run_dir,
        prompt_id=prompt_id,
        explicit_strategies_dir=strategies_dir,
    )

    report = generate_rankings(
        start=start,
        end=end,
        data_dir=data_dir,
        results_repo=run_dir,
        prompt_id=prompt_id,
        strategy_selector=strategy_selector,
        strategies_dir=strategy_root,
        overwrite=overwrite,
    )
    portfolios = build_portfolios(
        results_repo=run_dir,
        through=end,
        data_dir=data_dir,
        overwrite=overwrite,
    )
    accounting = update_accounting(
        results_repo=run_dir,
        data_dir=data_dir,
        through=end,
    )
    metrics = build_metrics(results_repo=run_dir, as_of=end)
    leaderboard = {}
    if not metrics.empty:
        leaderboard = {
            key: str(path) for key, path in build_leaderboard(run_dir).items()
        }

    payload = {
        "schema_version": 1,
        "run_type": "backtest",
        "status": "PASS",
        "prompt_id": prompt_id,
        "run_id": run_id,
        "start": date_id(start),
        "end": date_id(end),
        "created_at_utc": utc_now(),
        "strategies_dir": str(strategy_root),
        "rankings": report,
        "portfolios": portfolios,
        "accounting": accounting,
        "metrics_rows": int(len(metrics)),
        "leaderboard": leaderboard,
        "live_paths_written": [],
    }
    atomic_write_json(run_dir / "run.json", payload)
    return run_dir


def analyze_research_run(
    run_id: str,
    results_repo: Path = DEFAULT_RESULTS_REPO,
) -> Path:
    run_dir = find_research_run(results_repo, run_id)
    metrics_path = run_dir / "accounting" / "latest_metrics.csv"
    summary: dict[str, object] = {
        "schema_version": 1,
        "run_id": run_id,
        "analyzed_at_utc": utc_now(),
        "run_dir": str(run_dir),
        "has_metrics": metrics_path.exists(),
    }
    if metrics_path.exists():
        import pandas as pd

        metrics = pd.read_csv(metrics_path)
        summary["n_strategies"] = int(len(metrics))
        if not metrics.empty:
            top = metrics.iloc[0].to_dict()
            summary["top_strategy_id"] = str(top["strategy_id"])
            summary["top_sharpe"] = float(top["sharpe"])
            summary["top_cumulative_pnl"] = float(top["cumulative_pnl"])

    out_path = run_dir / "analysis.json"
    atomic_write_json(out_path, summary)
    return out_path


def promote_research_strategy(
    run_id: str,
    strategy_id: str,
    results_repo: Path = DEFAULT_RESULTS_REPO,
    overwrite: bool = False,
) -> Path:
    run_dir = find_research_run(results_repo, run_id)
    run_prompt_id = run_dir.parent.name
    slug = strategy_id
    if strategy_id.startswith(f"{run_prompt_id}__"):
        slug = strategy_id[len(run_prompt_id) + 2 :]

    source = run_dir / "strategies" / run_prompt_id / slug / "strategy.py"
    if not source.exists():
        legacy_source = run_dir / "strategies" / slug / "strategy.py"
        if legacy_source.exists():
            source = legacy_source
    if not source.exists():
        raise FileNotFoundError(
            "research promotion requires a strategy produced by the research run: "
            f"{source}"
        )

    dest_dir = STRATEGIES_DIR / run_prompt_id / slug
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "strategy.py"
    if dest.exists() and not overwrite:
        return dest
    shutil.copy2(source, dest)

    metadata = {
        "schema_version": 1,
        "prompt_id": run_prompt_id,
        "strategy_slug": slug,
        "strategy_id": f"{run_prompt_id}__{slug}",
        "promoted_from_run": run_id,
        "promoted_at_utc": utc_now(),
        "strategy_sha256": sha256_file(dest),
    }
    atomic_write_json(dest_dir / "strategy.json", metadata)
    return dest


def copy_reference_prompts(
    reference_root: Path | None = None,
    dest_dir: Path | None = None,
) -> list[Path]:
    reference_root = reference_root or (Path.home() / "bm")
    dest_dir = dest_dir or (Path.home() / "bm_codex" / "prompts" / "reference")
    if not reference_root.exists():
        return []

    copied: list[Path] = []
    for source in sorted(reference_root.glob("PROMPT*.md")):
        dest = dest_dir / source.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists() or sha256_file(source) != sha256_file(dest):
            shutil.copy2(source, dest)
        copied.append(dest)

    for source in sorted((reference_root / "prompt_history").glob("*/prompt.txt")):
        dest = dest_dir / "prompt_history" / source.parent.name / "prompt.txt"
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists() or sha256_file(source) != sha256_file(dest):
            shutil.copy2(source, dest)
        copied.append(dest)
    return copied


def resolve_research_strategies_dir(
    run_dir: Path,
    prompt_id: str,
    explicit_strategies_dir: Path | None,
) -> Path:
    if explicit_strategies_dir is not None:
        return explicit_strategies_dir

    run_strategy_root = run_dir / "strategies"
    prompt_strategy_root = run_strategy_root / prompt_id
    if any(prompt_strategy_root.glob("*/strategy.py")):
        return run_strategy_root

    return STRATEGIES_DIR


def copy_universe_files(
    source_results_repo: Path,
    run_dir:Path,
    start: dt.date,
    end: dt.date,
) -> None:
    source_dir = source_results_repo / "data" / "universe"
    if not source_dir.exists():
        return

    dest_dir = run_dir / "data" / "universe"
    dest_dir.mkdir(parents=True, exist_ok=True)
    for source in sorted(source_dir.glob("*.txt")):
        try:
            day = dt.datetime.strptime(source.stem, "%Y%m%d").date()
        except ValueError:
            continue
        if start <= day <= end:
            shutil.copy2(source, dest_dir / source.name)


def find_research_run(results_repo: Path, run_id: str) -> Path:
    root = results_repo / "research"
    matches = sorted(path for path in root.glob(f"*/{run_id}") if path.is_dir())
    if not matches:
        raise FileNotFoundError(f"research run not found: {run_id}")
    if len(matches) > 1:
        raise ValueError(f"research run id is ambiguous: {run_id}")
    return matches[0]
