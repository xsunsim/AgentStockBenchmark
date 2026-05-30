from __future__ import annotations

import datetime as dt
from typing import Any

from mcp.server.fastmcp import FastMCP

from agentstockbenchmark.dates import parse_date, date_id, iter_dates
from agentstockbenchmark.settings import DEFAULT_RESULTS_REPO

mcp = FastMCP("AgentStockBenchmark")

RESULTS_REPO_URL = "https://github.com/xsunsim/AgentStockBenchmarkResults.git"
BASE_SPARSE_PATTERNS = (
    "/accounting/",
    "/daily_digest/",
    "/leaderboard/",
    "/manifests/",
    "/portfolios/",
    "/prompts/",
    "/strategies/",
    "/README.md",
    "/README_CN.md",
)


def _sync_results_repo(
    timeout_seconds: int = 300,
    include_parquets: bool = False,
    specific_raw_date: str | None = None,
):
    """Helper to sync the local results repo with the remote GitHub repo safely.
    Uses sparse-checkout to prioritize essential metadata (leaderboards, manifests)
    over heavy market data.
    """
    import subprocess
    import os

    # Check if git is installed first
    try:
        subprocess.run(["git", "--version"], check=True, capture_output=True, timeout=5)
    except Exception:
        print("Warning: 'git' command not found. Please install Git to enable auto-sync.")
        return False

    target_dir = DEFAULT_RESULTS_REPO

    # Disable terminal prompts for git to prevent hanging
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"

    patterns = list(BASE_SPARSE_PATTERNS)
    if include_parquets:
        patterns.append("/data/parquet/")
    if specific_raw_date:
        patterns.append(f"/data/raw/daily/{specific_raw_date}.csv")

    def run_git(*args: str, check: bool = True) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git", "-C", str(target_dir), *args],
            check=check,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            env=env,
        )

    try:
        # Initialize if not present
        initialized_repo = not (target_dir / ".git").exists()
        if initialized_repo:
            target_dir.mkdir(parents=True, exist_ok=True)
            run_git("init")
            run_git("remote", "add", "origin", RESULTS_REPO_URL)
        else:
            origin = run_git("remote", "get-url", "origin", check=False)
            if origin.returncode != 0:
                run_git("remote", "add", "origin", RESULTS_REPO_URL)

        sparse_enabled = run_git(
            "config", "--bool", "core.sparseCheckout", check=False
        )
        if initialized_repo or sparse_enabled.stdout.strip() == "true":
            # --no-cone supports both directories and individual files, which is
            # needed for surgical syncs like data/raw/daily/<YYYYMMDD>.csv.
            run_git("sparse-checkout", "init", "--no-cone", check=False)
            run_git("sparse-checkout", "set", "--no-cone", *patterns)

        if initialized_repo:
            run_git("fetch", "--depth", "1", "origin", "main")
            run_git("checkout", "-B", "main", "FETCH_HEAD")
        else:
            run_git("pull", "--ff-only", "origin", "main")
        return True
    except subprocess.TimeoutExpired:
        print(f"Warning: Remote sync of results repo timed out after {timeout_seconds}s.")
    except Exception as e:
        print(f"Warning: Remote sync of results repo failed: {str(e)}")

    return False


def _ensure_results_repo(
    *,
    include_parquets: bool = False,
    specific_raw_date: str | None = None,
    required_paths: tuple[str, ...] = (),
) -> bool:
    """Sync the results repo, but allow existing local data if remote sync fails."""
    if _sync_results_repo(
        include_parquets=include_parquets,
        specific_raw_date=specific_raw_date,
    ):
        return True

    if required_paths:
        return all((DEFAULT_RESULTS_REPO / path).exists() for path in required_paths)
    return DEFAULT_RESULTS_REPO.exists()


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

def _validate_trading_date(date_str: str) -> tuple[dt.date | None, dict[str, str] | None]:
    """Helper to validate if a date string is a valid trading day."""
    try:
        date = parse_date(date_str)
        if date > dt.date.today():
            return None, {"error": f"{date_str} is in the future. Data is not yet available."}
        if date.weekday() >= 5:
            return None, {"error": f"{date_str} is a weekend. Markets are closed."}
        if not _is_trading_day(date):
            return None, {"error": f"{date_str} appears to be a market holiday."}
        return date, None
    except Exception as e:
        return None, {"error": f"Invalid date format: {str(e)}"}

