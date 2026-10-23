# KnowledgePilot V1.4 Step 2 Linux Runtime & Data Persistence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不改变 V1.3 Agent/RAG/检索语义的前提下，为 Linux 单机运行提供明确的数据目录契约、启动/停止脚本、权限预检和可重复持久化验收。

**Architecture:** 继续使用 Step 1 的单 FastAPI 容器、宿主机 Ollama 和内嵌 Chroma。新增脚本只负责部署编排与只读预检；业务进程继续通过 `KP_DATA_DIR` 使用 `/app/data`，Compose 绑定宿主机绝对目录。验收使用全新目录，先写入最小文档，再删除并重建容器验证数据，不迁移或打开 Windows 开发库。

**Tech Stack:** Python 3.11 标准库、PowerShell/portable shell、Docker Compose、FastAPI、Chroma、pytest。

---

## 范围与文件结构

拟新增文件：

```text
scripts/linux/preflight.py               # Linux/容器部署前只读检查与 JSON 输出
scripts/linux/up.sh                      # 受控启动，要求绝对数据目录已存在
scripts/linux/down.sh                    # 仅关闭指定 Compose 项目，不删除宿主数据
scripts/linux/verify_persistence.py       # 一次性目录的真实 HTTP/重建验收
tests/deployment/test_linux_preflight.py  # 环境、路径、权限与配置单元测试
docs/deployment/linux-runtime.md          # Linux 安装、权限、启停与故障处理
docs/deployment/linux-evidence-schema.md  # 验收 JSON 字段及证据边界
```

拟修改文件：

```text
compose.yaml                              # 仅增加 Linux 运行需要且跨平台安全的参数
.env.example                              # 解释 Linux 绝对数据路径和宿主 Ollama 地址
.gitignore                                # 仅在新证据/临时目录未被现有规则覆盖时最小补充
```

明确不修改：`llm/ollama_client.py` 的 Agent Loop、`rag/`、`evaluation/`、BM25/Hybrid/RRF、冻结 `data/evaluation/`、默认 Dense 策略。

### Task 1: Linux 部署前预检契约

**Files:**
- Create: `scripts/linux/preflight.py`
- Test: `tests/deployment/test_linux_preflight.py`

- [ ] **Step 1: 写失败测试**

测试以下独立行为：显式数据目录必须绝对、必须已存在、必须为目录、当前 UID 必须可创建并删除一个探针文件；Ollama base URL 必须为无路径的 HTTP(S) origin；输出 JSON 包含 `platform`、`data_dir`、`writable`、`ollama_url`、`errors`，且不会创建 Chroma。

- [ ] **Step 2: 验证红灯**

```powershell
$env:PYTHONPATH = Join-Path (Get-Location) 'src'
& D:/Anaconda/envs/knowledge-pilot/python.exe -B -m pytest -p no:cacheprovider -q tests/deployment/test_linux_preflight.py
```

预期：因 `scripts/linux/preflight.py` 尚不存在而失败。

- [ ] **Step 3: 最小实现**

实现 `validate_data_dir(Path) -> list[str]`、`validate_ollama_origin(str) -> list[str]` 和 `main()`。只使用 `argparse`、`json`、`os`、`pathlib`、`platform`、`tempfile`、`urllib.parse`；探针文件放在用户明确提供的数据目录内并在 finally 删除。不得导入 `knowledge_pilot.vector_store`。

- [ ] **Step 4: 运行目标测试和配置回归**

```powershell
& D:/Anaconda/envs/knowledge-pilot/python.exe -B -m pytest -p no:cacheprovider -q tests/deployment/test_linux_preflight.py tests/test_configuration.py
```

预期：全部通过，且测试仅使用临时目录。

### Task 2: Linux 启停脚本

**Files:**
- Create: `scripts/linux/up.sh`
- Create: `scripts/linux/down.sh`
- Modify: `.env.example`
- Test: `tests/deployment/test_linux_preflight.py`

- [ ] **Step 1: 增加失败测试**

静态解析脚本，要求 `set -eu`、拒绝空值和相对 `KP_HOST_DATA_DIR`、启动前调用 preflight、使用固定 Compose project 参数、只执行 `up -d api`；down 脚本只执行 `docker compose ... down`，不得包含 `-v`、`rm -rf` 或删除宿主路径。

- [ ] **Step 2: 验证红灯**

运行 Task 1 的测试命令，预期因脚本不存在失败。

- [ ] **Step 3: 实现脚本**

`up.sh` 接受环境中的 `KP_HOST_DATA_DIR`、`KP_OLLAMA_BASE_URL`、可选 `KP_API_PORT`，先用 `python3 scripts/linux/preflight.py` 输出结果，再运行 `docker compose -p knowledgepilot-v14 up -d api`。`down.sh` 只停止同名项目。脚本不得安装包、下载模型、修改 daemon 或系统 DNS。

- [ ] **Step 4: 更新 `.env.example`**

增加 Linux 示例注释：数据目录使用绝对路径；若 Ollama 在同一 Linux 主机且只监听 loopback，容器不能通过网关访问，必须由部署者配置受控监听地址和防火墙。保留 Windows 默认示例，不提交真实地址或密钥。

- [ ] **Step 5: 执行目标测试**

运行 Task 1 的测试命令，预期全部通过。

### Task 3: Linux 持久化验收器

