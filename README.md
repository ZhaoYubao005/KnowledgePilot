# KnowledgePilot

KnowledgePilot 是一个用于学习和实践大语言模型应用开发的本地项目。项目从最小可运行功能开始，逐步理解模型调用、上下文管理和后续 Agent 系统所需的核心机制。

## 当前版本：V0.2

V0.2 已实现：

- 通过 Ollama HTTP API 调用本地模型
- 在命令行中连续进行多轮聊天
- 在单次运行期间保存用户与模型的对话历史
- 使用 `system`、`user`、`assistant` 三类消息角色
- 通过 System Prompt 将助手身份设为“智库”
- 约束回答保持清晰、简洁
- 面对不确定的信息时明确说明，不编造答案
- 输入 `exit` 结束聊天

当前版本的上下文只保存在程序运行期间，关闭程序后不会持久化。

## 运行环境

- Windows 11
- Python 3.11.16
- Ollama 0.33.3
- 本地模型：`gemma4:e2b`
- Python 依赖：`requests==2.34.2`
- 项目解释器：`D:\Anaconda\envs\knowledge-pilot\python.exe`

运行前需要启动 Ollama，并确认本地已安装上述模型。

安装依赖：

```bash
python -m pip install -r requirements.txt
```

运行程序：

```bash
python src/knowledge_pilot/llm/ollama_client.py
```

## 项目结构

```text
KnowledgePilot/
├─ src/
│  └─ knowledge_pilot/
│     └─ llm/
│        └─ ollama_client.py
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

1. 配置管理和更清晰的模型调用边界
2. RAG 文档检索
3. Tool Calling
4. Agent Loop
5. Memory
6. FastAPI 服务接口

RAG、Tool Calling、Agent、持久化 Memory 和 FastAPI 均尚未实现。