@mcp.tool()
def list_active_prompts() -> dict[str, Any]:
    """
    Lists the IDs of all available strategy generation prompts.
    """
    try:
        if not _ensure_results_repo(required_paths=("prompts",)):
            return {
                "error": f"Could not sync or find results repo at {DEFAULT_RESULTS_REPO}."
            }
        from agentstockbenchmark.stage1.prompts import list_prompts
        return {"prompts": [p.prompt_id for p in list_prompts()]}
    except Exception as e:
        return {"error": f"Error listing prompts: {str(e)}"}

@mcp.tool()
def refresh_market_data(date: str) -> dict[str, Any]:
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
        
        run_date, error = _validate_trading_date(date)
        if error:
            return error

        # 1. Sync and check if data exists in results repo (authoritative source)
        _ensure_results_repo(
            include_parquets=True,
            specific_raw_date=date,
            required_paths=("data/parquet",),
        )
        daily_csv = DEFAULT_RESULTS_REPO / "data" / "raw" / "daily" / f"{date}.csv"
        
        if daily_csv.exists():
            # Re-merge to ensure parquets are updated with the new remote data
            data_dir = default_data_dir(DEFAULT_RESULTS_REPO)
            from agentstockbenchmark.stage2.market_data import merge_daily_csvs_into_parquets, verify_daily_merge
            merge_daily_csvs_into_parquets(DEFAULT_RESULTS_REPO, data_dir)
            verify_daily_merge(DEFAULT_RESULTS_REPO, data_dir, date=run_date)
            return {"status": "SUCCESS", "message": f"Market data for {date} found in remote repository and synced locally."}

        # 2. If it's today and not in remote, check if market is closed
        if run_date == dt.date.today():
            # Market close is 4:00 PM ET. 
            now_et = pd.Timestamp.now(tz="America/New_York")
            market_close_et = now_et.replace(hour=16, minute=0, second=0, microsecond=0)
            
            # Give a 15 min buffer
            if now_et < market_close_et + pd.Timedelta(minutes=15):
                time_until_close = (market_close_et + pd.Timedelta(minutes=15)) - now_et
                hours, remainder = divmod(int(time_until_close.total_seconds()), 3600)
                minutes, _ = divmod(remainder, 60)
                
                return {
                    "status": "WAIT",
                    "error": f"Market for {date} has not closed yet (or data is not yet available).",
                    "current_time_ny": now_et.strftime('%H:%M'),
                    "wait_time": f"{hours}h {minutes}m"
                }

        # 3. Download data locally
        data_dir = default_data_dir(DEFAULT_RESULTS_REPO)
        refresh_daily_data(
            date=run_date,
            results_repo=DEFAULT_RESULTS_REPO,
            data_dir=data_dir
        )
        return {"status": "SUCCESS", "message": f"Market data for {date} downloaded successfully from public sources."}
    except Exception as e:
        return {"status": "FAIL", "error": f"Failed to refresh market data for {date}: {str(e)}"}

@mcp.tool()
def list_available_strategies(prompt_id: str | None = None) -> dict[str, Any]:
    """
    Lists all available strategies (model outputs).
    
    Args:
        prompt_id: Optional ID to filter strategies by a specific prompt version.
    """
    try:
        if not _ensure_results_repo(required_paths=("prompts", "strategies")):
            return {
                "error": f"Could not sync or find results repo at {DEFAULT_RESULTS_REPO}."
            }
        from agentstockbenchmark.stage1.strategies import list_strategies
        from agentstockbenchmark.stage1.prompts import list_prompts
        
        if prompt_id:
            available_prompts = [p.prompt_id for p in list_prompts()]
            if prompt_id not in available_prompts:
                return {"error": f"Prompt ID {prompt_id!r} not found. Available prompts: {available_prompts}"}
            
            strategies = [s.strategy_id for s in list_strategies(prompt_id=prompt_id)]
            if not strategies:
                return {
                    "strategies": [],
                    "message": f"Prompt {prompt_id!r} found, but no strategy.py files have been generated for it yet."
                }
            return {"strategies": strategies}
                
        return {"strategies": [s.strategy_id for s in list_strategies()]}
    except Exception as e:
        return {"error": f"Error listing strategies: {str(e)}"}

