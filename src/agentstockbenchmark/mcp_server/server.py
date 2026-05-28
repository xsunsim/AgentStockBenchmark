from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from agentstockbenchmark.research import (
    generate_strategies_workspace,
    research_backtest,
    analyze_research_run,
    promote_research_strategy,
)
from agentstockbenchmark.workflow import backfill, run_daily
from agentstockbenchmark.dates import parse_date, date_id
from agentstockbenchmark.settings import DEFAULT_RESULTS_REPO

mcp = FastMCP("AgentStockBenchmark")

def _sync_results_repo(timeout_seconds: int = 30):
    """Helper to sync the local results repo with the remote GitHub repo safely."""
    import subprocess
    import os
    repo_url = "https://github.com/xsunsim/AgentStockBenchmarkResults.git"
    target_dir = DEFAULT_RESULTS_REPO
    
    # Disable terminal prompts for git to prevent hanging
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    
    try:
        if not (target_dir / ".git").exists():
            if target_dir.exists() and any(target_dir.iterdir()):
                # Non-empty dir: initialize and reset
                subprocess.run(["git", "-C", str(target_dir), "init"], check=True, capture_output=True, timeout=timeout_seconds, env=env)
                subprocess.run(["git", "-C", str(target_dir), "remote", "add", "origin", repo_url], check=True, capture_output=True, timeout=timeout_seconds, env=env)
                subprocess.run(["git", "-C", str(target_dir), "fetch", "origin"], check=True, capture_output=True, timeout=timeout_seconds, env=env)
                subprocess.run(["git", "-C", str(target_dir), "reset", "--hard", "origin/main"], check=True, capture_output=True, timeout=timeout_seconds, env=env)
            else:
                # Empty or missing dir: clone
                target_dir.parent.mkdir(parents=True, exist_ok=True)
                subprocess.run(["git", "clone", "--depth", "1", repo_url, str(target_dir)], check=True, capture_output=True, timeout=timeout_seconds, env=env)
        else:
            # Existing repo: pull
            subprocess.run(["git", "-C", str(target_dir), "pull", "origin", "main"], check=True, capture_output=True, timeout=timeout_seconds, env=env)
        return True
    except subprocess.TimeoutExpired:
        print("Warning: Remote sync timed out.")
        return False
    except Exception as e:
        print(f"Warning: Remote sync failed: {str(e)}")
        return False

@mcp.tool()
def list_active_prompts() -> list[str]:
    """
    Lists the IDs of all available strategy generation prompts.
    """
    try:
        from agentstockbenchmark.stage1.prompts import list_prompts
        return [p.prompt_id for p in list_prompts()]
    except Exception as e:
        return [f"Error listing prompts: {str(e)}"]

