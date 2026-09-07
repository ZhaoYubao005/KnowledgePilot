# KnowledgePilot

KnowledgePilot 是一个用于学习和实践大语言模型应用开发的本地项目。项目从最小可运行功能开始，逐步理解模型调用、上下文管理和后续 Agent 系统所需的核心机制。

## 当前版本：V0.5

V0.5 已实现：

- 通过 Ollama HTTP API 调用本地模型
- 在命令行中连续进行多轮聊天
- 在单次运行期间保存用户与模型的对话历史
- 使用 `system`、`user`、`assistant` 三类消息角色
- 通过 System Prompt 将助手身份设为“智库”
- 约束回答保持清晰、简洁
- 面对不确定的信息时明确说明，不编造答案
- 新增独立配置层 `config.py`
- 将 Ollama API 地址、模型名称和 System Prompt 从聊天主程序移入配置层
- 可通过修改 `MODEL_NAME` 切换本地 Ollama 模型
- 完成 `src` 布局下的 Python 包导入和 PyCharm 运行配置
- 通过 `load_text(file_path)` 以 UTF-8 编码读取 TXT 文档
- 通过 `chunk_text(text, chunk_size, overlap)` 按固定长度切分文本
- 支持相邻 Chunk 保留指定长度的重叠内容
- 避免在文本末尾生成完全重复的超短 Chunk
- 通过本地 Ollama `bge-m3` 模型生成文本 Embedding
- 支持单段文本与多个 Chunk 的批量向量化
- 通过余弦相似度比较 Query 与 Chunk 的语义相关性
- 按相似度降序返回 Top-K 检索结果
- 使用真实长文档验证 29 个 Chunk 对应 29 个 1024 维向量
- 输入 `exit` 结束聊天

当前文档模块仅支持基础 TXT 文本，不支持 PDF。Embedding 与 Retrieval 在运行时实时计算，尚未接入向量数据库或持久化存储。对话上下文只保存在程序运行期间，关闭程序后不会持久化。

## 运行环境

- Windows 11
- Python 3.11.16
- Ollama 0.33.3
- 对话模型：`gemma4:e2b`
- Embedding 模型：`bge-m3`
- Python 依赖：`requests==2.34.2`
- 项目解释器：`D:\Anaconda\envs\knowledge-pilot\python.exe`

运行前需要启动 Ollama，并确认本地已安装上述模型。

安装依赖：

```bash
python -m pip install -r requirements.txt
```

在 PyCharm 中可使用 `ollama_client`、`embedding` 或 `retriever` 运行配置直接运行。在 PowerShell 中运行：

```powershell
$env:PYTHONPATH = "src"
python src/knowledge_pilot/llm/ollama_client.py
```

运行 Embedding 或 Retrieval 验证：

```powershell
$env:PYTHONPATH = "src"
python src/knowledge_pilot/retrieval/embedding.py
python src/knowledge_pilot/retrieval/retriever.py
```

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
│     └─ retrieval/
│        ├─ __init__.py
│        ├─ similarity.py
│        ├─ embedding.py
│        └─ retriever.py
├─ tests/
├─ docs/
├─ data/
├─ logs/
├─ requirements.txt
└─ README.md
```

`data/` 和 `logs/` 是本地运行目录，不提交到 Git。

## 后续路线

后续版本计划按学习进度逐步加入：

1. Vector Store 向量存储
2. RAG 问答
3. Tool Calling
4. Agent Loop
5. 持久化 Memory
6. FastAPI 服务接口

Vector Store、RAG、Tool Calling、Agent Loop、持久化 Memory 和 FastAPI 尚未实现。
