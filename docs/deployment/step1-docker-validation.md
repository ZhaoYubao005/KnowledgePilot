# Step 1 Docker 真实部署续验

日期：2026-10-23（Asia/Singapore）。结论：**尚不满足封板条件**。Docker 环境已实际准备成功；构建受当前网络阻断，容器功能不得标为通过。

## 实际环境准备

- Windows 11 家庭版中文版，10.0.26200，WSL 报告 Windows 10.0.26200.9457。
- WSL 2.6.1.0、内核 6.6.87.2-1，默认版本 2。初查无分发；vmcompute 和 WSLService 已运行，HypervisorPresent=True。处理器虚拟化属性在 hypervisor 运行时返回 False，不能据此单独断言 BIOS 未开启；后续 Docker Linux Engine 实际运行证明后端可用。
- 受限沙箱内 WMI/WSL 返回 Access Denied，沙箱外授权检查成功；这个拒绝不是主机 WSL 安装失败。
- 初始无 Docker CLI/现行安装记录。历史 2025 年安装日志只表明旧更新卸载过旧版本，不作为本轮环境证据。
- 从 `https://desktop.docker.com/win/main/amd64/Docker%20Desktop%20Installer.exe` 下载至 `%TEMP%/KnowledgePilot-Docker-Desktop-Installer.exe`，641,758,128 字节；Get-AuthenticodeSignature 返回 Valid，签名者 Docker Inc。
- 实际执行安装器 `install --user --quiet --backend=wsl-2`，Start-Process 使用 Hidden；安装器退出 0，install-log.txt 记录 Installation succeeded。未手动接受新的许可标志，未改写已有 Desktop 设置，未启用额外 Windows 功能，未重启。
- 当前用户安装位置 `%LOCALAPPDATA%/Programs/DockerDesktop`；启动 Docker Desktop.exe 后，docker version 实际返回服务端 Linux/amd64。Docker Desktop 4.96.3 (244472)，Docker Engine/CLI 29.9.2，Compose 5.6.1，containerd 2.4.2。
- `wsl --list --verbose` 实际显示 docker-desktop Running、Version 2；后端日志记录 linux/wsl starting → running。不需要另装 Ubuntu。
- Windows Server 服务 LanmanServer 为 Running/Automatic；C 盘安装时可用空间约 172 GB。

## 实际执行命令与结果

使用显式路径避免新终端 PATH 尚未刷新。令 `$dockerRoot = Join-Path $env:LOCALAPPDATA 'Programs/DockerDesktop'`，`$env:PATH=(Join-Path $dockerRoot 'resources/bin')+';'+$env:PATH`。工作目录始终是现有独立 worktree。

1. `wsl --version`、`wsl --status`、`wsl --list --verbose`：结果如上。设置 `WSL_UTF8=1` 解决默认 UTF-16 输出乱码，不是系统功能变更。
2. `& (Join-Path $dockerRoot 'resources/bin/docker.exe') version`：客户端和 Linux 服务端均正常返回。
3. `& (Join-Path $dockerRoot 'resources/cli-plugins/docker-compose.exe') version`：v5.6.1。
4. `& (Join-Path $dockerRoot 'resources/cli-plugins/docker-compose.exe') -p kp-v14-step1-acceptance config --quiet`：退出 0。它是真实 Compose 检查，替代上一轮仅做 YAML 解析的证据。
5. 同一 Compose 可执行文件执行 `-p kp-v14-step1-acceptance --progress plain build api`，共两次，均退出 1：第一次获取 `registry-1.docker.io/v2/library/python/manifests/3.11-slim` 时 TLS handshake timeout；第二次取 `auth.docker.io/token` 时连接 `198.18.0.188:443` 超时。失败在基础镜像元数据阶段，未进入 COPY/项目安装；不能把它判为项目依赖安装成功或 Dockerfile 构建通过。
6. `docker pull python:3.11-slim`：首次当前终端缺少 credential helper PATH；补充上述 bin 路径后重试，失败原因为匿名认证请求 TLS handshake timeout。未读取或输出凭据/token，未改写 credential 配置。
7. 宿主机 urllib 对官方 registry、auth.docker.io 和 pypi.org 的有限超时探测：registry 曾一次返回预期未认证 401，但其余及最终复测均出现 TLS 握手超时，表明网络路径不稳定。Google 官方缓存 mirror.gcr.io、AWS public.ecr.aws 的公共根地址探测也超时；没有切换项目镜像源或使用第三方未知镜像。
8. 系统现有 ProxyEnable=0，保留的代理地址为 127.0.0.1:7892；有限超时 TCP 探测未建立连接。Docker info 未报告 HTTP/HTTPS proxy。没有启用、替换或关闭用户代理。
9. `Resolve-DnsName auth.docker.io -Type A` → `198.18.0.188`；DNS 列表显示 iKuuuVPN 使用 `198.18.0.2`。执行 `Clear-DnsClientCache` 后仍解析为同一 Fake-IP，向 1.1.1.1 查询也返回相同地址，说明当前网络路径对 DNS 查询有影响。未改全局 DNS/hosts、路由或 VPN 节点；不能将此描述为已证明 Docker 自身故障。
10. 运行 `D:/Anaconda/envs/knowledge-pilot/python.exe -B scripts/verify_step1_docker.py --docker <dockerRoot>/resources/bin/docker.exe --compose-plugin <dockerRoot>/resources/cli-plugins/docker-compose.exe`：退出 1。脚本再次通过真实 Compose 检查，随后的 image inspect 返回 No such image，故未启动应用容器。完整 argv、退出码和输出见 [JSON 证据](docker-evidence-20261023T070821Z-5cf687.json)。专用项目执行 down 退出 0；没有遗留本次应用容器/网络。

