# Agent Baseline：历史原始输出与离线复评分

## 当前交付边界

2026-10-11：已从 `C:\Users\lenovo\Downloads\agent_batch_raw_v1.json` 恢复此前终端打印的八条完整历史结果，并按原始字节复制到 `data/evaluation/reports/agent_batch_raw_v1.json`。原始文件 SHA-256 为 `056914368dbae1ee0d854672778787ea38c6fd277bbfe63edf29aac003bad865`。没有重新运行 Agent 或 Ollama。

本次使用现有 `finalize_agent_report.py --historical` 和 `agent_report.py`，将原始结果、独立复核和重新评分分别保存：

- `data/evaluation/reports/agent_batch_raw_v1.json`：恢复的原始回答、Trace、停止原因与全部历史评分。
- `data/evaluation/reports/agent_manual_reviews_v1.json`：八条结果的显式复核记录，包括用户已确认的三条答案，以及七次实际调用的相关性依据；绑定运行内容身份、答案和完整观察哈希。
- `data/evaluation/reports/agent_baseline_v1.json`：正式历史复评分报告，旧评分保留在 `source_raw_report` / `raw_result`，当前评分独立计算。
- `data/evaluation/reports/agent_baseline_validation_v1.json`：文件哈希、结构与绑定检查、274条回归测试结果、冻结材料及核心文件未变的证据。

本次结果为4成功、4失败、0 Pending、0运行错误。Task Success为4/8，Required Tool Hit采用按Case去重后的micro口径，为7/11；Invalid Tool为0/7，Average Decision Steps为15/8，Error Rate为0/8，completed为8/8。agent_002、006、007、008通过；001、003未调用calculator，004与005也缺少calculator，004的最终答案还错误地拒绝了已取得的三个字段事实。全部七次实际工具调用的相关性均经过本次逐条证据审核，没有默认通过。

报告状态是 `HISTORICAL_RESCORED_WITH_PROVENANCE_GAPS`。历史时间、模型、环境和原始Dataset字节身份仍为unknown/null；当前离线复评分环境另行记录。18条返回文本中17条与冻结Chunk存在空白差异，去除空白后的内容一致；原文未改写，该诊断不能证明历史Chroma逐字一致。报告和复核文件仍被现有Git规则忽略，本轮没有修改忽略规则或执行提交。上述来源限制不应被包装成一次环境完整的新运行。

## 文件与入口

- `src/knowledge_pilot/evaluation/agent_report.py`：纯离线报告、哈希、复核绑定及历史 Markdown 提取。
- `scripts/finalize_agent_report.py`：读取已有 JSON 或 Markdown，生成一个新报告。
- `tests/evaluation/test_agent_report.py`：离线行为与拒绝错误输入的测试。
- `data/evaluation/cases_v1.json`：冻结 Dataset；命令默认读取此文件，校验其真实字节 SHA-256 与冻结 Manifest，不修改任何冻结内容。

以下命令在 `D:\AI_develop\KnowledgePilot` 执行。输出目录必须已经存在。输入和输出都不会被覆盖；已有报告请使用另一个新文件名。

历史 JSON 已提取时：

```powershell
& 'D:\Anaconda\envs\knowledge-pilot\python.exe' -B scripts/finalize_agent_report.py --historical --raw-run data/evaluation/reports/agent_batch_raw_v1.json --output data/evaluation/reports/agent_baseline_pending_v1.json
```

仅在首次导入尚未保存的原始 Markdown 时使用下列命令。当前原始 JSON 已恢复，不需要再次执行；修改附件路径及输出名为实际可访问位置和新文件名：

```powershell
& 'D:\Anaconda\envs\knowledge-pilot\python.exe' -B scripts/finalize_agent_report.py --markdown --raw-run '实际附件路径\粘贴的 Markdown (1).md' --save-raw data/evaluation/reports/agent_batch_raw_v1.json --output data/evaluation/reports/agent_baseline_pending_v1.json
```

