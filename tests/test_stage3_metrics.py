import pandas as pd

from agentstockbenchmark.stage3.metrics import compute_strategy_metrics


def test_compute_strategy_metrics_handles_multiple_days():
    metrics = compute_strategy_metrics(pd.Series([1.0, -0.5, 2.0]))

    assert metrics["n_days"] == 3
    assert metrics["cumulative_pnl"] == 2.5
    assert metrics["win_rate"] == 0.667
