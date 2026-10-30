# KnowledgePilot

KnowledgePilot 是一个用于学习和实践大语言模型应用开发的本地项目。项目从本地 Ollama 对话逐步扩展到文档检索、RAG、Tool Calling 和受控 Agent Loop，并保持每个版本的能力边界清晰、可验证。

## V1.4 发布候选工程集成（等待人工审查）

正式封版仍为 V1.3.0；V1.4 尚未合并 main、创建 Tag 或正式发布。Step 1～4 的配置、Docker 最小部署、Linux 工具、日志/错误处理和 API 集成测试已在独立分支集成。Step 5 的当前验收与 Go/No-Go 见 [最终集成报告](docs/engineering/step5-integration-report.md)，变更与限制见 [V1.4 发布准备说明](docs/engineering/v1.4-release-readiness.md)。

当前全量回归为 479 passed、1 skipped。真正 Uvicorn + 明确模拟的模型 HTTP 上游验证 CRUD、实际 Chroma 和 Agent 工具循环；真实宿主 Ollama 的聊天、Embedding、检索另行记录，不将模拟工具选择描述为真实模型自主决策。Docker 历史 Step 1 验收通过不代表当前候选镜像已重新验收；当前 Engine 状态和原生 Linux 技术债需独立阅读报告。

当前 Python 配置读取进程环境，不自动加载 `.env`；未设置时保持 localhost:11434、原模型和 CWD/data。显式 `KP_DATA_DIR` 必须是绝对路径，包含 `raw_documents` 与 `vector_store`。Compose 读取 `.env`，内部固定 `/app/data`，宿主 Ollama 默认使用 `host.docker.internal:11434`，API 默认仅绑定宿主 127.0.0.1。使用专用数据目录，禁止将验收工具指向原始库或冻结评测库。

本地启动（先设置专用绝对数据路径，并确认已有模型可用）：

```powershell
$env:PYTHONPATH = Join-Path (Get-Location) 'src'
$env:KP_DATA_DIR = Join-Path (Get-Location) 'data'
python -m uvicorn knowledge_pilot.api.app:app --host 127.0.0.1 --port 8000 --workers 1
```

部署操作见 [当前候选部署入口](docs/deployment/release-candidate.md) 和 [Linux 运行说明](docs/deployment/linux-runtime.md)。`/health` 只证明轻量路由可用，不证明模型或数据写入就绪。项目尚无 API 身份认证，不应直接公开暴露。

## 已封版版本：V1.3.0 — RAG Retrieval Optimization

V1.3 增加独立的 Dense、BM25 和 Hybrid + RRF 检索实验链路，复用 V1.2 冻结 Dataset、Corpus 和评分规则；不改动生产 RAG Pipeline、Agent Loop 或 HTTP API 契约。默认检索仍为 Dense。

- Evidence Collector / CaseEvidence：保留 Chunk 身份、顺序、原始分数和逐题状态。
- RunReport / RunProvenance / JSON Writer：记录实际文件 SHA-256、Git/Python 身份，并独占保存 UTF-8 报告。
- Okapi BM25：k1=1.2、b=0.75；标准库中文字符 unigram/bigram 与技术标识符 Tokenizer，不是中文词级分词。
- Hybrid：Dense + BM25 每路 Top-5、RRF 常数60、最终 Top-3；身份去重，记录原始排名/分数与融合贡献，支持明确故障降级。
- 完整单进程安全测试：435 Passed / 0 Failed / 1 Skipped。唯一跳过项需显式启用真实 Ollama/Chroma 集成环境；未新增 Skip/XFail。

四组真实实验统一为 Dataset v1、Corpus corpus_v1、16 条 Retrieval Case、19 个冻结 Chunk、最终 Top-K=3。以下依次为 Hit@3 / Mean Recall@3 / MRR@3：

- Dense：1.000000 / 0.822917 / 0.968750。
- BM25：0.937500 / 0.732292 / 0.906250。
- Hybrid RRF Depth-3：1.000000 / 0.794792 / 0.927083。
- Hybrid RRF Depth-5：1.000000 / 0.794792 / 0.968750。

Hybrid 未全面优于 Dense；16 条固定 Case 和单轮延迟不足以证明普遍优势。降级机制有合成测试，未执行真实故障注入。本版不包含 jieba、Reranker、Hybrid 生产默认切换或其他新算法。