Markdown 模式只接受唯一、完整、八条唯一 Case 的历史批次 JSON；多个候选、截断内容、重复 JSON 键及非有限 JSON 数值都会被拒绝。保存的原始 JSON 是原文中从起始花括号到结束花括号的精确 UTF-8 子串，内部空白、答案、Trace 和旧分数保持原样，不加入包装或新分数。报告另外记录原 Markdown 文件哈希。提取不会把没有原始 Trace 的说明文字转换成运行记录。

完成真实人工复核后，将绑定该次导入的复核文件交给命令：

```powershell
& 'D:\Anaconda\envs\knowledge-pilot\python.exe' -B scripts/finalize_agent_report.py --historical --raw-run data/evaluation/reports/agent_batch_raw_v1.json --reviews data/evaluation/reports/agent_manual_reviews_v1.json --output data/evaluation/reports/agent_baseline_reviewed_v1.json
```

没有复核文件时仍可生成 Pending 报告。命令不会自动写入任何正面复核判定。

## 原始记录与历史来源

普通运行信封包含 `run_id`、`dataset_version`、`dataset_sha256`、`registered_tools`、`started_at_utc`、`finished_at_utc`、`environment`、`cases`。每条正常 Case 包含 `case_id`、原始字符串 `answer`、`trace` 和非空字符串 `stop_reason`。Trace 每条记录必须有 `step`、`tool`、`arguments`、`result`；`step` 是从 1 开始的整数，排除 bool。`arguments` 或 `result` 的值可以为 null，此时继续检查工具执行契约；缺失整个字段属于不可观测记录。

历史终端 JSON 的结构为 `dataset_version`、`agent_case_count`、`registered_tools`、`cases`。规范化时：

- 完整旧报告保留在 `source_raw_report`，各 Case 完整旧行保留在 `raw_result`。
- 新身份为 `historical-agent-v1-` 加原始 JSON 文件的字节 SHA-256。这是导入内容身份，不能当作历史执行 ID。
- 历史 `started_at_utc`、`finished_at_utc`、`environment` 明确为 null/未知。当前电脑配置、模型名、Git HEAD、提示词及数据库路径不会倒填为历史事实。
- 导入后的 Dataset 哈希绑定本次离线复评分所用文件；如果原始终端没有记录历史 Dataset 哈希，则其历史身份仍未知。
- `generated_at_utc` 是本次报告生成时间，独立于历史运行时间。

命令另外记录 `rescore_environment`：当前 Python、包版本元数据、Evaluator/报告模块/命令文件的字节哈希，以及只读 Git HEAD 和工作区是否有改动。它描述当前离线复评分过程。Git HEAD 不能独自代表尚未提交的工作代码。读取包版本无需导入这些业务模块，Git 查询禁用可选锁。

## 人工复核契约

`make_review_record(run, case_id, *, reviewer, rationale, answer_correct=None, task_relevance_by_trace=None, reviewed_at_utc=None)` 只根据明确提供的复核内容在内存中生成记录。调用者必须先实际阅读答案、Trace 和冻结任务要求；该函数不会替人完成复核，也不会自动保存复核文件。

复核信封的 `schema_version` 固定为 `agent_manual_reviews_v1`，并包含 `run_id`、`dataset_sha256` 与 `records`。每条记录包含：

- 同一 `run_id`、`dataset_sha256`、`case_id`。
- 原始答案 UTF-8 字节的 `answer_sha256`；缺少字符串答案的运行错误记录为 null。
- `agent_result_sha256`，绑定已有的 `answer`、`trace`、`stop_reason` 与 `error` 观察字段。任何观察变化都会使旧复核失效。
- `answer_correct`：只能是 true、false 或 null；数值 exact 答案仍由冻结 Decimal 规则重算。
- `task_relevance_by_trace`：使用 Trace 的从 0 开始的索引，JSON 中键为规范整数字符串，如 `"0"`。每个值只能为 true、false 或 null。
- 非空 `reviewer`、`rationale` 以及带 UTC 时区的 ISO `reviewed_at_utc`。

报告拒绝跨运行/跨 Dataset/答案或 Trace 已变化的复核、重复或未知 Case、越界索引、错误判定类型和缺失复核身份。答案哈希不去空白；报告重评分中的数值匹配则依照冻结答案规则去除首尾空白。

