import pandas as pd

from agentstockbenchmark.stage3.portfolio import build_portfolio_book


def test_build_portfolio_book_uses_accounting_universe_and_middle_missing_names():
    ranking = pd.DataFrame(
        [
            {"ticker": "A", "score": 3.0, "strategy_rank": 1},
            {"ticker": "B", "score": 2.0, "strategy_rank": 2},
            {"ticker": "X", "score": 1.0, "strategy_rank": 3},
            {"ticker": "Z", "score": -1.0, "strategy_rank": 4},
        ]
    )

    book = build_portfolio_book(ranking, ["A", "B", "C", "D", "Z"])

    assert [row["ticker"] for row in book.rows] == ["A", "B", "C", "D", "Z"]
    assert [row["ranking_status"] for row in book.rows] == [
        "ranked",
        "ranked",
        "missing",
        "missing",
        "ranked",
    ]
    assert book.n_ranked_in_universe == 3
    assert book.n_ranked_ignored == 1
    assert book.n_missing_rankings == 2
    assert book.rows[2]["position_dollars"] == 0.0
    assert book.rows[3]["position_dollars"] < 0.0


def test_build_portfolio_book_is_dollar_neutral():
    ranking = pd.DataFrame(
        [
            {"ticker": "A", "score": 3.0, "strategy_rank": 1},
            {"ticker": "B", "score": 2.0, "strategy_rank": 2},
            {"ticker": "C", "score": 1.0, "strategy_rank": 3},
        ]
    )

    book = build_portfolio_book(ranking, ["A", "B", "C"])

    assert round(sum(row["position_dollars"] for row in book.rows), 8) == 0.0
    assert book.rows[0]["position_dollars"] == 250.0
    assert book.rows[-1]["position_dollars"] == -250.0
