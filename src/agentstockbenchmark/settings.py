from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RESULTS_REPO = Path.home() / "bmr_codex"

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
