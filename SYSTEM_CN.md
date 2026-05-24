# AgentStockBenchmark 系统设计 (System Design)

[English Version](./SYSTEM.md)

本文件详细描述了 `AgentStockBenchmark` 的生产环境设计，以及它与结果存储仓库 `AgentStockBenchmarkResults` 之间的协作边界。本文档旨在帮助维护者和编程智能体深入理解系统架构，而无需从源码开始摸索。

## 项目目标

AgentStockBenchmark 旨在评估由编程智能体生成的股票排名策略。本基准测试必须明确以下三点：

1. 每一份排名是由哪段代码和提示词生成的。
2. 每一个排名日可用的市场数据和股票池（Universe）是什么。
3. 冻结的排名是如何转化为冻结的投资组合并最终实现会计核算的。

系统设计遵循保守原则：生产产物是可追加且可重启的，研究产物是隔离的，日期格式经过规范化，以确保路径匹配和审计检查的可预测性。

## 代码仓库结构

### `AgentStockBenchmark` (核心引擎)

这是引擎仓库，拥有以下内容：

- 位于 `prompts/<prompt_id>/prompt.md` 的提示词；
- 位于 `prompts/reference/` 的参考提示词；
- 位于 `strategies/<prompt_id>/<strategy_slug>/strategy.py` 的智能体提交策略；
- 策略元数据 `strategy.json`；
- 命令行入口 `agentstockbenchmark`；
- 阶段性模块 (Stage modules)；
- 每日工作流、审计、清单 (Manifests) 及研究编排逻辑；
- 本地测试用例。

### `AgentStockBenchmarkResults` (结果仓库)

这是结果仓库，拥有以下内容：

- 原始及衍生的 OHLCV 市场数据；
- 冻结的排名 CSV 文件；
- 冻结的投资组合 CSV 文件；
- 损益核算输出；
- 评估指标与排行榜；
- 运行、产物、审计、策略和发布清单；
- 结果端命令行入口 `agentstockbenchmark-results`。

引擎负责将生产结果写入 `AgentStockBenchmarkResults`；结果包负责渲染并发布已通过审计的产物。这种分离确保了复杂的基准测试逻辑不会污染公开的结果展示界面。

## 规范化日期约定

`YYYYMMDD` 是新产物唯一规范的持久化日期格式。

支持的 CLI 输入格式：

- `20260519`
- `2026-05-19`
- 某些命令支持 `today`

持久化输出：

- 路径组件使用 `YYYYMMDD`；
- CSV 产物的日期列使用 `YYYYMMDD`；
- JSON 清单的日期字段使用 `YYYYMMDD`；
- 诸如 `generated_at_utc` 的时间戳使用 ISO 8601 格式（因为它们是挂钟时间，而非基准测试业务日期）。

示例路径：

```text
data/universe/20260519.txt
data/raw/daily/20260519.csv
rankings/20260519/20260519__OpenAI__O3__LinearNeutral.csv
portfolios/20260519/20260519__OpenAI__O3__LinearNeutral.csv
accounting/metrics/20260519.csv
manifests/runs/20260519.json
manifests/artifacts/20260519.json
manifests/audits/20260519.json
```

日期处理助手位于 `agentstockbenchmark.dates`。新代码应优先使用该模块，而非直接调用 `datetime.date.fromisoformat`。

## 原子化写入

生产环境的写入操作使用 `agentstockbenchmark.io` 中的“临时文件-重命名”助手：

- `atomic_write_text`
- `atomic_write_json`
- `atomic_write_csv`
- `atomic_write_parquet`

原子化写入能够保护读取者免受每日生产、恢复或发布操作中可能产生的损坏或未完成文件的影响。

## 第一阶段 (Stage 1)：提示词与策略

第一阶段管理基准测试指令和提交的策略代码。

提示词布局：
`prompts/<prompt_id>/prompt.md`

策略布局：
`strategies/<prompt_id>/<strategy_slug>/strategy.py`

`strategy_id` 派生规则：
`<prompt_id>__<strategy_slug>`

缓存策略迁移是一次性的。它将缓存的策略文件夹拷贝到带日期的策略布局中。系统不会自动修复智能体输出的代码。如果提交的策略存在语法错误，除非管理员显式要求修复，否则该错误将被视为基准测试结果的一部分被保留。

## 第二阶段 (Stage 2)：市场数据与冻结排名

第二阶段承担两项职责：

1. 为策略执行准备 OHLCV 数据。
2. 运行策略代码并在进行任何投资组合或会计步骤之前冻结排名产物。

### 衍生 Parquet 格式
派生的 Parquet 是字段级别的宽表：
- 索引 (Index)：交易日期；
- 列 (Columns)：股票代码 (Tickers)；
- 值 (Values)：数值化的 OHLCV 数据。

缺失值在派生 Parquet 中被编码为 `0`。策略代码应将 `0` 视为缺失值。

### 股票池漂移 (Universe Drift)
标普 500 成分股随时间变化。每个生产日期都有一个对应的 `universe` 文件。投资组合构建必须使用对应排名日期的 universe 文件，以确保严谨性。

### 策略快照契约
策略接收一个 `dict[str, pandas.DataFrame]`，其中包含截至排名日（含当日）的所有可用历史数据。

## 第三阶段 (Stage 3)：冻结投资组合、会计与指标

第三阶段从冻结的排名产物开始，**不调用** 任何策略代码。

### 投资组合构建
构建规则：
- 股票池使用对应排名日期的标普 500 universe；
- 不在 universe 中的排名股票将被忽略；
- universe 中缺失排名的股票将按代码字母顺序插入到排名中位数位置；
- 线性美元中性阶梯范围从 `+250` 到 `-250`。

中位数插入规则避免了将缺失名称隐式放在极端多头或极端空头位置，同时确保了全宇宙的会计核算完整性。

### 会计核算 (Accounting)
会计核算遵循收盘价契约：
- 排名日期为 $t$
- 在 $t+1$ 收盘时入场
- 在 $t+2$ 收盘时出场

若入场或出场价格为 `0`、缺失或非数值，会计步骤将跳过该头寸。

## 每日生产工作流

顶层的 `daily-run` 命令执行以下操作：
1. 下载 universe；
2. 下载每日 CSV；
3. 将每日 CSV 合并到 Parquet；
4. 验证合并；
5. 为活跃策略生成排名；
6. 构建投资组合；
7. 更新会计核算；
8. 重建指标与排行榜；
9. 写入各类清单。

## 失效模型 (Failure Model)

失败是基准测试预期的一部分，且应当是可见的。

例如：
- 策略语法错误应出现在 `stage1 validate-strategies` 中；
- 策略运行时错误应出现在排名生成状态中；
- 缺失数据将导致合并验证或审计失败。

不要默认隐藏智能体的策略失效。本项目评估的是编程智能体的提交质量，因此无效代码也是一种极具参考价值的基准测试结果。

## 重要不变性 (Invariants)

- 持久化日期格式为 `YYYYMMDD`。
- 第二阶段排名在第三阶段投资组合之前冻结。
- 第三阶段从不调用策略代码。
- 研究产物严格隔离在 `research/` 目录下。
- `0` 在策略端数据中代表 OHLCV 缺失。
- 发布产物前必须通过审计。
