# V1.4 Step 2 Linux Runtime & Data Persistence

范围：单机、单 API 容器、内嵌 Chroma、外部宿主机 Ollama。不改变检索策略与 Agent 逻辑。Step 1 的真实部署证据继续有效；Step 2 的原生 Linux 验收需单独执行。

## 前置条件与平台边界

- Python >=3.11、POSIX sh、Git、Docker Engine（Linux 容器）和 Compose 插件已安装。脚本不安装依赖或模型。
- 本轮离线实测 Python 3.11.16 / pytest 9.1.1；Compose 客户端 5.6.1。当前宿主为 Windows，Docker Desktop Linux 后端不等同于原生 Linux Docker Engine 验收。
- Docker context 必须指向本机引擎：数据目录预检在 CLI 所在宿主执行，不能将其结果用于远程 daemon。原生验收时在目标 Linux 主机本地执行脚本；不得挂载原始 Windows Chroma 或冻结评测库。
- Docker Hub 可达性与镜像获取方式独立记录；不自动修改 daemon、DNS、代理或镜像源。若沿用已验收的缓存镜像，要记录其 ID，不宣称重新构建成功。

## 数据目录与权限

Compose 保留 Step 1 契约：宿主目录绑定 `/app/data`，内部 `KP_DATA_DIR=/app/data`，且 `create_host_path=false`。镜像中的用户 UID 为 10001。

在目标 Linux 创建专用目录（管理员执行一次；仅限新建目录）：

```sh
sudo install -d -m 2770 -o "$(id -u)" -g 10001 /srv/knowledgepilot/data
```

目录 owner 供当前部署用户操作，setgid 的 GID 10001 供容器写入。不要使用 `chmod -R 777` 或修改整台机器的数据目录权限。已有目录先检查内容与 owner，不自动递归 chown。SELinux 主机还需显式评审标签策略；本轮未验证 SELinux。

预检只在指定目录创建、写入、回读、删除唯一临时探针，不导入应用、不打开 Chroma、不创建数据目录。它只能证明当前宿主用户权限。

```sh
export KP_HOST_DATA_DIR=/srv/knowledgepilot/data
export KP_OLLAMA_BASE_URL=http://host.docker.internal:11434
export KP_API_PORT=8000
python3 scripts/linux/preflight.py --data-dir "$KP_HOST_DATA_DIR" --ollama-url "$KP_OLLAMA_BASE_URL"
```

URL 预检校验协议、origin、端口及凭证排除，不发推理请求。容器真实通信由持久化验收器检查。显式部署数据目录保持绝对路径；本地开发未设置 KP_DATA_DIR 时的历史相对路径默认不变。

Linux 的 `host-gateway` 只提供寻址，不会让仅监听 `127.0.0.1` 的 Ollama 自动可达。Ollama 仍在宿主运行；根据主机实际网络配置受控监听地址与防火墙，限制到容器网络，不直接开放公网。脚本不改 Ollama 设置，不拉取模型。

## 构建、启动与停止

先在仓库根目录显式构建镜像：

```sh
docker compose --env-file /dev/null -f compose.yaml -p knowledgepilot-v14 build api
sh scripts/linux/up.sh
docker compose --env-file /dev/null -f compose.yaml -p knowledgepilot-v14 ps
curl --fail http://127.0.0.1:8000/health
sh scripts/linux/down.sh
```

up/down 根据自身位置定位 Compose，允许从其他 CWD 启动；上例 curl 端口随 KP_API_PORT 调整。脚本要求明确 export 两个配置，不将 `.env` 当 shell 程序 source，并使用 `/dev/null` 禁用隐式 env-file 输入。

up 的顺序：宿主路径/URL预检 → Compose config → 同一镜像、同一挂载下 `run --user 10001:10001` 实际创建/回读/删除探针 → `up -d --no-build api`。UID 探针失败时不会启动 API；不得用宿主预检替代它。脚本不自动构建或修改目录权限。临时 run 容器通过 `--rm` 清理；若 UID 探针失败可能保留专用项目网络，不自动 down 已有应用。

