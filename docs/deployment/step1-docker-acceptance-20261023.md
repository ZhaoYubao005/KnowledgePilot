# KnowledgePilot V1.4 Step 1 — Docker 部署验收报告

- 验收时间：2026-10-23 15:54 (UTC+8) / 2026-10-23T07:54:18Z
- 验收执行：Doubao 接管验证（独立工作区，未改动 V1.3 核心、未改动冻结评测数据）
- 验收脚本：`scripts/verify_step1_docker.py`（工程自带，未修改）
- 原始证据：`docs/deployment/docker-evidence-20261023T075418Z-8fba4c.json`
- 结论：**PASS（9/9 检查全部通过）**

---

## 1. 环境与网络

| 项 | 实测值 |
|---|---|
| 宿主 OS | Windows 11 x86_64 (10.0.26200) |
| Docker Desktop | Server/Client 29.9.2，Linux 容器 |
| Docker Hub `registry-1.docker.io` | **不可达**（DNS 被解析到 157.240.12.36，TCP 443 超时，属典型 DNS 污染/网络封锁） |
| 国内镜像源（实测可用） | `docker.m.daocloud.io`（DaoCloud）拉取 `python:3.11-slim` 成功 |
| PyPI `pypi.org` | **直连可用**（HTTP 200，构建期 pip 下载 100–400 KB/s，无需换源） |
| 宿主 Ollama | `http://localhost:11434` 在线；已加载 `gemma4:e2b`（chat）与 `bge-m3:latest`（embedding） |

### 网络处置（未修改 Docker daemon.json、未改 Dockerfile）
1. 通过 DaoCloud 镜像拉取 `docker.m.daocloud.io/library/python:3.11-slim`，并 `docker tag` 回标准名 `python:3.11-slim`，使既有 Dockerfile 的 `FROM python:3.11-slim` 命中本地缓存，避免构建期再访问 Docker Hub。
2. PyPI 直连可用，未做任何换源。
3. 未修改 Docker Desktop 的 registry-mirrors 全局配置（避免影响其他项目）。

## 2. 镜像构建

| 项 | 结果 |
|---|---|
| 命令 | `docker build -t knowledgepilot:v1.4-step1 .` |
| 基础镜像 | python:3.11-slim (sha256:b7a9e5f6…) |
| pip 安装 | 全部依赖（含 chromadb 1.5.9 / fastapi 0.141.1 / pydantic 2.13.5 / onnxruntime 1.31.0）安装成功 |
| 镜像 ID | sha256:e2385118a0313ad0b00622b1ccefaa84f012756e76c8cbe0cd07db936cb55790 |
| 镜像体积 | 844 MB |
| 运行用户 | app (uid 10001)，EXPOSE 8000 |

## 3. Compose 服务与功能验证（9 项）

| # | 检查项 | 证据 | 结果 |
|---|---|---|---|
| 1 | `docker compose config --quiet` | exit 0 | PASS |
| 2 | 镜像存在 | `knowledgepilot:v1.4-step1` ID 已确认 | PASS |
| 3 | FastAPI `GET /health` | HTTP 200，body `{"status":"ok"}` | PASS |
| 4 | 容器内配置注入 | `OLLAMA_URL=http://host.docker.internal:11434/api/chat`；`EMBEDDING_URL=…/api/embed`；`MODEL=gemma4:e2b`；`EMBED_MODEL=bge-m3`；`DATA_DIR=/app/data` | PASS |
| 5 | 容器→宿主 Ollama 真实连通 | `GET /api/tags` 200，返回 `["gemma4:e2b","bge-m3:latest"]` | PASS |
| 6 | 真实 embedding 调用 | `POST /api/embed` model=`bge-m3`，返回 **1024 维**向量（与 bge-m3 维度一致） | PASS |
| 7 | 文档上传落盘 | POST `/documents` 返回 201，`document_id=3f70c03b-…`，`chunk_count=1`；宿主 `data/docker-step1-…/raw_documents/3f70c03b-…/docker-probe.txt` 字节级一致 | PASS |
| 8 | 数据卷挂载 | bind mount，Source=宿主独立 `data/docker-step1-<run_id>/`，Destination=`/app/data`，RW=true | PASS |
| 9 | **删容器重建后持久化** | 旧容器 `b52c9e5d…` → `stop/rm` → 新容器 `237cf91a…`（ID 不同）；`GET /documents` 仍返回该文档；Chroma 集合内 `count=1`，文档原文 `"KnowledgePilot Docker persistence acceptance document."` 完整保留 | PASS |

## 4. 清理
- 验收脚本执行 `docker compose down` 已移除本次项目容器与网络，宿主无 `kp-step1-*` 残留容器（已复核 `docker ps -a`）。
- 新鲜测试数据目录 `data/docker-step1-20261023T075418Z-8fba4c/` 按设计保留作为证据。

## 5. 边界遵守
- 未修改 `src/` 下任何 V1.3 核心代码（git status 中的 M 文件为 Step 1 既有改动，本次未触碰）。
- 未改动冻结评测数据（`data/evaluation/`）。
- 未改动 `Dockerfile` / `compose.yaml` / `requirements.txt` / `.env.example`，全部使用 Step 1 既有实现。
- 未向其他智能体可能修改的目录写入任何东西；本报告与证据 JSON 写入 `docs/deployment/`（Step 1 专属目录）。

## 6. 遗留风险与后续建议
1. **Docker Hub 直连仍不可用**：后续若换新 base 镜像（如升级 Python 版本），需重复「DaoCloud 拉取 → retag」流程；建议长期方案是在 Docker Desktop → Settings → Docker Engine 中加入 `registry-mirrors: ["https://docker.m.daocloud.io"]`，但这属于全局改动，需你授权后再做。
2. **Ollama 跑在宿主而非容器内**：Step 1 用 `host.docker.internal:11434` 依赖主机 Ollama；后续 Step（如 V1.5 全面容器化）需把 Ollama 也 Compose 化或预置模型卷。
3. **镜像体积 844 MB**：主要来自 chromadb/onnxruntime，Step 1 可接受；后续可考虑多阶段构建瘦身。
4. 本环境 pip 直连 pypi.org 可用；若换网络环境失败，构建期可临时加 `--build-arg PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple`（需 Dockerfile 显式 ARG，属后续可选优化，本次未做）。

**信心指数：10/10** —— 全部结论来自本次实测命令输出与自动生成的 evidence JSON，无推测项。