@mcp.tool()
def refresh_market_data(date: str) -> str:
    """
    Intelligently prepares market data for a specific date.
    1. Checks if remote GitHub results are updated with this date.
    2. If not, checks if market is closed and downloads data.
    
    Args:
        date: The date to refresh (YYYYMMDD).
    """
    try:
        from agentstockbenchmark.stage2.market_data import refresh_daily_data
        from agentstockbenchmark.workflow import default_data_dir
        import datetime as dt
        import pandas as pd
        
        run_date = parse_date(date)
        today = dt.date.today()
        
        if run_date > today:
            return f"Error: {date} is in the future. Data only becomes available after market close on the day of trading."

        # 1. Sync and check if data exists in results repo (authoritative source)
        _sync_results_repo()
        daily_csv = DEFAULT_RESULTS_REPO / "data" / "raw" / "daily" / f"{date}.csv"
        
        if daily_csv.exists():
            # Re-merge to ensure parquets are updated with the new remote data
            data_dir = default_data_dir(DEFAULT_RESULTS_REPO)
            from agentstockbenchmark.stage2.market_data import merge_daily_csvs_into_parquets, verify_daily_merge
            merge_daily_csvs_into_parquets(DEFAULT_RESULTS_REPO, data_dir)
            verify_daily_merge(DEFAULT_RESULTS_REPO, data_dir, date=run_date)
            return f"Market data for {date} found in remote repository and synced locally."

        # 2. If it's today and not in remote, check if market is closed
        if run_date == today:
            # Market close is 4:00 PM ET. 
            now_et = pd.Timestamp.now(tz="America/New_York")
            market_close_et = now_et.replace(hour=16, minute=0, second=0, microsecond=0)
            
            # Give a 15 min buffer
            if now_et < market_close_et + pd.Timedelta(minutes=15):
                time_until_close = (market_close_et + pd.Timedelta(minutes=15)) - now_et
                hours, remainder = divmod(int(time_until_close.total_seconds()), 3600)
                minutes, _ = divmod(remainder, 60)
                
                return (
                    f"Market for {date} has not closed yet (or data is not yet available). "
                    f"Current time in New York: {now_et.strftime('%H:%M')}. "
                    f"Please try again in {hours}h {minutes}m."
                )

        # 3. Download data locally
        data_dir = default_data_dir(DEFAULT_RESULTS_REPO)
        refresh_daily_data(
            date=run_date,
            results_repo=DEFAULT_RESULTS_REPO,
            data_dir=data_dir
        )
        return f"Market data for {date} downloaded successfully from public sources."
    except Exception as e:
        return f"Failed to refresh market data for {date}: {str(e)}"

@mcp.tool()
def list_available_strategies(prompt_id: str | None = None) -> list[str]:
    """
    Lists all available strategies (model outputs).
    
    Args:
        prompt_id: Optional ID to filter strategies by a specific prompt version.
    """
    try:
        from agentstockbenchmark.stage1.strategies import list_strategies
        return [s.strategy_id for s in list_strategies(prompt_id=prompt_id)]
    except Exception as e:
        return [f"Error listing strategies: {str(e)}"]

def _is_trading_day(date: dt.date) -> bool:
    """Checks if a date is likely a trading day (not weekend or major US holiday)."""
    if date.weekday() >= 5:
        return False
    # Simple check for major US market holidays
    holidays = {
        (1, 1),   # New Year's
        (7, 4),   # Independence Day
        (12, 25), # Christmas
    }
    if (date.month, date.day) in holidays:
        return False
    return True

@mcp.tool()
def run_strategy_on_date(strategy_id: str, date: str) -> str:
    """
    Runs a specific strategy for a single date to generate rankings.
    Much faster than running the full production pipeline.
    
    Args:
        strategy_id: The full ID of the strategy (e.g., '20260517__OpenAI__GPT5_5__LinearNeutral').
        date: The date to run on (YYYYMMDD).
    """
    try:
        from agentstockbenchmark.stage2.rankings import generate_rankings
        from agentstockbenchmark.workflow import default_data_dir
        
        run_date = parse_date(date)
        
        # Validation for non-trading days
        if run_date > dt.date.today():
            return f"FAILED: {date} is in the future. Data is not yet available."
        if run_date.weekday() >= 5:
            return f"FAILED: {date} is a weekend. Markets are closed."
        if not _is_trading_day(run_date):
            return f"FAILED: {date} appears to be a market holiday."

        data_dir = default_data_dir(DEFAULT_RESULTS_REPO)
        
        # Check if data exists
        close_path = data_dir / "close.parquet"
        if close_path.exists():
            import pandas as pd
            close = pd.read_parquet(close_path)
            if pd.Timestamp(run_date) not in close.index:
                # Try refreshing data first
                refresh_market_data(date)
                close = pd.read_parquet(close_path)
                if pd.Timestamp(run_date) not in close.index:
                    return f"FAILED: No market data found for {date} in local parquets even after refresh."

        report = generate_rankings(
            start=run_date,
            end=run_date,
            data_dir=data_dir,
            results_repo=DEFAULT_RESULTS_REPO,
            strategy_selector=strategy_id,
            overwrite=True
        )
        
        res = report.get(date, {}).get(strategy_id, "FAILED")
        if res == "FAILED":
            return f"FAILED: Strategy execution failed for {strategy_id} on {date}. Check model output formatting."
        return f"Strategy {strategy_id} run for {date}. Status: {res}"
    except Exception as e:
        return f"Error running strategy: {str(e)}"

