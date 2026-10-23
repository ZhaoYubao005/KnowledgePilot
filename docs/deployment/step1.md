# V1.4 Step 1 — Configuration & Docker Minimum Deployment

2026-10-23。实现、本地验证与 Docker 真实部署验收均已完成。**最终状态：PASS。**

**最终 Docker 验收（2026-10-23）**：Docker Hub 直连问题未改全局 daemon 配置；验收执行者通过 DaoCloud 临时拉取并 retag `python:3.11-slim` 后完成原 Dockerfile 构建。真实 Compose、容器 `/health`、宿主机 Ollama、1024 维 bge-m3 Embedding、文档落盘、绑定挂载及删容器重建后的 Chroma 持久化共 9/9 通过。最终证据见 [验收报告](step1-docker-acceptance-20261023.md) 与 [机器可读通过证据](docker-evidence-20261023T075418Z-8fba4c.json)。此前的 [阻断诊断](step1-docker-validation.md) 与 [失败证据](docker-evidence-20261023T070821Z-5cf687.json) 作为历史过程保留，不再代表当前状态。

## 工作区与边界

独立 worktree：`C:\Users\lenovo\.codex\.chatgpt-projects\g-p-6a9c0574f0648191afc307eb07a1456b\KnowledgePilot-v14-step1`，detached HEAD 基于 v1.3.0 提交 `268887c0bd7f1c987317fd07d0b4e221d38b84df`。未提交、推送或创建 Tag。原 `D:\AI_develop\KnowledgePilot` main 及 12 个未跟踪面试资料文件不作改动。

未进入 Step 2–5：无 readiness、统一异常/日志、超时重试、算法调整、CI、备份系统或旧库迁移。生产默认仍为 Dense。内嵌 Chroma 仍导入时初始化，文档更新仍非原子，/health 仍只表示进程路由可用。

## 文件用途

- `src/knowledge_pilot/config.py`：标准库读取并验证环境；保留 SYSTEM_PROMPT、OLLAMA_URL、MODEL_NAME 兼容接口。
- `src/knowledge_pilot/retrieval/embedding.py`：仅将硬编码地址和模型替换为配置引用。
- `src/knowledge_pilot/vector_store/chroma_store.py`：持久库位置改为 DATA_DIR/vector_store。
- `src/knowledge_pilot/api/services.py`：三个原文路径引用改为 DATA_DIR/raw_documents。
- `.env.example`：Compose 示例变量，不包含真实密钥。
- `Dockerfile`：Python 3.11 slim、pip 安装当前项目、非 root、单 worker 真实 ASGI 入口。
- `.dockerignore`：构建上下文仅放行 Dockerfile、pyproject、README、src，排除数据库、环境文件、缓存、测试和历史资料。
- `compose.yaml`：单 API 服务、环回端口发布、宿主机 Ollama 寻址、完整 data 绑定挂载；目录不存在时拒绝启动。
- `tests/test_configuration.py`：新解释器验证缺省值、覆盖、非法输入、Embedding 实际调用参数。
- `scripts/verify_step1_local.py`：手动执行的真实 HTTP/Ollama/临时 Chroma 验证器，自动停止子进程并清理其新建临时目录，不由 pytest 默认运行。
- `docs/deployment/step1-plan.md`、本文：执行计划、使用与验收证据。

## 配置与调用链

进程环境 → config.py（导入时读取一次）→ Ollama client 的 OLLAMA_URL / MODEL_NAME，以及 Embedding 的 EMBEDDING_URL / EMBEDDING_MODEL。变更环境后必须重启进程。

`python -m uvicorn knowledge_pilot.api.app:app` → app.py 六路由 → services.py → 原 Agent/工具与 Chroma。Chroma 模块创建 PersistentClient(DATA_DIR/vector_store)，原文存储使用 DATA_DIR/raw_documents。Docker 使用这一入口，没有替代演示服务。

