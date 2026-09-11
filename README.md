# KnowledgePilot

KnowledgePilot 是一个用于学习和实践大语言模型应用开发的本地项目。项目从本地对话逐步扩展到文档检索、RAG 和 Tool Calling，并保持每个版本的能力边界清晰、可验证。

## 当前版本：V0.9 Tool Calling

V0.9 已实现单轮 Tool Calling：模型可以直接回答，也可以在 `calculator` 与 `search_knowledge_base` 之间自主选择一个工具。应用层执行一次 Python Tool，将 Tool Result 写回消息历史，再由第二次 Ollama 请求生成最终回答。

```text
用户问题
↓
第一次 Ollama（携带两个 Tool Schema）
↓
直接回答，或产生 tool_calls
↓
只处理 tool_calls[0]
↓
execute_tool_call() → TOOL_REGISTRY → Python Tool
↓
Assistant Tool Call + Tool Result 写回 messages
↓
第二次 Ollama（不再携带 tools）
↓
Final Answer
```

### V0.9 已实现

- `calculator`：加、减、乘、除
- `search_knowledge_base`：检索持久化 Chroma 知识库，返回 `content + source`
- 两个 Tool Schema
- Tool Registry 与 Tool Executor
- dict / JSON string 两种 Tool arguments
- LLM 自主选择 Tool
- Tool Result 回写 messages
- 第二次 Ollama 生成 Final Answer
- 普通问题不调用 Tool 的 fallback

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

### 当前限制

- 一次只执行 `tool_calls[0]`
- 第二次 LLM 请求不再传入 `tools`，不能再次选择 Tool
- 尚未实现 Agent Loop
- 尚未实现 Stop Condition
- Planner、Memory、MCP、FastAPI 与多步 Agent 属于 V1.0 或以后
- 文档加载当前以 TXT 为主，不支持 PDF
- 对话上下文只保存在单次程序运行期间

## 运行环境

- Windows 11
- Python 3.11.16
- Ollama 0.33.3
- 对话模型：`gemma4:e2b`
- Embedding 模型：`bge-m3`
- Python 依赖：`requests==2.34.2`、`chromadb==1.5.9`
- 项目解释器：`D:\Anaconda\envs\knowledge-pilot\python.exe`

运行前需要启动 Ollama，并确认本地已安装上述模型。

安装依赖：

```bash
python -m pip install -r requirements.txt
```

在 PyCharm 中可使用 `ollama_client`、`knowledge_base_tool` 或 `registry` 稳定运行配置，Working Directory 均为 `$PROJECT_DIR$`，PYTHONPATH 为 `$PROJECT_DIR$/src`。

在 PowerShell 中启动正式交互入口：

```powershell
$env:PYTHONPATH = "src"
python src/knowledge_pilot/llm/ollama_client.py
```

运行知识库 Tool 或 Registry 验证：

```powershell
$env:PYTHONPATH = "src"
python src/knowledge_pilot/tools/knowledge_base_tool.py
python src/knowledge_pilot/tools/registry.py
```

运行最小自动化测试：

```powershell
$env:PYTHONPATH = "src"
python -m unittest tests.test_tools_unit -v

$env:KNOWLEDGE_PILOT_RUN_INTEGRATION = "1"
python -m unittest tests.test_knowledge_base_integration -v
```

知识库默认使用项目根目录下的 `data/vector_store`，Collection 名称为 `knowledge_pilot_docs`。

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
│  ├─ test_tools_unit.py
│  └─ test_knowledge_base_integration.py
├─ docs/
│  └─ devlog/
│     └─ V0.9.md
├─ data/
├─ logs/
├─ pyproject.toml
├─ requirements.txt
└─ README.md
```

`data/` 和 `logs/` 是本地运行目录，不提交到 Git。

## 下一版本边界

V1.0 再考虑多轮 Agent Loop、多个 Tool Call、Action → Observation → Action、Stop Condition、Planner 等能力。V0.9 不提前实现这些内容。
