from __future__ import annotations

import re
import shutil
from pathlib import Path

from agentstockbenchmark.io import atomic_write_json, atomic_write_text
from agentstockbenchmark.settings import PROMPTS_DIR, STRATEGIES_DIR
from agentstockbenchmark.stage1.strategies import file_sha256


VERSION_SUFFIX_RE = re.compile(r"_(?:v\d+|\d{6,8})$")


def strategy_slug_from_cache_name(name: str) -> str:
    return VERSION_SUFFIX_RE.sub("", name)


def copy_prompt(
    source_prompt: Path,
    prompt_id: str,
    prompts_dir: Path = PROMPTS_DIR,
    overwrite: bool = False,
) -> Path:
    if not source_prompt.exists():
        raise FileNotFoundError(f"prompt source not found: {source_prompt}")

    dest_dir = prompts_dir / prompt_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "prompt.md"
    if dest.exists() and not overwrite:
        return dest
    atomic_write_text(dest, source_prompt.read_text())
    return dest


def migrate_cached_strategies(
    source_dir: Path,
    prompt_id: str,
    strategies_dir: Path = STRATEGIES_DIR,
    glob_pattern: str = "*",
    overwrite: bool = False,
) -> list[Path]:
    if not source_dir.exists():
        raise FileNotFoundError(f"strategy cache not found: {source_dir}")

    migrated: list[Path] = []
    for cache_dir in sorted(p for p in source_dir.glob(glob_pattern) if p.is_dir()):
        strategy_source = cache_dir / "strategy.py"
        if not strategy_source.exists():
            continue

        slug = strategy_slug_from_cache_name(cache_dir.name)
        dest_dir = strategies_dir / prompt_id / slug
        dest_dir.mkdir(parents=True, exist_ok=True)
        strategy_dest = dest_dir / "strategy.py"

        if overwrite or not strategy_dest.exists():
            shutil.copy2(strategy_source, strategy_dest)

        for optional_name in ("prompt.md", "meta.json"):
            optional_source = cache_dir / optional_name
            optional_dest = dest_dir / optional_name
            if optional_source.exists() and (overwrite or not optional_dest.exists()):
                shutil.copy2(optional_source, optional_dest)

        metadata = {
            "schema_version": 1,
            "prompt_id": prompt_id,
            "strategy_slug": slug,
            "strategy_id": f"{prompt_id}__{slug}",
            "source_cache": str(cache_dir),
            "source_cache_name": cache_dir.name,
            "strategy_sha256": file_sha256(strategy_dest),
        }
        atomic_write_json(dest_dir / "strategy.json", metadata)
        migrated.append(strategy_dest)

    return migrated