配置、逐 Case 收益/退化、独立 Runtime 复现命令和测试隔离修复见[V1.3 消融与验收说明](docs/evaluation/hybrid_rrf_v13.md)。四份原字节真实报告及 SHA-256 见[归档索引](docs/evaluation/v1.3_reports/archive_index.json)。数据库、缓存和原始运行目录不纳入 Git。

## V1.2 Offline Evaluation Baseline（1.2.0，历史基础）

V1.2 增加固定数据上的 RAG Retrieval 与 Agent 离线评测，保留 V1.0 Agent Loop、V1.1 API、RAG Core 和工具实现。正式 Dataset V1 已冻结：24 条 Case（16 Retrieval、8 Agent），六篇 Corpus 按 500 字符、100 字符 overlap 切为 19 个 Chunk。

### V1.2 已实现

- RAG Metrics：Hit@K、Recall@K、RR@K、MRR、Fact Coverage@K、Evidence Sufficient@K。
- RAG Evaluator / Runner：批量检索、逐题评分、检索耗时及错误记录；检索评测不调用最终答案生成。
- Agent Evaluator / Runner：Decimal 数值匹配、Trace/决策轮数、工具尝试、原生执行契约及任务成功判定。
- Agent Report：保留原始执行与历史评分，按运行身份、Dataset、答案和完整观察哈希绑定人工审核；缺少审核依据的结果保持 Pending。
- 独立进程在首次导入 Chroma 前固定 Evaluation CWD 和绝对 PYTHONPATH；开发知识库不参与评测。
- Evaluation 回归共 274 项，使用 Mock / 构造数据，不依赖真实 Agent、Ollama 或 Chroma。

### 已保存的 Baseline

RAG Top-K=3：[历史报告](data/evaluation/reports/rag_baseline_v1_k3_20261010T143304_819842Z.json)。

- Hit Rate：16/16＝100%；平均 Recall：82.2917%（16题）；MRR：96.875%（16题）。
- Fact Coverage 与 Evidence Sufficient：各为100%（仅4条 Multi-Chunk）。
- 平均检索耗时：287.608 ms（16题，包含首条较高延迟）。

Agent：[原始结果](data/evaluation/reports/agent_batch_raw_v1.json)、[审核记录](data/evaluation/reports/agent_manual_reviews_v1.json)、[正式历史复评分](data/evaluation/reports/agent_baseline_v1.json)、[历史验收记录](data/evaluation/reports/agent_baseline_validation_v1.json)。

- Task Success：4/8＝50%，4成功、4失败、0 Pending、0运行错误。
- Required Tool Hit Rate：7/11＝63.64%（micro：逐题必需工具名称命中数 / 必需名称总数）。
- Invalid Tool Rate：0/7；Average Steps：15/8＝1.875；Error Rate：0/8。
- stop_reason：completed 8/8；completed 不代表任务成功。
- 答案正确、工具尝试、工具执行成功、任务相关性分别判断；不能互相替代。

### Evaluation 运行方法

在项目根目录激活已有环境。首次建库需单独授权，先阅读[冻结输入与重建说明](data/evaluation/README.md)；已初始化环境直接使用以下入口：

```powershell
conda activate knowledge-pilot
$projectRoot = (Resolve-Path '.').Path
$env:PYTHONPATH = Join-Path $projectRoot 'src'

# 默认只检查独立环境，不打开数据库或调用模型
python -B scripts/run_rag_evaluation.py

# 以下是实际评测命令，会调用 Ollama / 独立 Evaluation Chroma
python -B scripts/run_rag_evaluation.py --run-all --k 3
python -B scripts/run_rag_evaluation.py --run-agent-all
```

启动入口从自身路径推导项目根，在新子进程首次导入业务模块前固定 CWD 为 data/evaluation/runtime/corpus_v1、PYTHONPATH 为项目 src，实际库为该 CWD 下的 data/vector_store。无参数入口只检查文件和环境，不创建数据库；内部 --check-env 参数不用于项目根的直接调用。原有 API / CLI 仍从项目根使用开发库。

