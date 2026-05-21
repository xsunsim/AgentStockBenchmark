from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

from agentstockbenchmark.dates import date_id
from agentstockbenchmark.io import atomic_write_json, sha256_file
from agentstockbenchmark.settings import DEFAULT_RESULTS_REPO, STRATEGIES_DIR
from agentstockbenchmark.stage1.strategies import list_strategies


def write_strategy_manifest(
    results_repo: Path = DEFAULT_RESULTS_REPO,
    strategies_dir: Path = STRATEGIES_DIR,
) -> Path:
    rows = []
    for ref in list_strategies(strategies_dir=strategies_dir):
        rows.append(
            {
                "prompt_id": ref.prompt_id,
                "strategy_slug": ref.strategy_slug,
                "strategy_id": ref.strategy_id,
                "path": str(ref.path),
                "strategy_sha256": sha256_file(ref.path),
            }
        )

    payload = {
        "schema_version": 1,
        "generated_at_utc": utc_now(),
        "n_strategies": len(rows),
        "strategies": rows,
    }
    path = results_repo / "manifests" / "strategies.json"
    atomic_write_json(path, payload)
    return path


def write_run_manifest(
    results_repo: Path,
    run_date: dt.date,
    payload: dict[str, Any],
) -> Path:
    manifest = {
        "schema_version": 1,
        "run_date": date_id(run_date),
        "generated_at_utc": utc_now(),
        **payload,
    }
    path = results_repo / "manifests" / "runs" / f"{date_id(run_date)}.json"
    atomic_write_json(path, manifest)
    return path


def write_artifact_manifest(results_repo: Path, run_date: dt.date) -> Path:
    entries = []
    for path in collect_artifacts_for_date(results_repo, run_date):
        if not path.exists() or not path.is_file():
            continue
        rel_path = path.relative_to(results_repo).as_posix()
        entries.append(
            {
                "path": rel_path,
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )

    payload = {
        "schema_version": 1,
        "artifact_date": date_id(run_date),
        "generated_at_utc": utc_now(),
        "artifacts": sorted(entries, key=lambda item: item["path"]),
    }
    path = results_repo / "manifests" / "artifacts" / f"{date_id(run_date)}.json"
    atomic_write_json(path, payload)
    return path


def verify_artifact_manifest(results_repo: Path, run_date: dt.date) -> list[str]:
    import json

    manifest_path = (
        results_repo / "manifests" / "artifacts" / f"{date_id(run_date)}.json"
    )
    if not manifest_path.exists():
        return []

    manifest = json.loads(manifest_path.read_text())
    failures = []
    for entry in manifest.get("artifacts", []):
        path = results_repo / entry["path"]
        if not path.exists():
            failures.append(f"missing manifest artifact: {entry['path']}")
            continue
        actual = sha256_file(path)
        if actual != entry["sha256"]:
            failures.append(f"checksum mismatch for {entry['path']}")
    return failures


def collect_artifacts_for_date(results_repo: Path, run_date: dt.date) -> list[Path]:
    did = date_id(run_date)
    paths: list[Path] = [
        results_repo / "data" / "universe" / f"{did}.txt",
        results_repo / "data" / "raw" / "daily" / f"{did}.csv",
    ]

    for root in (results_repo / "rankings" / did, results_repo / "portfolios" / did):
        if not root.exists():
            continue
        paths.extend(path for path in sorted(root.glob("*")) if path.is_file())

    metric_path = results_repo / "accounting" / "metrics" / f"{did}.csv"
    if metric_path.exists():
        paths.append(metric_path)

    return paths


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