@mcp.tool()
def run_strategy_on_date(strategy_id: str, date: str) -> dict[str, Any]:
    """
    Runs a specific strategy for a single date to generate rankings.
    Much faster than running the full production pipeline.
    
    Args:
        strategy_id: The full ID of the strategy (e.g., '20260517__OpenAI__GPT5_5__LinearNeutral').
        date: The date to run on (YYYYMMDD).
    """
    try:
        if not _ensure_results_repo(
            include_parquets=True,
            required_paths=("strategies", "data/parquet"),
        ):
            return {
                "status": "FAIL",
                "error": f"Could not sync or find required results data at {DEFAULT_RESULTS_REPO}.",
            }
        from agentstockbenchmark.stage2.rankings import generate_rankings
        from agentstockbenchmark.workflow import default_data_dir
        from agentstockbenchmark.stage1.strategies import list_strategies
        
        run_date, error = _validate_trading_date(date)
        if error:
            return error

        # Check if strategy exists (supports glob)
        strategies = list_strategies(selector=strategy_id)
        if not strategies:
            return {"error": f"Strategy matching {strategy_id!r} not found."}

        data_dir = default_data_dir(DEFAULT_RESULTS_REPO)

        # Check if data exists
        _ensure_results_repo(include_parquets=True, required_paths=("data/parquet",))
        close_path = data_dir / "close.parquet"
        if close_path.exists():
            import pandas as pd
            close = pd.read_parquet(close_path)
            if pd.Timestamp(run_date) not in close.index:
                # Try refreshing data first
                refresh_market_data(date)
                close = pd.read_parquet(close_path)
                if pd.Timestamp(run_date) not in close.index:
                    return {"status": "FAIL", "error": f"No market data found for {date} in local parquets even after refresh."}

        report = generate_rankings(
            start=run_date,
            end=run_date,
            data_dir=data_dir,
            results_repo=DEFAULT_RESULTS_REPO,
            strategy_selector=strategy_id,
            overwrite=True
        )
        
        date_id_str = date_id(run_date)
        res = report.get(date_id_str, {})
        if not res:
            return {"status": "FAIL", "error": f"Strategy execution failed for {strategy_id} on {date}. Check model output formatting."}
        return {"status": "SUCCESS", "date": date_id_str, "results": res}
    except Exception as e:
        return {"status": "FAIL", "error": f"Error running strategy: {str(e)}"}

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
    try:
        if not _ensure_results_repo(required_paths=("strategies", "portfolios")):
            return {
                "error": f"Could not sync or find required results data at {DEFAULT_RESULTS_REPO}."
            }
        from agentstockbenchmark.stage3.portfolio import build_portfolios
        from agentstockbenchmark.stage1.strategies import list_strategies
        import pandas as pd

        # 0. Validate strategy existence
        strategies = list_strategies(selector=strategy_id)
        if not strategies:
            return {"error": f"Strategy matching {strategy_id!r} not found."}
        
        # If multiple matches, we can't reliably auto-heal for all.
        if len(strategies) > 1:
            return {"error": f"Strategy selector {strategy_id!r} is ambiguous. Matches found: {[s.strategy_id for s in strategies]}"}
        
        exact_strategy_id = strategies[0].strategy_id

        # 1. Validate date
        try:
            trading_date = parse_date(target_trading_date)
        except Exception as e:
            return {"error": f"Invalid date format: {str(e)}"}
            
        if trading_date > dt.date.today() + dt.timedelta(days=1):
            return {"error": f"{target_trading_date} is too far in the future. Predictions are only available for the next trading day."}
        
        # 2. Search backwards for the most recent valid ranking date
        current_search_date = trading_date
        max_lookback = 7
        ranking_date = None
        portfolio_path = None
        
        for i in range(max_lookback):
            current_search_date = _get_previous_trading_date(current_search_date)
            ranking_date_str = date_id(current_search_date)
            path = DEFAULT_RESULTS_REPO / "portfolios" / ranking_date_str / f"{exact_strategy_id}.csv"
            
            # 1. If it exists, we are done
            if path.exists():
                portfolio_path = path
                ranking_date = current_search_date
                break
            
            # 2. If it doesn't exist, and it's the MOST RECENT possible trading day, try to generate it
            if i == 0: 
                refresh_res = refresh_market_data(ranking_date_str)
                if refresh_res.get("status") == "SUCCESS":
                    run_res = run_strategy_on_date(exact_strategy_id, ranking_date_str)
                    if run_res.get("status") == "SUCCESS":
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
            "strategy_id": exact_strategy_id,
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
def create_research_workspace(prompt_id: str, run_id: str | None = None) -> dict[str, Any]:
    """
    Creates an isolated workspace for generating new trading strategies.
    
    Args:
        prompt_id: The ID of the prompt to use (e.g., '20260517').
        run_id: Optional unique ID for this research run.
    """
    try:
        if not _ensure_results_repo(required_paths=("prompts",)):
            return {
                "error": f"Could not sync or find results repo at {DEFAULT_RESULTS_REPO}."
            }
        from agentstockbenchmark.research import generate_strategies_workspace
        from agentstockbenchmark.stage1.prompts import list_prompts
        available_prompts = [p.prompt_id for p in list_prompts()]
        if prompt_id not in available_prompts:
            return {"error": f"Prompt ID {prompt_id!r} not found. Available prompts: {available_prompts}"}
            
        run_dir = generate_strategies_workspace(prompt_id=prompt_id, run_id=run_id)
        return {
            "status": "SUCCESS",
            "workspace_path": str(run_dir),
            "instructions": f"Please place your generated strategy.py files in {run_dir}/strategies/{prompt_id}/<strategy_slug>/strategy.py"
        }
    except Exception as e:
        return {"error": f"Error creating workspace: {str(e)}"}