def _get_previous_trading_date(date: dt.date) -> dt.date:
    """Finds the likely previous trading day."""
    prev = date - dt.timedelta(days=1)
    while not _is_trading_day(prev):
        prev -= dt.timedelta(days=1)
    return prev

@mcp.tool()
def get_top_positions(strategy_id: str, target_trading_date: str, top_n: int = 10) -> dict[str, Any]:
    """
    Returns top stock positions for a strategy to be traded ON a specific date.
    AUTO-HEALING: Automatically handles mapping and looks back for valid data if needed.
    
    Args:
        strategy_id: The ID of the strategy.
        target_trading_date: The date you want to enter the trades (YYYYMMDD).
        top_n: Number of top long/short positions to return.
    """
    from agentstockbenchmark.stage3.portfolio import build_portfolios
    import pandas as pd
    
    try:
        trading_date = parse_date(target_trading_date)
        
        # Search backwards for the most recent valid ranking date
        current_search_date = trading_date
        max_lookback = 7
        ranking_date = None
        portfolio_path = None
        
        for i in range(max_lookback):
            current_search_date = _get_previous_trading_date(current_search_date)
            ranking_date_str = date_id(current_search_date)
            path = DEFAULT_RESULTS_REPO / "portfolios" / ranking_date_str / f"{strategy_id}.csv"
            
            # 1. If it exists, we are done
            if path.exists():
                portfolio_path = path
                ranking_date = current_search_date
                break
            
            # 2. If it doesn't exist, and it's the MOST RECENT possible trading day, try to generate it
            if i == 0: 
                print(f"Attempting auto-heal for ranking date {ranking_date_str}...")
                refresh_status = refresh_market_data(ranking_date_str)
                # If data was found or downloaded
                if "Error:" not in refresh_status and "not closed" not in refresh_status:
                    run_status = run_strategy_on_date(strategy_id, ranking_date_str)
                    if "PASS" in run_status or "run for" in run_status:
                        build_portfolios(results_repo=DEFAULT_RESULTS_REPO, ranking_date=current_search_date)
                        if path.exists():
                            portfolio_path = path
                            ranking_date = current_search_date
                            break
        
        if not portfolio_path:
            return {
                "error": (
                    f"Could not find or generate valid rankings for trading on {target_trading_date}. "
                    f"Looked back up to {max_lookback} days. This usually happens if market data "
                    "for the previous trading days is missing (e.g. holidays) or if strategies failed."
                )
            }
            
        df = pd.read_csv(portfolio_path)
        df = df.sort_values("position_dollars", ascending=False)
        
        top_longs = df.head(top_n)[["ticker", "position_dollars", "score"]].to_dict(orient="records")
        top_shorts = df.tail(top_n)[["ticker", "position_dollars", "score"]].to_dict(orient="records")
        
        return {
            "strategy_id": strategy_id,
            "target_trading_date": target_trading_date,
            "data_cutoff_date": date_id(ranking_date),
            "top_longs": top_longs,
            "top_shorts": top_shorts,
            "instructions": f"Enter these positions at the market open on {target_trading_date}. "
                            f"Generated using data finalized on {date_id(ranking_date)}."
        }
    except Exception as e:
        return {"error": str(e)}

