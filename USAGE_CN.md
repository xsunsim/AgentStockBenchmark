# AgentStockBenchmark 使用手册 (Usage)

[English Version](./USAGE.md)

本文件是面向维护者和编程智能体的命令行操作指南。下文中的命令均以 `PYTHONPATH=src python -m ...` 开头，以便在未安装包的情况下直接从本地源码运行。

请使用紧凑日期格式，例如 `20260519`。大多数命令也接受 ISO 格式日期（如 `2026-05-19`），但系统生成的产物一律使用 `YYYYMMDD` 格式。

## 环境配置

核心引擎仓库：

```bash
cd AgentStockBenchmark
export PYTHONPATH=src
python -m agentstockbenchmark --help
```

结果处理工具：

```bash
cd AgentStockBenchmarkResults
export PYTHONPATH=src
python -m agentstockbenchmark_results --help
```

## 每日生产运行 (Daily Production)

执行完整的每日工作流：

```bash
cd AgentStockBenchmark
PYTHONPATH=src python -m agentstockbenchmark daily-run \
  --date 20260519 \
  --results-repo ../AgentStockBenchmarkResults
```

仅运行特定策略：

```bash
PYTHONPATH=src python -m agentstockbenchmark daily-run \
  --date 20260519 \
  --results-repo ../AgentStockBenchmarkResults \
  --strategy 20260519__OpenAI__O3__LinearNeutral
```

强制覆盖已有产物：

```bash
PYTHONPATH=src python -m agentstockbenchmark daily-run \
  --date 20260519 \
  --results-repo ../AgentStockBenchmarkResults \
  --overwrite
```

## 数据回测 (Backfill)

回测所有阶段（数据、排名、组合、核算）：

```bash
cd AgentStockBenchmark
PYTHONPATH=src python -m agentstockbenchmark backfill \
  --start 20260501 \
  --end 20260519 \
  --step all \
  --results-repo ../AgentStockBenchmarkResults
```

仅回测会计核算、指标和排行榜：

```bash
PYTHONPATH=src python -m agentstockbenchmark backfill \
  --start 20260501 \
  --end 20260519 \
  --step accounting \
  --data-dir ../AgentStockBenchmarkResults/data/parquet \
  --results-repo ../AgentStockBenchmarkResults
```

## 第一阶段：提示词与策略 (Stage 1)

列出所有提示词：

```bash
PYTHONPATH=src python -m agentstockbenchmark stage1 list-prompts
```

验证特定提示词下的策略导入是否正常：

```bash
PYTHONPATH=src python -m agentstockbenchmark stage1 validate-strategies \
  --prompt-id 20260519
```

## 数据修复 (Repair Data)

如果某日的生产运行启动过早（导致数据不完整）或下载过程中出现网络故障，请使用 `repair-date` 强制刷新市场数据并更新受影响的历史损益：

```bash
cd AgentStockBenchmark
PYTHONPATH=src python -m agentstockbenchmark repair-date \
  --date 20260521 \
  --results-repo ../AgentStockBenchmarkResults
```

该命令将：
1. **强制刷新数据**：重新下载该日完整的市场数据，覆盖之前不完整的 CSV。
2. **同步 Parquet**：将修复后的 CSV 重新合并到全局 Parquet 表中。
3. **刷新会计核算**：重新计算所有将该日作为入场或出场价格的历史排名日损益。
4. **更新排行榜**：重新生成指标和累计收益图表。

## 结果发布 (Publish)

在审计通过后，从结果仓库运行发布命令：

```bash
cd AgentStockBenchmarkResults
PYTHONPATH=src python -m agentstockbenchmark_results publish \
  --date 20260519 \
  --results-repo . \
  --push  # 可选：尝试执行 Git commit 和 push
```

## 研究工作流 (Research)

创建一个策略生成工作区：

```bash
cd AgentStockBenchmark
PYTHONPATH=src python -m agentstockbenchmark research generate-strategies \
  --prompt-id 20260519 \
  --results-repo ../AgentStockBenchmarkResults
```

对研究运行进行回测：

```bash
PYTHONPATH=src python -m agentstockbenchmark research backtest \
  --prompt-id 20260519 \
  --run-id <run_id> \
  --start 20260501 \
  --end 20260519 \
  --results-repo ../AgentStockBenchmarkResults
```

正式晋升研究策略到生产环境：

```bash
PYTHONPATH=src python -m agentstockbenchmark research promote \
  --run-id <run_id> \
  --strategy-id <strategy_id> \
  --results-repo ../AgentStockBenchmarkResults
```

## 常见问题 (Common Problems)

**策略导入失败**：
运行 `stage1 validate-strategies` 检查错误。若是智能体代码本身的语法错误，应予以保留，除非明确要求修复。

**未出现会计核算行**：
检查 Parquet 中是否已包含排名日之后的 $t+1$ 和 $t+2$ 交易日数据。系统不会为无法结算的日期凭空制造收益。

**审计提示合并验证失败**：
若数据不完整（如抓取过早），请使用 `repair-date` 命令修复。