一次诊断命令的 Python -c 引号转义出错，返回 SyntaxError；已用 PowerShell here-string 正确重跑。该错误没有修改源码，不作为网络探测结果。

## 测试数据与容器验证边界

新增 `scripts/verify_step1_docker.py`，仅是显式运行的验收器，不更改业务行为。它预定在镜像存在后验证：

- 专用 Compose 项目与随机本机端口；独立新建 data/docker-step1-<run_id>。
- 真实 /health 200、容器内配置值、宿主机 Ollama /api/tags 与真实 /api/embed；只记录向量维度，不保存向量内容。
- 通过 API 上传最小 TXT，并检查绑定目录 raw 文件和 Chroma sqlite。
- 停止并删除旧容器，再 up 创建新容器，确认容器 ID 改变、文档 ID/Chunk/原文及 Chroma 记录内容保留。
- finally 仅清理自身 Compose 项目，保留新测试目录和 JSON 证据。

本次创建的测试目录：`data/docker-step1-20261023T070821Z-5cf687`，镜像检查失败前未写入原文或 Chroma；不是持久化通过证据。运行状态为 failed，只有 compose_config 检查通过；不能引用脚本中尚未到达的断言作为实际结果。

容器启动、容器 /health、容器到 Ollama、非 root 目录写权限、删除重建后的持久化：全部 **BLOCKED_NOT_RUN**。上一轮本地 Uvicorn/真实 Ollama/临时 Chroma 成功结果仍只属于本地证据，不提升为容器证据。

## 新鲜回归与保护边界

在独立 worktree 设置 PYTHONPATH=<worktree>/src、KNOWLEDGE_PILOT_RUN_INTEGRATION=0，清除 KP_ 部署变量后执行：

```powershell
& D:/Anaconda/envs/knowledge-pilot/python.exe -B -m pytest -p no:cacheprovider -q
git diff --check
```

结果：439 passed、1 skipped、2 warnings、14 subtests passed，6.34s。原有真实知识库测试保持显式跳过。警告仍为 Starlette/httpx 和 anyio 的现有弃用提示，无依赖升级。

本轮只新增验收脚本与更新文档/JSON 证据，未再修改生产源码、Dockerfile 或 Compose。main 的 tracked diff 和 staged diff 均为空，HEAD 仍为 268887c；12 个未跟踪面试资料文件仍在。独立 worktree 的 data/evaluation、evaluation 实现、Agent Loop 和 RAG 均无 diff。未打开原 Chroma，没有提交、推送或 Tag。

## 剩余阻断、最少人工操作与封板结论

不需要用户重装 Docker、运行项目命令或重启系统。需要先恢复当前网络/VPN 到官方 Docker Hub（registry-1.docker.io、auth.docker.io 及其镜像层下载域名）与 PyPI 的有效 HTTPS 路径。若网络/VPN 客户端要求交互登录、选择可用线路或账号授权，该最小交互需用户完成；本轮未访问账号或凭据，也未替用户改变 VPN 节点。是否确需交互尚未验证，不虚构账号失效。

网络恢复后由工程代理继续执行：Compose build → 上述验收器 → 必要失败修复/回归 → 更新报告。当前安装/引擎/Compose 配置已有真实证据，但核心容器部署与持久化没有完成，**Step 1 不满足封板条件**。不创建 v1.4.0 Tag，不推进 Step 2。

官方资料：[Windows 当前用户安装与 WSL 要求](https://docs.docker.com/desktop/setup/install/windows-install/)、[Google 官方 Docker Hub 缓存说明](https://docs.cloud.google.com/artifact-registry/docs/pull-cached-dockerhub-images)。官方说明用于选择安装与诊断方式，不替代本机运行证据。
