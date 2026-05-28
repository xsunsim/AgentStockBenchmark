import sys
import os
import json

# Add src to sys.path
sys.path.append(os.path.abspath("src"))

from agentstockbenchmark.mcp_server.server import (
    list_active_prompts,
    list_available_strategies,
    get_leaderboard,
    refresh_market_data,
    run_strategy_on_date,
    get_top_positions,
    create_research_workspace,
    run_research_backtest,
    analyze_results
)

def run_test(name, func, *args, **kwargs):
    print(f"Testing {name}...")
    try:
        result = func(*args, **kwargs)
        print(f"Result: {json.dumps(result, indent=2, default=str)}")
    except Exception as e:
        print(f"Exception: {str(e)}")
    print("-" * 20)

if __name__ == "__main__":
    # 1. list_active_prompts()
    run_test("list_active_prompts", list_active_prompts)

    # 2. list_available_strategies(prompt_id="20260517")
    run_test("list_available_strategies(prompt_id='20260517')", list_available_strategies, prompt_id="20260517")

    # 3. list_available_strategies(prompt_id="INVALID_ID")
    run_test("list_available_strategies(prompt_id='INVALID_ID')", list_available_strategies, prompt_id="INVALID_ID")

    # 4. get_leaderboard()
    run_test("get_leaderboard", get_leaderboard)

    # 5. refresh_market_data(date="20260524") (Note: This is a Sunday)
    run_test("refresh_market_data(date='20260524')", refresh_market_data, date="20260524")

    # 6. run_strategy_on_date(strategy_id="20260517__OpenAI__GPT5_5__LinearNeutral", date="20260527")
    run_test("run_strategy_on_date", run_strategy_on_date, strategy_id="20260517__OpenAI__GPT5_5__LinearNeutral", date="20260527")

    # 7. get_top_positions(strategy_id="20260517__OpenAI__GPT5_5__LinearNeutral", target_trading_date="20260528")
    run_test("get_top_positions", get_top_positions, strategy_id="20260517__OpenAI__GPT5_5__LinearNeutral", target_trading_date="20260528")

    # 8. create_research_workspace(prompt_id="20260517")
    run_test("create_research_workspace", create_research_workspace, prompt_id="20260517")

    # 9. run_research_backtest(prompt_id="20260517", start_date="20260501", end_date="20260507", strategy_selector="*Gemini*")
    run_test("run_research_backtest", run_research_backtest, prompt_id="20260517", start_date="20260501", end_date="20260507", strategy_selector="*Gemini*")

    # 10. analyze_results(run_id="NON_EXISTENT")
    run_test("analyze_results", analyze_results, run_id="NON_EXISTENT")