down 只对固定 `knowledgepilot-v14` 项目运行 `down`，不传 `-v`，不删除宿主数据。标准输出、错误输出和退出码供操作端记录；没有后台守护器或自动重启循环。shell 文件由 `.gitattributes` 固定 LF，通过 `sh` 执行，不依赖 Windows checkout 的 executable 位。

## 可重复持久化验收

为每轮测试单独准备 setgid 的空验收根：

```sh
sudo install -d -m 2770 -o "$(id -u)" -g 10001 /srv/knowledgepilot/acceptance
python3 scripts/linux/verify_persistence.py \
  --test-root /srv/knowledgepilot/acceptance \
  --ollama-url http://host.docker.internal:11434 \
  --require-native-linux
```

脚本在验收根下独占新建随机子目录，POSIX 权限 0770；通过父目录 setgid 继承 GID 10001，不对既有目录执行 chmod/chown。只有 synthetic TXT 写入该目录，重跑使用另一个子目录，绝不清空之前的测试数据。

验证项：平台/Engine 身份、宿主权限、真实 Compose、镜像、UID 10001 写入、实际服务 UID、HTTP /health、容器到 Ollama tags、真实 Embedding、上传、原文与 SQLite、bind mount，以及停止/删除/重建不同容器 ID 后的文档与集合内容一致。模型默认 bge-m3、1024 维，可显式参数化，但不得对已有索引切换模型。

不传 `--require-native-linux` 可做 Windows Docker Desktop 诊断；即使这些检查全部通过，`native_linux_acceptance` 仍为 BLOCKED_NOT_RUN。传该参数时，检测到 Desktop/WSL 会拒绝验收。平台检测是环境标识检查，不是对远程主机可信身份的认证；同时保留 host/Engine/Kernel 原始标识供审查。

证据默认保存到 `docs/deployment/linux-evidence-<run_id>.json`；可通过 `--evidence-root` 指定已有绝对目录。使用 exclusive create，避免覆盖已有证据。异常和超时也记录退出码与状态；只在尝试本轮资源后对随机 `kp-step2-*` 项目 down，保留新测试目录。

## 数据恢复与回滚边界

原文与向量库必须作为一致的数据集处理。备份前停止所有写入者并确认容器停止，再对整个专用 data 目录做离线备份。此步骤是操作要求，本轮没有执行完整备份/恢复验收，不得声称已验证。

恢复时使用新的空目录和同版本镜像/Embedding 模型，在副本上检查 metadata source、原文、文档 ID 与向量库一致后再切换挂载。既有 Windows 绝对路径与历史相对 metadata 不会因挂载自动迁移；Step 2 不修改旧库。不以删除旧库解决错误。镜像版本回滚不等于数据库格式可以回滚。

## 故障定位

- 预检退出 1：按 JSON errors 检查绝对路径、目录存在性、宿主写入/删除权限和 URL。
- UID 探针失败：检查目录 owner/GID/mode、父目录可遍历性及 SELinux；不要提高容器为 root 规避。
- /health 成功但 Ollama 失败：分别核对 host-gateway、宿主监听、防火墙、模型名称。/health 只代表轻量路由可用。
- Docker API 管道不存在：引擎尚未启动，Compose config 可通过但构建和 UID 探针不可验证。
- Desktop AF_UNIX `engine.sock` 错误：属于宿主运行时故障，不改项目业务逻辑、不清空 Docker 数据或 Chroma。保存日志后由系统所有者恢复 Desktop。

官方参考：[Compose run 用户覆盖](https://docs.docker.com/reference/cli/docker/compose/run/)、[Compose 挂载与服务配置](https://docs.docker.com/reference/compose-file/services/)。