Agent 批量入口目前只打印完整结果，尚未自动保存带完整环境信息的运行信封。新运行必须另存完整 UTF-8 原始输出；新答案不能继承旧运行的审核结论。离线报告工具只重新评分现有输入，不调用模型，也不覆盖已有输出：

```powershell
python -B scripts/finalize_agent_report.py --historical --raw-run data/evaluation/reports/agent_batch_raw_v1.json --reviews data/evaluation/reports/agent_manual_reviews_v1.json --output data/evaluation/reports/agent_baseline_new_rescore.json
```

完整 Evaluation 回归使用已有 pytest（验收环境为9.1.1）：

```powershell
python -m pytest tests/evaluation -q
```

### V1.2 评分与来源限制

- 普通 Recall 保留全部真实 Relevant；No-answer 不参与普通正例 Recall/MRR 平均。Multi-Chunk 同时报告 Recall、去重 Fact Coverage 和 Evidence Sufficient。
- 数值答案要求完整 ASCII 数值，strip 后使用有限 Decimal 比较；12与12.0等价，不从解释文字中提取数字。
- Agent 任务相关性使用显式 True / False / None 审核；Pending 排除于已判定 Task Success 的分母，报告同时给出总量及 Pending 数量。
- Agent 报告状态保持 HISTORICAL_RESCORED_WITH_PROVENANCE_GAPS。原始运行时间、模型、提示词和环境未知；18段返回正文中17段与当前 Corpus 仅有空白差异，不能证明历史 Chroma 字节一致。当前离线复评分环境与历史运行环境分别记录。
- RAG 历史报告保存逐题成绩，缺少原始 Top-K、距离、Dataset/源码指纹和完整环境信息；它没有当前报告脚本后来增加的错误汇总字段，不能补写历史事实。
- 历史验收 JSON 保留原字节。此次发布仅清理 Runner 注释/空行与入口说明，这些文件的字节哈希会与旧验收快照不同；正式封板另运行完整274项回归，不改写历史证据。
- 冻结 README / Manifest 中的 Git HEAD 和“尚未提交”等措辞是冻结时的历史记录；当前代码身份以发布 Commit 为准。固定 Corpus / Dataset 不随发布改写。
- 仅指定冻结材料与五份 Baseline JSON 进入版本控制；runtime、SQLite、索引二进制、缓存和其他开发数据继续忽略。指定报告及三个复评分指纹源码使用 -text 保留原始字节。
- 该成绩仅代表固定的24条Case。Chroma 相对路径依赖、Ollama 外部依赖、模型随机性和 V1.1 非原子更新等限制仍存在。完整来源说明见[Agent Baseline 说明](docs/evaluation/agent_baseline.md)。

## V1.1 FastAPI API（历史基础）

V1.1 在 V1.0 Agent Loop、RAG、Tool Calling 和 Chroma 能力之上增加 HTTP API，不改变这些核心能力的职责。请求由 FastAPI Route 和 Pydantic 校验，Service Layer 连接现有核心函数，响应模型约束返回的 JSON。

```text
客户端 → FastAPI Route / Pydantic → API Service Layer → V1.0 Agent / Chroma → Response Model → JSON
```

### V1.1 API

- `GET /health`：健康检查，成功为 200。
- `POST /chat`：Agent 对话，成功为 200；请求校验为 422；Ollama 返回非 JSON 为 502、连接不可用为 503。
- `POST /documents`：上传 UTF-8 TXT 并写入 Chroma，成功为 201；文件无效为 400、请求校验为 422、Embedding 返回非 JSON 为 502、连接不可用为 503。
- `GET /documents`：按 `document_id` 聚合文档，返回 `DocumentResponse` 列表，成功为 200。
- `PUT /documents/{document_id}`：更新文档，成功为 200；文件无效为 400、文档不存在为 404、请求校验为 422、Embedding 返回非 JSON 为 502、连接不可用为 503。
- `DELETE /documents/{document_id}`：删除文档及受管理的 raw 文件，成功为 200；文档不存在为 404、请求校验为 422。

上传与更新使用 `data/raw_documents/{document_id}/` 保存原始 TXT。Pydantic 定义请求/响应模型；各 Route 的已处理状态码在 OpenAPI / Swagger 中声明。V1.1 当时不包含 Memory、MCP、LangChain、Docker 或 Web UI；V1.4 候选已补 Docker 和可配置数据根。