@mcp.tool()
def run_research_backtest(
    prompt_id: str, 
    start_date: str, 
    end_date: str, 
    run_id: str | None = None,
    strategy_selector: str | None = None
) -> dict[str, Any]:
    """
    Runs a backtest on strategies in a research workspace.
    CAUTION: Running many strategies over long periods may time out.
    
    Args:
        prompt_id: The ID of the prompt/workspace.
        start_date: Backtest start date (YYYYMMDD).
        end_date: Backtest end date (YYYYMMDD).
        run_id: The unique ID of the research run.
        strategy_selector: Optional glob pattern to select specific strategies.
    """
    try:
        if not _ensure_results_repo(
            include_parquets=True,
            required_paths=("prompts", "strategies", "data/parquet"),
        ):
            return {
                "error": f"Could not sync or find required results data at {DEFAULT_RESULTS_REPO}."
            }
        from agentstockbenchmark.workflow import default_data_dir
        from agentstockbenchmark.stage1.strategies import list_strategies
        from agentstockbenchmark.settings import STRATEGIES_DIR
        from agentstockbenchmark.research import resolve_research_strategies_dir, find_research_run
        from agentstockbenchmark.research import research_backtest
        
        start = parse_date(start_date)
        end = parse_date(end_date)
        
        # 1. Resolve strategies to estimate workload
        # If run_id is provided, we check that workspace.
        strategies_dir = None
        if run_id:
            try:
                run_dir = find_research_run(DEFAULT_RESULTS_REPO, run_id)
                strategies_dir = resolve_research_strategies_dir(run_dir, prompt_id, None)
            except Exception:
                pass # research_backtest will handle missing run_id by creating one
        
        # Estimate workload to prevent 4-minute timeouts
        days = list(iter_dates(start, end))
        num_days = len(days)
        
        # Get count of strategies that will be run
        strategies = list_strategies(strategies_dir=strategies_dir or STRATEGIES_DIR, prompt_id=prompt_id, selector=strategy_selector)
        num_strategies = len(strategies)
        
        workload = num_days * num_strategies
        # Threshold: 200 units (e.g. 20 days * 10 strategies)
        if workload > 200:
            return {
                "error": "Backtest workload too heavy for a single request.",
                "details": f"Attempted {num_days} days x {num_strategies} strategies = {workload} units (Limit: 200).",
                "hint": "Please use a 'strategy_selector' to run fewer models, or a shorter date range (e.g. 2 weeks)."
            }

        data_dir = default_data_dir(DEFAULT_RESULTS_REPO)
        
        run_dir = research_backtest(
            prompt_id=prompt_id,
            start=start,
            end=end,
            data_dir=data_dir,
            run_id=run_id,
            strategy_selector=strategy_selector
        )
        return {"status": "SUCCESS", "results_workspace": str(run_dir)}
    except ValueError as e:
        if "no strategies found" in str(e).lower():
            return {
                "error": "No strategies found in the workspace.",
                "hint": f"Please ensure you have generated and placed strategy.py files in the workspace (e.g., under research/{prompt_id}/{run_id}/strategies/) before running a backtest."
            }
        return {"error": f"Error running backtest: {str(e)}"}
    except Exception as e:
        return {"error": f"Error running backtest: {str(e)}"}

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
        if not _ensure_results_repo():
            return {
                "error": f"Could not sync or find results repo at {DEFAULT_RESULTS_REPO}."
            }
        from agentstockbenchmark.research import analyze_research_run
        analysis_path = analyze_research_run(run_id=run_id)
        with open(analysis_path, 'r') as f:
            data = json.load(f)
            
        if not data.get("has_metrics", False):
            data["hint"] = (
                "Run found, but no performance metrics were generated. "
                "Ensure that strategies were placed in the workspace and that the backtest completed successfully."
            )
        return data
    except Exception as e:
        # Return the exception message directly as it now contains the match list
        return {"error": str(e)}