- `KP_OLLAMA_BASE_URL`：本地默认 `http://localhost:11434`；Compose 默认 `http://host.docker.internal:11434`。只接受无路径/凭证/查询的 HTTP(S) origin，派生 /api/chat 与 /api/embed。
- `KP_CHAT_MODEL`：默认 gemma4:e2b。
- `KP_EMBED_MODEL`：默认 bge-m3。已有索引不能随意更换模型或维度。
- `KP_DATA_DIR`：不设置时仍为 CWD 相对 `data`，兼容原本本地与评测隔离方式；显式设置必须为绝对路径。不会在解析配置时创建目录。
- `KP_API_PORT`：Compose 的宿主机发布端口，默认 8000；容器内固定 8000。不是 Python 配置变量。
- `KP_HOST_DATA_DIR`：Compose 的宿主机绑定源，默认 ./data；容器里固定 KP_DATA_DIR=/app/data。

Python 不自动读取 .env。Compose 自动读取项目 .env 并将列出的变量注入容器；命令行进程环境覆盖 Compose 插值文件。未引入 dotenv/settings 框架。除上述配置引用外，不修改 Agent、RAG、实验 Dense/BM25/Hybrid/RRF 或冻结 Case。

## 构建与启动命令（供 Docker 可用环境执行，本轮未通过 Docker 实测）

PowerShell，先进入上述独立工作区：

```powershell
Copy-Item .env.example .env
New-Item -ItemType Directory -Path ./data -Force
docker compose config
docker compose build api
docker compose up -d api
docker compose ps
docker compose logs --tail 100 api
Invoke-RestMethod http://127.0.0.1:8000/health
```

默认使用独立工作区空数据目录，**不会自动装入原 main 的开发数据库**。若确实要使用已有数据，先停掉其他使用者并备份，再在本机 .env 设置 `KP_HOST_DATA_DIR=D:/AI_develop/KnowledgePilot/data`；该目录不会进入镜像或版本控制。本轮没有执行这个操作。共享内嵌库不做并行写入承诺。

Windows 主机既有 Chroma/source 元数据可能包含绝对 Windows 路径；绑定挂载不会迁移元数据。已有向量数据不会被初始化步骤主动清空，但跨平台检索、原文更新/删除及 metadata 可用性须在副本上验收后再使用旧库。历史相对 source 与新的绝对根组合也可能影响原文清理；Step 1 不声称已解决旧库迁移。优先验证一次性副本，禁止通过删除旧库解决问题。

Linux 先创建宿主机数据目录并使其对 UID 10001 可写，再启动；不要给整个项目目录宽泛写权限。Docker Desktop 与 Linux Engine 的宿主机寻址不同，Compose 提供 host-gateway 映射；Linux 宿主机 Ollama 若只监听 loopback，容器通常不能通过网关访问，需由用户配置允许的监听地址与防火墙。本轮未修改宿主机 Ollama 设置，不自动下载模型。

容器探测命令：

```powershell
docker compose exec api python -c "import os; print({k:os.environ[k] for k in ['KP_OLLAMA_BASE_URL','KP_CHAT_MODEL','KP_EMBED_MODEL','KP_DATA_DIR']})"
docker compose exec api python -c "import json,urllib.request,os; r=urllib.request.urlopen(os.environ['KP_OLLAMA_BASE_URL']+'/api/tags',timeout=5); print(r.status); print([x['name'] for x in json.load(r)['models']])"
docker inspect --format '{{json .Mounts}}' $(docker compose ps -q api)
docker compose restart api
docker compose down
```

验收数据持久化必须先通过 API 写入测试 TXT，记录 ID，重建容器后 GET /documents 核实 ID/Chunk 并核对宿主机 raw/vector_store 文件；目录存在或 inspect 显示挂载不等于持久化验收通过。不要删除宿主机数据目录。/health 200 不能替代模型推理验证。

本地现有环境的真实启动命令（需在独立测试数据目录运行）：

```powershell
$env:PYTHONPATH = Join-Path (Get-Location) 'src'
$env:KP_DATA_DIR = 'C:/absolute/path/to/isolated-data'
& D:/Anaconda/envs/knowledge-pilot/python.exe -B -m uvicorn knowledge_pilot.api.app:app --host 127.0.0.1 --port 8000
```