### V1.1 已知限制

`PUT /documents/{document_id}` 不是原子更新：旧 Chroma Chunk 先删除，再写入新 Chunk；失败时 raw 文件有最小回滚保护，但旧 Chunk 可能丢失。此风险在 V1.4 候选仍存在。V1.1 当时缺少的 Ollama timeout、状态码与响应结构检查已由 V1.4 Step 3 补充。历史风险与故障记录见 [V1.1 开发与技术债记录](docs/devlog/V1.1.md)。

## V1.0 Agent Loop（历史基础）

V1.0 将 V0.9 的单步 Tool Calling 升级为循环式 Agent 决策。模型可以直接回答，也可以选择 `calculator` 或 `search_knowledge_base`；Tool Result 作为 Observation 写回消息历史后，模型仍然拥有全部 tools，可以继续进行下一轮 Decision，直到正常完成或达到最大步骤限制。

```text
用户问题
↓
Decision：Ollama 根据 messages 与 Tool Schema 决定直接回答或调用 Tool
↓
没有 tool_calls ───────────────→ completed
↓ 有 tool_calls
Action：顺序执行本轮全部 tool_calls
↓
Observation：Tool Result 写回 messages，并记录 Agent Trace
↓
下一轮 Decision（仍携带全部 tools）
↓
completed 或 max_steps
```

### V1.0 已实现

- 本地 Ollama 命令行对话与 System Prompt
- TXT 文档加载、Chunk、Embedding 与 Retrieval
- 持久化 Chroma Vector Store
- Multi-document RAG，支持来源 Metadata 与 `document_id` 过滤
- RAG Pipeline；`answer_with_rag()` 继续返回字符串答案与 sources
- `calculator`：加、减、乘、除
- `search_knowledge_base`：返回严格的 `content + source`
- 两个 Tool Schema、Tool Registry 与 Tool Executor
- dict / JSON string 两种 Tool arguments
- 由 LLM 根据用户意图和 Tool Schema 自主选择 Tool
- Agent Loop 与跨轮 Multi-step Tool Calling
- Observation 写回后再次进行 LLM Decision
- 同一轮中的多个 `tool_calls` 全部顺序执行
- Tool 执行异常转换为 Error Observation，并继续下一轮 Decision
- `max_steps` 最大决策轮数，默认值为 5
- Stop Reason：`completed`、`max_steps`
- Agent Trace：记录 `step`、`tool`、`arguments`、`result`
- Agent Result：统一返回 `answer`、`trace`、`stop_reason`
- Malformed Tool Call 基础保护：缺少 `function.name` 或 `function.arguments` 时生成 Error Observation；缺少名称时使用 `unknown_tool`
- 普通问题不调用 Tool，直接返回回答

### Agent Result

`chat_with_ollama(messages, max_steps=5)` 返回：

```python
{
    "answer": "最终回答",
    "trace": [
        {
            "step": 1,
            "tool": "calculator",
            "arguments": {
                "a": 19,
                "b": 32,
                "operation": "multiply",
            },
            "result": 608,
        }
    ],
    "stop_reason": "completed",
}
```

`max_steps` 统计 LLM 决策轮次，不是 Tool 数量。同一轮出现多个 Tool Call 时，它们具有相同的 step，并分别形成 Trace 与 Observation。

### 版本演进

- V0.1：本地 Ollama 命令行聊天
- V0.2：System Prompt
- V0.3：Config Layer
- V0.4：TXT Document Loader 与 Chunk
- V0.5：Embedding 与 Retrieval
- V0.6：RAG Generation，将检索结果注入 Prompt 后交给 Ollama 生成回答
- V0.7：Chroma Vector Store 持久化，RAG Pipeline 改用持久化检索
- V0.8：Multi-document RAG，支持多文档入库、来源 Metadata 与文档过滤
- V0.9：Tool Calling，支持计算器、知识库检索、Registry、Executor 与最终回答
- V1.0：Agent Loop，支持 Observation 驱动的再次决策、跨轮多步 Tool Calling、同轮多个 Tool Call、停止原因与执行 Trace
- V1.1：FastAPI、六个 HTTP Route、Pydantic 模型、Service Layer、raw 文件管理、OpenAPI Contract 与 unittest API Contract 测试
- V1.2：冻结 Evaluation Dataset V1、独立 Chroma 环境、RAG / Agent Evaluator 与 Runner、人工审核绑定及正式历史 Baseline

