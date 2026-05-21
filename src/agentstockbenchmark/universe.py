from __future__ import annotations

from pathlib import Path

from agentstockbenchmark.dates import parse_date_id


def read_universe_file(path: Path) -> list[str]:
    tickers = {line.strip() for line in path.read_text().splitlines() if line.strip()}
    return sorted(tickers)


def latest_universe_file(universe_dir: Path) -> Path | None:
    if not universe_dir.exists():
        return None

    dated = []
    for path in universe_dir.glob("*.txt"):
        try:
            dated.append((parse_date_id(path.stem), path))
        except ValueError:
            continue
    if not dated:
        return None
    return max(dated, key=lambda item: item[0])[1]
