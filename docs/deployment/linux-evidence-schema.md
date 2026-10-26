# Linux Runtime 验收证据 v1

`scripts/linux/verify_persistence.py` 产生 UTF-8 JSON，schema 为 `kp_linux_runtime_v1`。历史报告不可覆盖；所有路径均指向本轮全新测试数据，不包含凭据、用户文档或向量正文。

字段说明：

- `run_id`、`started_at_utc`、`finished_at_utc`：UTC 时间与随机后缀。
- `host_platform`、`engine`、`docker_version`、`compose_version`：CLI 宿主和 daemon 的实际标识。Engine 未连接成功时相关字段可缺失，不补写猜测值。
- `git_commit`、`git_status`、`source_sha256`：检出身份与部署文件/脚本 SHA-256，dirty 状态保留，防止把未提交脚本误认作基线镜像内容。该源码指纹不单独证明镜像包含相同字节；镜像身份另记。
- `project`、`data_root`、`data_stat`、`api_base`：专用项目、数据根、owner/GID/mode 与本机环回端口。
- `models`：明确选择的聊天模型、Embedding 模型及预期维度；不能用安装模型列表代替实际选用配置。
- `commands`：实际 argv、exit_code、stdout/stderr；启动失败或超时的 exit_code 为 null 并记录错误类型。
- `checks`：仅添加已经实际完成的项目，缺失项代表未完成。`container_uid_probe` 必须是 UID 10001 的真实写入/回读/删除，`service_identity` 再确认实际 API 用户。
- `image` 检查：镜像 ID、用户和真实 FastAPI 启动命令；不 dump 整个 Engine/环境变量或敏感配置。
- `recreate_persistence`：不同的新旧容器 ID、文档 ID/Chunk、Chroma count/固定 synthetic 正文与原文 SHA-256。
- `cleanup`：本轮随机项目的资源清理结果；任何清理失败都会把 status 置为 failed，宿主数据始终保留。
- `status`：本轮所选环境的操作检查 passed/failed。它不能单独决定 Step 2 封板。
- `native_linux_environment`：本机 Linux + Engine 标识不含 Desktop/WSL 的环境筛选结果；不代替平台证据审查。
- `native_linux_acceptance`：原生 Linux 且全部操作通过为 PASS，原生 Linux 操作失败为 FAIL；没有可用的原生 Linux 环境为 BLOCKED_NOT_RUN。

进程退出 0 只表示当前环境的操作检查通过；正式 Step 2 PASS 还需要原生 Linux 验收 PASS、离线回归无新增失败及保护文件不变。Windows Docker Desktop 上跑过的成功步骤必须在文档中保留平台边界。

默认验收检查覆盖新库持久化，不覆盖生产备份恢复、旧 Windows 库迁移、多进程并发写入、真实 /chat 生成、故障恢复 SLA 或 SELinux。上述内容不得从本证据推导为通过。