### V1.0 当时的限制（历史）

- 当前是单 Agent、顺序 Tool Executor，不支持并行 Tool 执行或 Multi-Agent
- 当前没有独立 Planner
- 对话历史只保存在当前程序进程中，没有 Memory 或长期记忆
- V1.0 当时尚未实现 MCP、FastAPI 与 Web UI；FastAPI 在 V1.1 引入
- 文档加载当前以 TXT 为主，不支持 PDF
- Tool Observation 当前使用 `str(result)`，不是结构化 JSON
- Ollama HTTP 请求当前没有 timeout，也没有显式检查 HTTP status code
- Malformed Tool Call 保护目前只覆盖缺少 `function.name` 和 `function.arguments` 的基础场景
- Chroma 使用相对路径，运行时依赖正确的 Working Directory

## 本机运行环境（历史记录）

以下为此前本机运行记录，不是已恢复 Agent 历史运行的环境证明。

- Windows 11
- Python 3.11.16
- Ollama 0.34.0
- 对话模型：`gemma4:e2b`
- Embedding 模型：`bge-m3`
- Python 直接依赖：`requests==2.34.2`、`chromadb==1.5.9`、`fastapi[standard]==0.141.1`、`pydantic==2.13.5`
- 项目解释器：`D:\Anaconda\envs\knowledge-pilot\python.exe`

运行前需要启动 Ollama，并确认本地已安装上述两个模型。

### 原有 API / CLI 的 Working Directory 与 PYTHONPATH

以下为未设置 `KP_DATA_DIR` 时的历史本地运行约定；V1.4 候选可通过绝对数据路径消除数据位置对 CWD 的依赖。原有 API / CLI 从项目根目录 `D:\AI_develop\KnowledgePilot` 运行时，默认库等价于：

```python
chromadb.PersistentClient(path="data/vector_store")
```

因此只有在项目根目录启动时，该路径才会解析为正式数据库：

```text
D:\AI_develop\KnowledgePilot\data\vector_store
```

Collection 名称为 `knowledge_pilot_docs`。如果从其他目录启动，可能连接到另一个空数据库。

PyCharm 本机 Run Configuration 应保持：

```text
Working Directory=$PROJECT_DIR$
PYTHONPATH=$PROJECT_DIR$/src
```

`.idea/` 当前被 Git 忽略，这些配置不会随仓库自动分发到其他环境。

### 安装依赖

```powershell
Set-Location "D:\AI_develop\KnowledgePilot"
$python = "D:\Anaconda\envs\knowledge-pilot\python.exe"
& $python -m pip install -r requirements.txt
```

也可以先激活对应 Conda 环境，再将后续命令中的 `& $python` 替换为 `python`。

### 启动 V1.1 FastAPI

先启动 Ollama；`services.py` 导入时会初始化使用相对路径的 Chroma collection。在项目根目录执行：

```powershell
conda activate knowledge-pilot
$env:PYTHONPATH = "src"
fastapi dev src/knowledge_pilot/api/app.py
```

