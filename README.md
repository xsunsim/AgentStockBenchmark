# AgentStockBenchmark: The Clean-Room Engine (Github:AgentStockBenchmark)

[中文版本](./README_CN.md)

### THE ULTIMATE STRESS TEST FOR AGI
This is a live, tamper-proof arena testing whether the world's smartest AI agents can actually solve the ultimate stock prediction problem. We are not testing raw models in a sterile academic sandbox. We are testing the full autonomous loop—tools like Claude Code, Codex, and Gemini CLI—given clean data, a strict objective, and zero internet access. Every day, they are judged on one highly specific question: **which stock in the S&P 500 will have the best performance tomorrow?**

Most AI coding benchmarks are broken by data contamination. You never know if an AI "solved" a challenge or just memorized a GitHub repo. But nobody—not OpenAI, not Anthropic, not Google—has a chance to know **which stock in the S&P 500 will have the best performance tomorrow** during its training process. The future is the only uncontaminated test set.

**If you find this project interesting, please consider giving it a ⭐ Star and Forking the repository to test your own ideas!**

---

### JUST LOOKING FOR THE LEADERBOARD?
If you are here to see which AI makes the most money in this arena, check out our companion repository:
👉 **[AgentStockBenchmarkResults](https://github.com/xsunsim/AgentStockBenchmarkResults)**

The Results repository hosts the live leaderboard, the beautiful cumulative PnL charts, and the daily performance digests.

---

### THE "CLEAN ROOM" ARCHITECTURE
To ensure 100% integrity, this engine enforces a strict two-repository boundary:
1.  **This Repo (`AgentStockBenchmark`)**: The "Clean Room." It hosts the frozen agent logic, the prompts, and the orchestration engine. Once an agent generates a strategy, it is merged here and receives a permanent server-side timestamp.
2.  **Results Repo (`AgentStockBenchmarkResults`)**: The "Arena." It hosts the realized market data and the public leaderboard. 

**The Time Invariant**: An agent is only allowed to see a data snapshot truncated exactly at $t-1$ (yesterday). Its prediction for $t$ (today) must be frozen before market data for $t$ even exists.

---

### FOR DEVELOPERS & RESEARCHERS
This repository is an open-source engineering laboratory. We invite tech-heavy users to fork this engine and experiment with the "Autonomous Loop."

#### 1. Fork & Extend the Ideas
The true alpha in this benchmark isn't just the model—it's the **ideas**. We encourage you to:
*   **Implement New Portfolio Math**: Don't like our Linear Neutral ladder? Fork the engine and implement your own risk-parity or Kelly-criterion sizing logic in `stage3`.
*   **Agentic Scaffolding**: Modify the research workflow in `agentstockbenchmark.research` to test how different "chain-of-thought" or "self-reflection" loops affect strategy quality.
*   **Custom Universes**: The engine is built for the S&P 500, but the data-ingestion pipeline is flexible. Extend it to crypto, forex, or international equities.

#### 2. Prompt Engineering is Alpha
The biggest variable in performance is the scaffolding provided to the agent.
*   Check [STRATEGY_EDITORIAL.md](STRATEGY_EDITORIAL.md) to see how different model lineages (OpenAI, Anthropic, Google) responded to **[Prompt Version 20260517](prompts/20260517/prompt.md)**.
*   Experiment with the prompts in `prompts/`. Can you force a model to better understand overfitting? Can you scaffold it to build more robust volatility-normalization?

---

### ENGINE DOCUMENTATION
*   [SYSTEM.md](SYSTEM.md): Deep dive into the architecture, data contracts, and the $t-1 \to t \to t+1$ failure model.
*   [USAGE.md](USAGE.md): Full CLI cookbook for production, backfilling, and model migration.
*   [STRATEGY_EDITORIAL.md](STRATEGY_EDITORIAL.md): A detailed quantitative analysis of the strategies produced by each model under **[Prompt Version 20260517](prompts/20260517/prompt.md)**.

### QUICK START
```bash
# Clone the engine
git clone git@github.com:xsunsim/AgentStockBenchmark.git
cd AgentStockBenchmark
export PYTHONPATH=src

# List active prompts and strategies
python -m agentstockbenchmark stage1 list-prompts
python -m agentstockbenchmark stage1 list-strategies --prompt-id 20260517
```

### 🤖 USE IT AS AN MCP SERVER (Model Context Protocol)

We have officially published AgentStockBenchmark as an MCP server. This allows you to give AI agents (like Claude Desktop or Cursor) direct access to our live market data, strategy execution engine, and historical leaderboard.

#### 1. Configuration (Claude Desktop)

The absolute most reliable way to install and run this server is using `uvx`. This method requires **zero manual installation** and bypasses all common Python `PATH` errors.

1. **Install `uv`** (if you haven't already):
   * Mac/Linux: `curl -LsSf https://astral.sh/uv/install.sh | sh`
   * Windows: `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`

2. Add this exact block to your `claude_desktop_config.json`. 
*(Note: Replace `/path/to/your/clone` with the actual folder where you cloned this repository, e.g., `/Users/xiaoyusun/AgentStockBenchmark`)*
```json
{
  "mcpServers": {
    "agent-stock": {
      "command": "uvx",
      "args": [
        "--from",
        "agentstockbenchmark",
        "asb-mcp"
      ],
      "env": {
        "ASB_PROJECT_ROOT": "/path/to/your/clone"
      }
    }
  }
}
```
*(When you restart Claude, `uvx` will automatically download the package from PyPI, set up an isolated environment, and run the server. The `ASB_PROJECT_ROOT` environment variable tells the isolated server where to find your local `prompts` and `strategies` folders).*

#### 2. Advanced: Manual pip Installation
If you prefer not to use `uvx`, you can install it globally:
```bash
pip install agentstockbenchmark
```
**⚠️ WARNING**: If Claude Desktop complains it cannot find the `asb-mcp` command, it is because your Python `bin` directory is not in Claude's PATH. You must provide the **absolute path** to the executable in your config (e.g., `"command": "/opt/anaconda3/bin/asb-mcp"`).

#### 3. Available Tools & Capabilities
Once connected, your AI assistant has access to 11 specialized tools, categorized below:

**A. Core Discovery & Performance**
*   `get_leaderboard`: Instantly fetches the live, auto-synced production leaderboard from GitHub.
*   `list_active_prompts`: Shows available strategy generation templates (e.g., `20260517`).
*   `list_available_strategies`: Lists all AI-generated models currently competing in the arena.

**B. The "Autopilot" Prediction Engine**
*   `get_top_positions`: **(Highly Recommended)** Just tell the AI what day you want to trade (e.g., "Show me top positions for tomorrow"). This tool automatically handles the complex pipeline: checking market hours, syncing remote data, running the specified strategy, and returning the top 10 long/short stocks.
*   `run_strategy_on_date`: Run a single model on a specific date for targeted analysis.
*   `refresh_market_data`: Force a download of the latest OHLCV data for the S&P 500 universe.

**C. The Research Sandbox (Build Your Own)**
*   `create_research_workspace`: Sets up an isolated local folder for you to test a brand new prompt or strategy.
*   `run_research_backtest`: Evaluates your experimental strategy over a custom date range.
*   `analyze_results`: Calculates Sharpe ratio and PnL for your experiment.
*   `promote_strategy`: Pushes a winning experimental strategy into your local production arena.

**D. Production Workflows**
*   `run_production_daily`: Executes the full $T-1 \to T$ pipeline (data ingestion, running all production strategies, portfolio construction, and leaderboard updating) for a given date.

---

### 🧠 FOR AI AGENTS (OPERATIONAL GUIDE)
If you are an AI agent reading this via MCP, follow these best practices:

1.  **Checking Performance**: Always start with `get_leaderboard` to see which model lineages are currently winning.
2.  **Predicting the Future**: To get positions for the *next* trading day, use `get_top_positions` with the `target_trading_date` set to the next day. The tool handles all data fetching and execution automatically.
3.  **Experimental Workflow**:
    *   Use `list_active_prompts` to find a starting point.
    *   Use `create_research_workspace` to set up a lab.
    *   Generate a new `strategy.py` file based on the prompt.
    *   Use `run_research_backtest` to verify your idea. (Limit date ranges to < 30 days to avoid timeouts).
    *   Use `analyze_results` to see if your Sharpe ratio beats the current leaderboard.
4.  **Data Latency**: Market data for "Today" only becomes available 15 minutes after the New York market close (4:15 PM ET). Do not attempt to pull data for today while the market is still open.

---

### WHAT WE ARE NOT
We are not a hedge fund. We are not a stock recommendation service. **Use it at your own risk.**

We care if Codex beats Claude Code—not if AAPL beats NVDA tomorrow.
