# V1.4 候选部署入口

这是发布准备文档，不是当前容器部署通过声明。原 Step 1 历史证据、Step 2 历史 BLOCKED 报告保留不改写；最新状态见 [Step 5 集成报告](../engineering/step5-integration-report.md)。

## 配置和数据

Python >=3.11，依赖由 `pyproject.toml` 固定直接版本；Dockerfile 安装真实包并以 UID 10001 运行。当前不新增依赖或服务。Python 只读进程环境；Compose 自动读取 `.env`，Linux 脚本明确忽略 `.env`，要求导出配置。不要把含 shell 代码的 `.env` source 到 shell。

- `KP_OLLAMA_BASE_URL`：无凭据的 HTTP(S) origin；本地默认 localhost:11434，Compose 默认 host.docker.internal:11434。
- `KP_CHAT_MODEL` / `KP_EMBED_MODEL`：默认 gemma4:e2b / bge-m3；不对既有索引随意切换模型。
- `KP_DATA_DIR`：Python 显式配置必须为绝对路径；容器固定 /app/data。
- `KP_HOST_DATA_DIR`：Compose 宿主整个数据根；目录必须已存在，不自动创建挂载源。测试使用新目录。
- `KP_API_PORT`：宿主映射端口，默认 8000；容器监听 8000，宿主默认仅 127.0.0.1。
- `KP_LOG_LEVEL`：默认 INFO；模型连接/读取超时默认 5/120 秒。

原文和 Chroma 必须一起备份。备份前停止全部写入者；恢复到新目录并用相同版本、模型检查一致性。尚未完成完整恢复验收，Windows metadata source 路径不会因跨平台挂载自动迁移。禁止用清库处理迁移问题。

## Compose 操作（引擎可用后执行）

在候选 worktree 根创建本轮专用数据目录，再从 `.env.example` 复制本地 `.env` 并按实际路径设置 KP_HOST_DATA_DIR。不要提交 `.env`。新 Linux 目录按 linux-runtime.md 授予 UID/GID 10001 必要访问权限。

```sh
docker compose config --quiet
docker compose build api
docker compose up -d --no-build api
curl --fail http://127.0.0.1:8000/health
docker compose down
```

这些是复现操作说明，不表示本轮已经执行 build/up。Compose 目前沿用镜像名 `knowledgepilot:v1.4-step1`，它是开发镜像标签，不是不可变发布身份；正式发布前需重新构建当前候选并记录 image ID/digest，不能直接用旧同名镜像冒充。多份 checkout 使用同标签时须评审镜像覆盖影响，不改 daemon 镜像源。

Linux 使用 `scripts/linux/up.sh` / `down.sh`，明确导出绝对 KP_HOST_DATA_DIR 与可达宿主 Ollama origin。up.sh 先做宿主探针和 Compose 检查，再在同挂载中以 UID 10001 实际写入，最后启动；宿主探针通过不能代替容器探针。原生 Linux 验收脚本为 `scripts/linux/verify_persistence.py --require-native-linux`，使用独立验收根。详见 [Linux 说明](linux-runtime.md)。

## 运行边界

Ollama 保持在宿主机，不新增 Ollama/Chroma 服务。Linux host-gateway 无法访问仅监听 loopback 的服务，需部署者评审监听和防火墙；不公开暴露 Ollama。单 API worker + 内嵌 Chroma；没有认证、自动备份、滚动升级或已验证的多实例共享写入支持。

轻量 `/health` 不访问 Ollama，不代表 readiness。应用日志为安全 JSON，请求 ID 在响应头中；未知错误返回安全 500，模型错误按 502/503/504 分类。文档 PUT 非原子，模型/写入失败可丢旧索引；需要原子更新保证的使用场景当前为 No-Go。不要用用户数据故障注入。
