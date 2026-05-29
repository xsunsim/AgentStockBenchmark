from __future__ import annotations

import os
from pathlib import Path

_cwd = Path.cwd()
_env_root = os.environ.get("ASB_PROJECT_ROOT")

DEFAULT_RESULTS_REPO = Path(os.environ.get("ASB_RESULTS_REPO", Path.home() / "bmr_codex"))

if _env_root:
    PROJECT_ROOT = Path(_env_root)
elif (_cwd / "prompts").exists() and (_cwd / "strategies").exists():
    PROJECT_ROOT = _cwd
else:
    # Try to find common clone locations to be helpful
    _home_repo = Path.home() / "AgentStockBenchmark"
    _home_repo2 = Path.home() / "AgentStockBench" / "AgentStockBenchmark"
    if _home_repo.exists() and (_home_repo / "prompts").exists():
        PROJECT_ROOT = _home_repo
    elif _home_repo2.exists() and (_home_repo2 / "prompts").exists():
        PROJECT_ROOT = _home_repo2
    else:
        # Fallback to the results repo for zero-install users!
        PROJECT_ROOT = DEFAULT_RESULTS_REPO

PROMPTS_DIR = PROJECT_ROOT / "prompts"
STRATEGIES_DIR = PROJECT_ROOT / "strategies"

OHLCV_FIELDS = ("open", "high", "low", "close", "volume")
RAW_CSV_FIELD_NAMES = {
    "Open": "open",
    "High": "high",
    "Low": "low",
    "Close": "close",
    "Volume": "volume",
}

POSITION_MAX_DOLLARS = 250.0
MIN_HISTORY_DAYS = 21