@mcp.tool()
def create_research_workspace(prompt_id: str, run_id: str | None = None) -> str:
    """
    Creates an isolated workspace for generating new trading strategies.
    
    Args:
        prompt_id: The ID of the prompt to use (e.g., '20260517').
        run_id: Optional unique ID for this research run.
    """
    try:
        run_dir = generate_strategies_workspace(prompt_id=prompt_id, run_id=run_id)
        return f"Research workspace created at: {run_dir}. Please place your generated strategy.py files in {run_dir}/strategies/{prompt_id}/<strategy_slug>/strategy.py"
    except Exception as e:
        return f"Error creating workspace: {str(e)}"

@mcp.tool()
def run_research_backtest(
    prompt_id: str, 
    start_date: str, 
    end_date: str, 
    run_id: str | None = None,
    strategy_selector: str | None = None
) -> str:
    """
    Runs a backtest on strategies in a research workspace.
    
    Args:
        prompt_id: The ID of the prompt/workspace.
        start_date: Backtest start date (YYYYMMDD).
        end_date: Backtest end date (YYYYMMDD).
        run_id: The unique ID of the research run.
        strategy_selector: Optional glob pattern to select specific strategies.
    """
    try:
        from agentstockbenchmark.workflow import default_data_dir
        
        start = parse_date(start_date)
        end = parse_date(end_date)
        data_dir = default_data_dir(DEFAULT_RESULTS_REPO)
        
        run_dir = research_backtest(
            prompt_id=prompt_id,
            start=start,
            end=end,
            data_dir=data_dir,
            run_id=run_id,
            strategy_selector=strategy_selector
        )
        return f"Backtest completed. Results available in: {run_dir}"
    except Exception as e:
        return f"Error running backtest: {str(e)}"

@mcp.tool()
def analyze_results(run_id: str) -> dict[str, Any]:
    """
    Analyzes and summarizes the results of a research backtest.
    If multiple runs match the ID, an error with matches is returned.
    
    Args:
        run_id: The unique ID of the research run.
    """
    import json
    try:
        analysis_path = analyze_research_run(run_id=run_id)
        with open(analysis_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        # Return the exception message directly as it now contains the match list
        return {"error": str(e)}

@mcp.tool()
def promote_strategy(run_id: str, strategy_id: str) -> str:
    """
    Promotes a successful research strategy to the production 'strategies/' directory.
    
    Args:
        run_id: The unique ID of the research run where the strategy was tested.
        strategy_id: The ID of the strategy to promote.
    """
    try:
        dest_path = promote_research_strategy(run_id=run_id, strategy_id=strategy_id)
        return f"Strategy promoted to production: {dest_path}"
    except Exception as e:
        return f"Error promoting strategy: {str(e)}"

@mcp.tool()
def run_production_daily(date: str) -> dict[str, Any]:
    """
    Runs the full production pipeline (Stage 1, 2, and 3) for a specific date.
    
    Args:
        date: The date to run (YYYYMMDD).
    """
    try:
        run_date = parse_date(date)
        report = run_daily(run_date=run_date)
        return report
    except Exception as e:
        return {"status": "FAIL", "error": str(e)}

@mcp.tool()
def get_leaderboard() -> str:
    """
    Retrieves the current production leaderboard in Markdown format.
    Automatically syncs with the remote repository to ensure data is up to date.
    """
    from agentstockbenchmark.stage3.leaderboard import build_leaderboard
    
    # Auto-Sync with Remote
    _sync_results_repo()

    # Build and Return Leaderboard
    try:
        # Ensure leaderboard is up to date from local data
        build_leaderboard(results_repo=DEFAULT_RESULTS_REPO)
    except Exception as e:
        return (
            f"Leaderboard currently unavailable. Sync or build failed: {str(e)}\n"
            "You may need to run 'run_production_daily' to generate local data."
        )
    
    leaderboard_path = DEFAULT_RESULTS_REPO / "leaderboard" / "leaderboard.md"
    if leaderboard_path.exists():
        return leaderboard_path.read_text()
    return "Leaderboard file not found after sync."

if __name__ == "__main__":
    mcp.run()