项目安装方式来自 pyproject 的 setuptools，`python -m pip install .`；Dockerfile 使用该方式，主机本轮没有安装依赖。requirements.txt 保持原样；未引入新的运行依赖。镜像基础标签尚非 digest 锁定，传递依赖也未锁定，构建可重复性仍有边界。

## 实际验证记录

以下命令均在独立工作区运行；原 main 仅做 Git 只读核对。

1. 环境：`D:/Anaconda/envs/knowledge-pilot/python.exe -B -c "import sys,importlib.metadata as m; print(sys.version); print({n:m.version(n) for n in ['pytest','fastapi','chromadb','requests','pydantic','uvicorn']})"`：Python 3.11.16，pytest 9.1.1，FastAPI 0.141.1，Chroma 1.5.9，requests 2.34.2，Pydantic 2.13.5，Uvicorn 0.52.4。
2. 修改前基线：设置 PYTHONPATH=<worktree>/src、KNOWLEDGE_PILOT_RUN_INTEGRATION=0，执行 `D:/Anaconda/envs/knowledge-pilot/python.exe -B -m pytest -p no:cacheprovider -q`：435 passed、1 skipped、2 warnings，7 subtests passed，17.97s。
3. TDD 红灯：同解释器执行 `-B -m pytest -p no:cacheprovider -q tests/test_configuration.py`，预期失败；pytest 含子测试统计显示 10 failed、1 passed，原因是新配置尚不存在、覆盖未生效。不是回归成绩。
4. 实现后全量：同基线命令，439 passed、1 skipped、2 warnings，14 subtests passed，6.11s。跳过原有显式真实知识库测试。警告来自现有 Starlette TestClient/httpx 和 anyio 弃用；未安装替代包。
5. 宿主机 Ollama：`python -B -c "import urllib.request; r=urllib.request.urlopen('http://localhost:11434/api/tags',timeout=5); print('host Ollama tags HTTP',r.status)"`（使用上述完整解释器路径）：200。
6. 真实本地 smoke：`D:/Anaconda/envs/knowledge-pilot/python.exe -B scripts/verify_step1_local.py`：退出 0；真实 Uvicorn /health 200；真实 Ollama Embedding 写入一个 Chunk；配置路径下 raw 文件和 Chroma sqlite 存在；重启进程后文档保留；更新/删除成功。整个过程仅使用新建临时库。没有测试 /chat 的真实生成，也没有声称测试 Docker。
7. Docker：实际执行 `docker --version`，PowerShell 返回 CommandNotFound。PATH、常见 C:/Program Files/Docker、D:/Program Files/Docker、用户 Programs/DockerDesktop 以及卸载注册信息未找到可用 CLI；仅发现 ProgramData/DockerDesktop 历史安装日志，不能证明当前已安装。未安装/启动 Docker。因缺 CLI，compose config/build/up、容器 health、容器到 Ollama 网络、Linux UID/权限、镜像依赖安装、容器重建挂载均未执行，状态 PENDING_MANUAL。
8. `git diff --check`：退出 0。Compose 使用现有 PyYAML 进行基本结构解析，不能替代 docker compose config 的模式/插值校验。

## 兼容性与下一步

默认地址、模型、相对 data 根、SYSTEM_PROMPT、API 路由、Agent 返回契约和默认 Dense 均保留。现有安全测试全部保持通过；冻结 data/evaluation 与实验代码无 diff。完整回归在未设置 KP_DATA_DIR 时运行；进行历史评测必须清除部署 KP_ 环境或使用其原先隔离启动约定，避免显式配置指向开发库。

Step 1 剩余验收首先是在有 Docker 的目标环境执行上述容器检查，不能用本地 smoke 代替。通过后再规划 Step 2：明确 liveness/readiness、上游超时和响应错误边界、请求日志；继续保留 Agent/检索语义，不顺带重构算法。旧库跨平台迁移单独设计并在副本上验证。

官方核对资料：

- [FastAPI 容器部署](https://fastapi.tiangolo.com/deployment/docker/)
- [Docker Compose 网络与 host-gateway](https://docs.docker.com/compose/how-tos/networking/)
- [Compose 服务、端口和挂载配置](https://docs.docker.com/reference/compose-file/services/)