规范 JSON 哈希使用 `sort_keys=True`、`ensure_ascii=False`、紧凑分隔符、UTF-8，并拒绝 NaN/Infinity；它与原始源文件字节哈希分别记录。

## 答案、工具、任务的独立判定

`answer_correct`、工具尝试/合法性、`tool_execution_success`、`required_tool_execution_success` 和 `task_relevance` 分别报告。

必需工具名称被尝试，就计入 Required Tool Hit Rate，包括失败尝试。禁止工具任何尝试都违规。Invalid Tool Rate 只判断名称是否在调用方提供的注册名称中。参数与返回值是否符合冻结契约是另一项检查；合法返回并不能自动证明与本题相关。空知识库列表可属于执行成功，但其是否支持拒答仍需任务复核。

每个必需工具至少有一次执行成功且明确相关，才能满足任务相关执行约束。早期失败或无关调用允许由后续相关成功调用恢复。全部成功候选都明确无关时为 false；没有明确相关候选、仍有未复核候选时为 null。无必需工具时该约束自然满足。不从 Case ID、关键词、算式、答案相等或停止原因推断相关性。

每个 Case 的状态是：

- `PASS`：答案和全部必要约束均满足。
- `FAIL`：已知至少一项失败；已知失败优先于其他未复核项。
- `PENDING`：尚不能确定 Task Success，`task_success` 为 null。
- `RUN_ERROR`：运行失败或关键原始观察缺失/无效；`task_success` 为 false，不可观测工具与步数指标为 null。

报告保留每条答案、Trace、工具名、决策轮数、匹配复核和 `pending_fields`。失败工具尝试单列 `tool_failures`，其分类仅是“执行或契约失败”，不臆测原因。工具失败次数与运行错误次数分别统计。合法空 Trace 的尝试数为 0；缺失/无效 Trace 不能被替换成空列表。

历史报告有未复核字段时为 `PENDING_REVIEW`；完成复核后仍保留 `HISTORICAL_RESCORED_WITH_PROVENANCE_GAPS`。普通报告缺少运行来源或复核时为 `BASELINE_PENDING`。这些状态不把来源未知的历史批次标成来源完整的真实新运行。

## 聚合分母

每项聚合保存 `value`、`numerator`、`denominator` 和文字定义；分母为 0 时 value 为 null。

- Task Success Rate：true 数量 / 已确定 true 或 false 的 Case 数。Pending 不进入分母；RUN_ERROR 按冻结单条规则为 false，进入该分母，同时单列错误率。
- Answer Accuracy：正确答案数 / 布尔答案判定数；未复核及不可观测答案不进入分母。
- Required Tool Hit Rate：按 Case 去重后已尝试的必需名称总数 / 可观测 Case 的必需名称总数；不是各 Case 比率的平均。
- All Required Tools Hit Rate：命中全部必需名称的 Case 数 / 有必需工具且可观测的 Case 数。
- Invalid Tool Rate：未注册调用总数 / 全部可观测调用总数；不平均各 Case 的比率。全部合法空 Trace 时没有调用，聚合值为 null。
- Average Decision Steps：可观测决策轮数总和 / 步数可观测的 Case 数。
- Error Rate：RUN_ERROR 数 / 全部八条 Agent Case。
- Stop Reason Distribution：按可观测字符串停止原因计数，另列分母及不可观测数量。

所有 Agent 类别均进入对应 Agent 聚合，包括 no_answer；不混入 Retrieval 的正例分母。报告同时显示 Task Success Pending 数和仍有复核字段的 Case 数。上述 Agent 聚合分母是显式实现选择；冻结文件规定的是单 Case 规则，不应声称这些新增聚合分母来自冻结文件。

## 验证

```powershell
$env:PYTHONPATH = 'src'
& 'D:\Anaconda\envs\knowledge-pilot\python.exe' -B -m pytest tests/evaluation/test_agent_report.py tests/evaluation/test_agent_evaluator.py -p no:cacheprovider -q
```

验证只用构造数据和临时文件，不需要模型、联网、知识库初始化或真实工具执行。测试结果不能替代真实历史八条输出及其人工复核证据。
