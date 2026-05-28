from __future__ import annotations

import hashlib
import importlib.util
import json
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Callable

from agentstockbenchmark.settings import STRATEGIES_DIR


@dataclass(frozen=True)
class StrategyRef:
    prompt_id: str
    strategy_slug: str
    path: Path
    metadata_path: Path

    @property
    def strategy_id(self) -> str:
        return f"{self.prompt_id}__{self.strategy_slug}"


def list_strategies(
    strategies_dir: Path = STRATEGIES_DIR,
    prompt_id: str | None = None,
    selector: str | None = None,
) -> list[StrategyRef]:
    if not strategies_dir.exists():
        return []

    import fnmatch

    prompt_dirs = [strategies_dir / prompt_id] if prompt_id else sorted(
        p for p in strategies_dir.iterdir() if p.is_dir()
    )

    strategies: list[StrategyRef] = []
    for prompt_dir in prompt_dirs:
        if not prompt_dir.exists() or not prompt_dir.is_dir():
            continue
        for strategy_dir in sorted(p for p in prompt_dir.iterdir() if p.is_dir()):
            strategy_path = strategy_dir / "strategy.py"
            if strategy_path.exists():
                ref = StrategyRef(
                    prompt_id=prompt_dir.name,
                    strategy_slug=strategy_dir.name,
                    path=strategy_path,
                    metadata_path=strategy_dir / "strategy.json",
                )
                
                if selector:
                    # Match against ID or slug using glob pattern
                    if fnmatch.fnmatch(ref.strategy_id, selector) or fnmatch.fnmatch(ref.strategy_slug, selector):
                        strategies.append(ref)
                else:
                    strategies.append(ref)
    return strategies


def find_strategy(
    selector: str,
    strategies_dir: Path = STRATEGIES_DIR,
    prompt_id: str | None = None,
) -> StrategyRef:
    # Use exact match first, then fall back to glob if no exact match found
    # but the glob implementation in list_strategies already covers both.
    # However, find_strategy usually implies finding a SINGLE strategy.
    
    matches = list_strategies(strategies_dir=strategies_dir, prompt_id=prompt_id, selector=selector)

    if not matches:
        raise ValueError(f"strategy not found: {selector}")
    if len(matches) > 1:
        names = ", ".join(ref.strategy_id for ref in matches)
        raise ValueError(f"strategy selector {selector!r} is ambiguous. Matches found: {names}")
    return matches[0]


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_strategy(path: Path) -> Callable:
    module = _load_module_from_path(path)
    if not hasattr(module, "generate_signal"):
        raise AttributeError(f"{path} does not define generate_signal(data)")
    fn = module.generate_signal
    if not callable(fn):
        raise TypeError(f"{path}: generate_signal is not callable")
    return fn


def load_metadata(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def validate_strategy_imports(
    strategies_dir: Path = STRATEGIES_DIR,
    prompt_id: str | None = None,
) -> dict[str, str]:
    statuses: dict[str, str] = {}
    for ref in list_strategies(strategies_dir=strategies_dir, prompt_id=prompt_id):
        try:
            load_strategy(ref.path)
            statuses[ref.strategy_id] = "PASS"
        except Exception as exc:
            statuses[ref.strategy_id] = f"ERROR: {exc}"
    return statuses


def _load_module_from_path(path: Path) -> ModuleType:
    module_name = "agentstockbenchmark_strategy_" + hashlib.sha1(
        str(path).encode("utf-8")
    ).hexdigest()
    spec = importlib.util.spec_from_file_location(module_name, str(path))
    if spec is None or spec.loader is None:
        raise ImportError(f"could not import strategy from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
