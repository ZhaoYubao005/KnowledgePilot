# KnowledgePilot

KnowledgePilot 是一个用于学习和实践大语言模型应用开发的本地项目。项目从本地 Ollama 对话逐步扩展到文档检索、RAG、Tool Calling 和受控 Agent Loop，并保持每个版本的能力边界清晰、可验证。

## 当前版本：V1.0 Agent Loop

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

### 当前限制

- 当前是单 Agent、顺序 Tool Executor，不支持并行 Tool 执行或 Multi-Agent
- 当前没有独立 Planner
- 对话历史只保存在当前程序进程中，没有 Memory 或长期记忆
- 尚未实现 MCP、FastAPI 与 Web UI
- 文档加载当前以 TXT 为主，不支持 PDF
- Tool Observation 当前使用 `str(result)`，不是结构化 JSON
- Ollama HTTP 请求当前没有 timeout，也没有显式检查 HTTP status code
- Malformed Tool Call 保护目前只覆盖缺少 `function.name` 和 `function.arguments` 的基础场景
- Chroma 使用相对路径，运行时依赖正确的 Working Directory

## 运行环境

- Windows 11
- Python 3.11.16
- Ollama 0.34.0
- 对话模型：`gemma4:e2b`
- Embedding 模型：`bge-m3`
- Python 依赖：`requests==2.34.2`、`chromadb==1.5.9`
- 项目解释器：`D:\Anaconda\envs\knowledge-pilot\python.exe`

运行前需要启动 Ollama，并确认本地已安装上述两个模型。

### Working Directory 与 PYTHONPATH

必须从项目根目录 `D:\AI_develop\KnowledgePilot` 运行。`chroma_store.py` 使用相对路径：

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

### 启动正式交互入口

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

### 运行完整自动化测试

```powershell
Set-Location "D:\AI_develop\KnowledgePilot"
$env:PYTHONPATH = "src"
$env:KNOWLEDGE_PILOT_RUN_INTEGRATION = "1"
$python = "D:\Anaconda\envs\knowledge-pilot\python.exe"
& $python -B -m unittest discover -s tests -v
```

当前测试共 21 项：

- 10 项 calculator、Schema、Registry 与 Tool arguments 单元测试
- 9 项 Agent Loop 确定性 Mock 测试，不请求真实 Ollama
- 1 项 RAG Pipeline 返回契约 Mock 测试
- 1 项真实知识库集成测试，使用本地 Embedding 服务与正式 Chroma

知识库集成测试只有在 `KNOWLEDGE_PILOT_RUN_INTEGRATION=1` 时运行。

## 项目结构

```text
KnowledgePilot/
├─ src/
│  └─ knowledge_pilot/
│     ├─ __init__.py
│     ├─ config.py
│     ├─ document/
│     │  ├─ __init__.py
│     │  └─ text_loader.py
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
├─ tests/
│  ├─ test_agent_loop.py
│  ├─ test_knowledge_base_integration.py
│  ├─ test_rag_pipeline.py
│  └─ test_tools_unit.py
├─ docs/
│  └─ devlog/
│     ├─ V0.9.md
│     └─ V1.0.md
├─ data/
├─ logs/
├─ .gitignore
├─ pyproject.toml
├─ requirements.txt
└─ README.md
```

`data/`、`logs/`、`.idea/` 和生成的 `*.egg-info/` 是本地运行或工具目录，不作为普通项目源码提交。

## V1.0 边界

V1.0 的范围是受 `max_steps` 约束的单 Agent 循环式 Tool Calling。Memory、长期记忆、Planner、Multi-Agent、MCP、FastAPI、Web UI 和并行 Tool 执行均未实现，不应作为当前版本能力声明。