Swagger 页面：[http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)；OpenAPI JSON：[http://127.0.0.1:8000/openapi.json](http://127.0.0.1:8000/openapi.json)。开发服务器默认仅供本机开发，不代表生产部署配置。

### 启动 V1.0 CLI 交互入口

```powershell
Set-Location "D:\AI_develop\KnowledgePilot"
$env:PYTHONPATH = "src"
$python = "D:\Anaconda\envs\knowledge-pilot\python.exe"
& $python src/knowledge_pilot/llm/ollama_client.py
```

输入 `exit` 结束程序。

### 运行知识库 Tool 或 Registry

```powershell
Set-Location "D:\AI_develop\KnowledgePilot"
$env:PYTHONPATH = "src"
$python = "D:\Anaconda\envs\knowledge-pilot\python.exe"
& $python src/knowledge_pilot/tools/knowledge_base_tool.py
& $python src/knowledge_pilot/tools/registry.py
```

### V1.1 历史自动化测试

```powershell
Set-Location "D:\AI_develop\KnowledgePilot"
$env:PYTHONPATH = "src"
$env:KNOWLEDGE_PILOT_RUN_INTEGRATION = "1"
$python = "D:\Anaconda\envs\knowledge-pilot\python.exe"
& $python -B -m unittest discover -s tests -v
```

V1.1 封版前回归共 40 项（V1.0 原有 21 项 + V1.1 API Contract 19 项）：

- 10 项 calculator、Schema、Registry 与 Tool arguments 单元测试
- 9 项 Agent Loop 确定性 Mock 测试，不请求真实 Ollama
- 1 项 RAG Pipeline 返回契约 Mock 测试
- 1 项真实知识库集成测试，使用本地 Embedding 服务与 Chroma 数据（受限环境使用临时副本）
- 19 项 FastAPI Contract 测试，使用 Mock Service，不真实调用 Ollama、Embedding 或 Chroma

知识库集成测试只有在 `KNOWLEDGE_PILOT_RUN_INTEGRATION=1` 时运行。2026-09-24 的完整回归在临时 Chroma 副本上得到 40/40 通过；当前受限测试环境直接打开原始数据库会报 `attempt to write a readonly database`，原始 Chroma 文件哈希在隔离回归前后保持一致。正常可写的本机环境可按上面的命令运行完整测试。

## 项目结构

```text
KnowledgePilot/
├─ src/
│  └─ knowledge_pilot/
│     ├─ __init__.py
│     ├─ api/
│     │  ├─ __init__.py
│     │  ├─ app.py
│     │  ├─ schemas.py
│     │  └─ services.py
│     ├─ config.py
│     ├─ document/
│     │  ├─ __init__.py
│     │  └─ text_loader.py
│     ├─ evaluation/
│     │  ├─ rag_metrics.py / rag_evaluator.py / rag_runner.py
│     │  └─ agent_evaluator.py / agent_runner.py / agent_report.py
│     ├─ llm/
│     │  ├─ __init__.py
│     │  └─ ollama_client.py
│     ├─ rag/
│     │  ├─ __init__.py
│     │  ├─ pipeline.py
│     │  └─ prompt_builder.py
│     ├─ retrieval/
│     │  ├─ __init__.py
│     │  ├─ similarity.py
│     │  ├─ embedding.py
│     │  └─ retriever.py
│     ├─ tools/
│     │  ├─ __init__.py
│     │  ├─ calculator.py
│     │  ├─ knowledge_base_tool.py
│     │  ├─ registry.py
│     │  └─ schemas.py
│     └─ vector_store/
│        ├─ __init__.py
│        └─ chroma_store.py
├─ scripts/
│  ├─ run_rag_evaluation.py
│  └─ finalize_agent_report.py
├─ tests/
│  ├─ evaluation/
│  ├─ test_agent_loop.py
│  ├─ test_api_contract.py
│  ├─ test_knowledge_base_integration.py
│  ├─ test_rag_pipeline.py
│  └─ test_tools_unit.py
├─ docs/
│  ├─ evaluation/agent_baseline.md
│  └─ devlog/
│     ├─ V0.9.md
│     ├─ V1.0.md
│     └─ V1.1.md
├─ data/
│  └─ evaluation/  # 固定Corpus、Dataset、Manifest与指定Baseline报告
├─ logs/
├─ .gitignore
├─ pyproject.toml
├─ requirements.txt
└─ README.md
```

data/ 仅追踪指定 Evaluation 冻结材料和五份 Baseline 报告，其余开发数据与 runtime、logs/、.idea/、生成的 *.egg-info/ 继续忽略。

## V1.0 边界（历史）

V1.0 的范围是受 `max_steps` 约束的单 Agent 循环式 Tool Calling。Memory、长期记忆、Planner、Multi-Agent、MCP、FastAPI、Web UI 和并行 Tool 执行均未包含在 V1.0 中。FastAPI API 是 V1.1 新增能力；其余能力仍不能作为当前版本功能声明。

## V1.5 LangGraph Workflow 开发分支

新增独立 `POST /workflow/chat`，原 `/chat` 保持原 Agent Loop。
工作流：初始化 → Schema 路由 → 直接回答 / 知识库检索 / 计算器 → 生成 → 结束。
默认 `route=auto` 通过 Ollama 结构化输出判断；也可显式指定 `direct`、`rag`、`tool`。

```powershell
python -m pip install -r requirements.txt -c requirements-workflow-lock.txt
python -m pip install --no-deps -e .
python -m uvicorn knowledge_pilot.api.app:app --host 127.0.0.1 --port 8000
Invoke-RestMethod http://127.0.0.1:8000/workflow/chat -Method Post -ContentType 'application/json' -Body '{"query":"Calculate 6 * 7 using calculator."}'
```

Python 独立入口：

```python
from knowledge_pilot.workflow.graph import run_workflow
result = run_workflow({"query": "我的上传文档介绍了什么？", "route": "rag", "top_k": 3})
print(result["status"], result["answer"], result["trace"])
```

工作流错误必须检查 `status` 和 `error`；HTTP 200 不代表领域执行成功。
无证据返回 `no_results`；工具/路由失败返回 `failed`；模型错误映射为 502/503/504。

验收：`python scripts/verify_v15_workflow.py --evidence ./data/v15-http.json`。
真实 Ollama：在同一命令追加 `--real-ollama http://localhost:11434`。
验收器只创建自有临时数据，不使用日常 Chroma；真实模式不下载模型。
[源码教学交接](docs/engineering/v1.5-source-handoff.md) · [测试与发布准备](docs/engineering/v1.5-validation.md)。
V1.4 Docker / 原生 Linux 验证缺口继续保留；本分支不是正式版本发布。

## V1.6 Agent Reliability & Memory 开发候选

两个聊天入口均可选传入 `session_id`；省略时保持既有无会话行为。

```powershell
# 在 V1.6 worktree，使用本地独立 .venv
./.venv/Scripts/python.exe -m uvicorn knowledge_pilot.api.app:app --host 127.0.0.1 --port 8000
$session = Invoke-RestMethod http://127.0.0.1:8000/sessions -Method Post
$body = @{query='My embedding model is bge-m3'; route='direct'; session_id=$session.session_id} | ConvertTo-Json
Invoke-RestMethod http://127.0.0.1:8000/workflow/chat -Method Post -ContentType 'application/json' -Body $body
$body = @{query='How many dimensions does that model use?'; route='direct'; session_id=$session.session_id} | ConvertTo-Json
Invoke-RestMethod http://127.0.0.1:8000/workflow/chat -Method Post -ContentType 'application/json' -Body $body
Invoke-RestMethod "http://127.0.0.1:8000/sessions/$($session.session_id)" -Method Get
Invoke-RestMethod "http://127.0.0.1:8000/sessions/$($session.session_id)" -Method Delete
```

`DELETE` 清空历史并保留会话标识；SQLite 位于 `KP_DATA_DIR/sessions.sqlite3`，重启保留。
同一会话同时生成回答时使用 revision 校验；冲突返回 409，不覆盖先完成的历史。
ID 是随机访问凭证；没有认证、过期策略或用户权限系统，只用于受控本地使用。

默认历史最多10个完整对话轮次、12000字符；配置 `KP_SESSION_MAX_TURNS`（1..100）、
`KP_SESSION_MAX_CHARS`（256..100000）。这是历史字符预算，不是精确 token 或全请求预算。
当前问题始终单独传给模型；过大的历史轮次可被整体舍弃。

Workflow 的只读检索遇到明确临时连接/超时错误时有限重试；`KP_TOOL_MAX_ATTEMPTS` 默认2，范围1..3。
计算器参数错误、除零、未知工具不自动重试。恢复信息见可选 `diagnostics`，原节点 `trace` 不变。
旧 Agent Loop 本身仍保持原有行为；此恢复策略在 Workflow 工具边界生效。

验收命令（自有临时数据）：

```powershell
./.venv/Scripts/python.exe -B -m pytest tests -q -p no:cacheprovider --basetemp ./data/pytest-v16
./.venv/Scripts/python.exe -B scripts/verify_v16_memory.py --evidence ./data/v16-simulated.json
./.venv/Scripts/python.exe -B scripts/verify_v16_memory.py --evidence ./data/v16-real.json --real-ollama http://localhost:11434
```

[源码教学包](docs/engineering/v1.6-source-handoff.md) · [验收与限制](docs/engineering/v1.6-validation.md)。