@mcp.tool()
def promote_strategy(run_id: str, strategy_id: str) -> dict[str, Any]:
    """
    Promotes a successful research strategy to the production 'strategies/' directory.
    
    Args:
        run_id: The unique ID of the research run where the strategy was tested.
        strategy_id: The ID of the strategy to promote.
    """
    try:
        if not _ensure_results_repo():
            return {
                "error": f"Could not sync or find results repo at {DEFAULT_RESULTS_REPO}."
            }
        from agentstockbenchmark.research import promote_research_strategy
        dest_path = promote_research_strategy(run_id=run_id, strategy_id=strategy_id)
        return {"status": "SUCCESS", "promoted_path": str(dest_path)}
    except Exception as e:
        return {"error": f"Error promoting strategy: {str(e)}"}

@mcp.tool()
def run_production_daily(date: str) -> dict[str, Any]:
    """
    Runs the full production pipeline (Stage 1, 2, and 3) for a specific date.
    
    Args:
        date: The date to run (YYYYMMDD).
    """
    try:
        if not _ensure_results_repo(
            include_parquets=True,
            required_paths=("prompts", "strategies"),
        ):
            return {
                "status": "FAIL",
                "error": f"Could not sync or find required results data at {DEFAULT_RESULTS_REPO}.",
            }
        from agentstockbenchmark.workflow import run_daily

        run_date, error = _validate_trading_date(date)
        if error:
            # Re-format error to match JSON expectation but include status: FAIL
            return {"status": "FAIL", **error}
            
        report = run_daily(run_date=run_date)
        return report
    except Exception as e:
        return {"status": "FAIL", "error": str(e)}

@mcp.tool()
def get_leaderboard() -> dict[str, Any]:
    """
    Retrieves the current production leaderboard in Markdown format.
    Automatically syncs with the remote repository to ensure data is up to date.
    """
    # Auto-Sync with Remote
    if not _ensure_results_repo(required_paths=("leaderboard/leaderboard.md",)):
        return {
            "error": f"Could not sync or find results repo at {DEFAULT_RESULTS_REPO}."
        }

    leaderboard_path = DEFAULT_RESULTS_REPO / "leaderboard" / "leaderboard.md"
    if leaderboard_path.exists():
        return {"leaderboard_markdown": leaderboard_path.read_text()}

    from agentstockbenchmark.stage3.leaderboard import build_leaderboard

    # Build and Return Leaderboard
    try:
        # Ensure leaderboard is up to date from local data
        build_leaderboard(results_repo=DEFAULT_RESULTS_REPO)
    except Exception as e:
        return {
            "error": f"Leaderboard currently unavailable. Sync or build failed: {str(e)}",
            "hint": "You may need to run 'run_production_daily' to generate local data."
        }
    
    if leaderboard_path.exists():
        return {"leaderboard_markdown": leaderboard_path.read_text()}
    return {"error": "Leaderboard file not found after sync."}

if __name__ == "__main__":
    mcp.run()