**Files:**
- Create: `scripts/linux/verify_persistence.py`
- Create: `docs/deployment/linux-evidence-schema.md`
- Test: `tests/deployment/test_linux_preflight.py`

- [ ] **Step 1: 写失败测试**

测试验收器的命令生成与安全边界：随机 Compose project、随机环回端口、数据根必须位于调用者提供的验收根之下；清理只允许 `docker compose down`；证据状态只有 `passed`/`failed`，每个检查记录实际命令退出码。

- [ ] **Step 2: 验证红灯**

运行目标测试，预期因模块不存在失败。

- [ ] **Step 3: 最小实现**

复用 `scripts/verify_step1_docker.py` 已验证的检查顺序，但参数化为 Linux：Compose config、镜像身份、容器 `/health`、Ollama tags、真实 Embedding、上传、bind mount、停止/删除/重建、GET `/documents` 与集合内容核对。不得删除宿主数据目录；finally 只 down 自己的项目并写 evidence JSON。

- [ ] **Step 4: 定义 evidence schema 文档**

记录 `run_id`、UTC 时间、Git commit/dirty、Docker/Compose 版本、镜像 ID、平台、数据目录、模型名、每项检查、命令退出码、cleanup 和最终状态。明确目录存在、Mock 或本地进程测试不能替代容器持久化通过。

- [ ] **Step 5: 运行离线测试**

```powershell
& D:/Anaconda/envs/knowledge-pilot/python.exe -B -m pytest -p no:cacheprovider -q tests/deployment tests/test_configuration.py
```

预期：全部通过，不启动 Docker。

### Task 4: Compose Linux 兼容性与文档

**Files:**
- Modify: `compose.yaml`
- Create: `docs/deployment/linux-runtime.md`
- Test: `tests/deployment/test_linux_preflight.py`

- [ ] **Step 1: 先写 Compose 断言**

要求 bind source 来自 `KP_HOST_DATA_DIR`、target `/app/data`、`create_host_path: false`、容器数据根为绝对路径、API 默认只绑定环回地址；Linux 的 `host-gateway` 映射保留。若现有 Compose 已满足，不为了制造 diff 改写它，只保留测试与文档。

- [ ] **Step 2: 运行真实 `docker compose config --quiet`**

在 Windows Docker Desktop 和目标 Linux Docker Engine 各执行一次。两次命令、版本和退出码写入验收记录；某一平台未执行则标记 `PENDING_MANUAL`。

- [ ] **Step 3: 编写 Linux runbook**

覆盖：支持的 Python/Docker/Compose 实测版本、非 root UID 10001 的目录权限、Ollama 网络拓扑、启动/查看日志/停止、备份前停止写入、恢复到新目录、故障处理和回滚边界。不得宣称运行中的 SQLite 文件复制是已验证备份。

- [ ] **Step 4: 运行离线全量回归**

```powershell
$env:PYTHONPATH = Join-Path (Get-Location) 'src'
$env:KNOWLEDGE_PILOT_RUN_INTEGRATION = '0'
& D:/Anaconda/envs/knowledge-pilot/python.exe -B -m pytest -p no:cacheprovider -q
```

预期基线：至少保持 Step 1 的 439 passed、1 skipped；新增测试增加 passed 数，不允许新增 skip/xfail。

### Task 5: 真实 Linux 验收与交接

**Files:**
- Create: `docs/deployment/linux-acceptance-<UTC_RUN_ID>.md`
- Create: `docs/deployment/linux-evidence-<UTC_RUN_ID>.json`

- [ ] **Step 1: 准备全新数据目录**

在目标 Linux 主机创建绝对路径的空验收目录，设置为 UID 10001 可写；记录 `stat`，不使用现有 Windows/开发 Chroma，也不复制冻结评测库。

- [ ] **Step 2: 执行预检和镜像构建**

运行 preflight、`docker compose config --quiet`、`docker compose build api`。记录基础镜像身份、构建退出码和最终镜像 ID；临时镜像获取方式必须单独记录，不写入全局 daemon 配置。

- [ ] **Step 3: 执行真实持久化验收**

运行 `scripts/linux/verify_persistence.py`。验收必须包含真实 Ollama Embedding、宿主原文字节、Chroma sqlite、不同容器 ID 和重建后的集合内容。

- [ ] **Step 4: 检查清理和保护边界**

确认专用容器/网络已移除，测试数据按证据策略保留；`git diff --name-only -- data/evaluation src/knowledge_pilot/evaluation src/knowledge_pilot/rag` 为空，main 用户文件不变。

- [ ] **Step 5: 汇总验收状态**

只有 Compose、构建、真实 Linux 容器、Ollama、持久化、全量回归全部通过才标记 Step 2 PASS。任何未运行项写 `PENDING_MANUAL` 或 `BLOCKED_NOT_RUN`，不使用 Windows Docker Desktop 结果替代 Linux 主机验收。

## 自检结果

- 范围覆盖 Linux 兼容性、路径、权限、数据持久化、部署脚本与可重复证据。
- 无算法重构、模型下载、daemon 全局修改、旧库迁移或冻结数据修改。
- 先测试后实现；离线测试与真实部署验收分层。
- Step 2 需要真实 Linux Docker Engine 才能最终 PASS；仅在 Windows Docker Desktop/WSL 后端执行时必须明确平台边界。
