# V1.4 Step 2 工程交付与验收记录

日期：2026-10-24，Asia/Singapore。

**阶段结论：实现与离线回归完成；真实运行验收阻断，Step 2 尚未 PASS，不满足封板条件。** 宿主预检、shell 替身测试和 Compose 配置通过均不能替代容器 UID 10001 或原生 Linux 实测。

## Git 与协作边界

- PR #1 已通过连接 GitHub 只读核实：open、merged=false，head 为 Step 1 `d7463c9701a1e1869caf4ebfcb2d8e28fa889b10`，base main 为 `268887c`。
- 新分支 `v1.4-step2-linux-runtime`，独立 worktree：`C:\Users\lenovo\.codex\.chatgpt-projects\g-p-6a9c0574f0648191afc307eb07a1456b\KnowledgePilot-v14-step2`。从 Step 1 提交开始，未合并 main。
- Step 2 目前未提交、未推送；没有创建 PR 或 Tag。Step 1 功能分支和验收报告不改写，用户的原 main 与 12 个未跟踪面试资料文件保留。
- `git diff --exit-code d7463c9 -- src data/evaluation docs/evaluation` 退出 0，证明 Step 2 没有修改业务源码、冻结输入或实验报告。
- Step 1 验收报告 SHA-256：`7D4D728E344D4F54712CFA5BC9918D682F5AAF2E777D275F645ADFFAA95A0FB3`；通过 JSON：`A88E996FDBD699BB706BBC8C485C90CD1955D8D3D2814937722A6EF81303640C`，与先前一致。

## 修改文件与计划对应

- 新增 `scripts/linux/preflight.py`：绝对/已存在目录校验、真实宿主 create/write/read/delete 探针、URL origin/端口/凭证校验，JSON 与非零退出；不导入业务或 Chroma。
- 新增 `scripts/linux/up.sh`：定位自身项目、显式 export 输入、Compose 检查、同镜像同挂载 UID 10001 探针、通过后 no-build 启动 API。
- 新增 `scripts/linux/down.sh`：停止固定部署项目，保留宿主数据；不使用 `-v` 或递归删除。
- 新增 `scripts/linux/verify_persistence.py`：随机项目/端口、新数据子目录、环境/镜像/命令身份、UID 探针、真实 HTTP/Ollama/Embedding、容器删除重建持久化、finally 有界项目清理及 exclusive JSON 证据。
- 新增 `tests/deployment/test_linux_preflight.py`：16 个离线测试，覆盖失败权限、清理失败、URL、shell 实际命令顺序、UID 探针失败阻止启动、独占数据目录、Desktop/native 状态区分和引擎缺失证据。
- 新增 `docs/deployment/linux-runtime.md`：Linux 权限、宿主 Ollama、构建/启停、验收与备份/回滚边界。
- 新增 `docs/deployment/linux-evidence-schema.md`：证据字段、缺失值和状态规则。
- 新增本报告与两份 `linux-evidence-20261024T*.json`：实际结果，保留失败事实；最终源码对应的是 `linux-evidence-20261024T091639Z-0ccd08.json`。
- 修改 `.env.example`：Linux 明确 export/绝对路径及宿主 loopback 限制说明。
- 修改 `.gitattributes`：仅对 `scripts/linux/*.sh` 固定 LF，保证 Windows checkout 后 Linux 可执行；冻结文件规则不变。

Compose 现有配置已经满足 bind `/app/data`、`create_host_path=false`、环回发布端口及 host-gateway，无须改写。`.gitignore` 已覆盖本轮 `data/` 临时文件，无须增加规则。没有生产业务逻辑修改。

计划任务 1–4 的实现和离线验证已完成；任务 2 的真实 UID 写入、任务 4 的 Linux 主机 Compose 与任务 5 的完整真实 Linux 验收均等待运行环境恢复。

## 实际测试命令与结果

### 离线测试

解释器沿用已有 `D:/Anaconda/envs/knowledge-pilot/python.exe`，未安装依赖。Windows Git 实际位于 `D:/AI/Git/Git`，shell 测试通过实际 POSIX shell 执行脚本，Docker 命令是临时替身，不连接 daemon。

TDD 红灯：新测试先运行，13 failed（预检/脚本/验收器尚不存在）。随后针对清理权限、引擎缺失证据又先出现失败，再修正。初始全量尝试受系统 TEMP 权限影响并中断，未当作基线通过；沙箱内 MSYS 的命名对象权限错误也未当作产品失败或 PASS。

最终完整命令（工作目录为 Step 2 worktree，沙箱外运行以满足 MSYS 命名对象权限）：

```powershell
$env:TEMP = Join-Path (Get-Location) 'data/test-tmp'
$env:TMP = $env:TEMP
$env:PYTHONPATH = Join-Path (Get-Location) 'src'
$env:KNOWLEDGE_PILOT_RUN_INTEGRATION = '0'
& D:/Anaconda/envs/knowledge-pilot/python.exe -B -m pytest -p no:cacheprovider -q --basetemp ./data/pytest-step2-reviewed-20261024
git diff --check
& D:/AI/Git/Git/usr/bin/sh.exe -n scripts/linux/up.sh scripts/linux/down.sh
```

实际最终结果：**455 passed、1 skipped、2 warnings、29 subtests passed，9.16s**。唯一 skipped 仍为既有显式真实知识库测试，未新增 skip/xfail。两条现有警告为 Starlette/httpx 与 anyio 弃用；不通过升级依赖处理。`git diff --check` 与 shell 语法检查退出 0。

按 requesting-code-review 技能进行的独立只读复核未发现 Critical/Important 问题；三个 Minor 意见已处理：宿主探针失败不可记录 PASS、超时保留部分输出、证据明确记录选用模型。为第一项先新增失败测试再修正，并运行上述最终回归。

`--basetemp` 必须每次选新目录，不重用已有测试或证据目录，因为 pytest 会管理该路径内容。

### 实际 Compose 检查与构建尝试

使用现有 `C:/Users/lenovo/AppData/Local/Programs/DockerDesktop/resources/cli-plugins/docker-compose.exe`：

```text
--env-file NUL -f compose.yaml -p kp-step2-config-check config --quiet
--env-file NUL -f compose.yaml -p kp-step2-config-check config --format json
-p kp-step2-build-check --progress plain build api
```

config 命令退出 0，解析实际 JSON 确认 `KP_DATA_DIR=/app/data`、bind target、禁止自动创建宿主路径、端口只发布到 127.0.0.1。这个结果来自 Windows 客户端，原生 Linux 客户端未执行。

build 实际退出 1：无法连接 `//./pipe/dockerDesktopLinuxEngine`，管道不存在。未开始构建，不能声称镜像构建成功或新依赖已安装。

### 实际验收器执行

```powershell
& D:/Anaconda/envs/knowledge-pilot/python.exe -B scripts/linux/verify_persistence.py `
  --test-root (Join-Path (Get-Location) 'data/acceptance') `
  --ollama-url http://host.docker.internal:11434 `
  --docker C:/Users/lenovo/AppData/Local/Programs/DockerDesktop/resources/bin/docker.exe `
  --compose-plugin C:/Users/lenovo/AppData/Local/Programs/DockerDesktop/resources/cli-plugins/docker-compose.exe
```

实际两次均退出 1，在 Docker info 阶段因引擎不可用失败。初次证据：[linux-evidence-20261024T090706Z-eb0dbb.json](linux-evidence-20261024T090706Z-eb0dbb.json)。最终源码指纹对应：[linux-evidence-20261024T091639Z-0ccd08.json](linux-evidence-20261024T091639Z-0ccd08.json)。两份均为 `checks={}`、`status=failed`、`native_linux_acceptance=BLOCKED_NOT_RUN`；未尝试容器资源，不执行 down，数据子目录没有原文或数据库。

两份证据分别保留各自运行时源码 SHA-256；不能把任何失败记录误认为脚本在真实环境下通过。最终脚本的离线回归另有上述结果。

## Docker 运行时阻断

只读检查显示唯一 WSL 分发为 docker-desktop、Stopped、Version 2；没有本任务可用的独立 Linux 主机。

启动既有 Desktop 后，日志 `AppData/Local/Docker/log/host/com.docker.backend.exe.log` 记录：

```text
starting services: initializing Secrets Engine:
listening on .../docker-secrets-engine/engine.sock:
rename .../engine.sock .../engine.sock.stale:
The file cannot be accessed by the system.
```

对应 socket 具有 ReparsePoint 属性。仅针对这个无运行进程的失效端点尝试改名、删除及清除重解析点，Windows 均返回 Error 1920；尝试保留父目录备份也被拒绝访问，所有恢复操作均未成功，没有删除任何内容。未读取 secret 内容，不修改 daemon、DNS、VPN、镜像、用户数据库或 Docker 全局配置。

Docker 项目已有相同故障记录：[docker/for-win #15064](https://github.com/docker/for-win/issues/15064)。这里只用来解释日志模式，不能保证某种恢复步骤必然有效。不要使用 factory reset 或删除 Docker/Chroma 数据规避。

最少外部动作是恢复宿主 Docker Desktop 的启动能力；可能需要系统所有者的管理员权限或注销/重启后处理失效 socket。工程代理没有自动重启系统，也不保证重启必然解决。即便 Desktop 恢复，正式 Step 2 PASS 仍需在可用的原生 Linux 主机上运行相同验收。

## 阶段验收状态

- 实现与离线回归：PASS。
- Windows Compose 配置/挂载契约：PASS。
- 容器 UID 10001 实际写入：BLOCKED_NOT_RUN。
- 容器 /health、宿主 Ollama、真实 Embedding、删容器重建持久化：BLOCKED_NOT_RUN。
- 原生 Linux Compose/Engine/权限/持久化：BLOCKED_NOT_RUN。
- 旧库迁移、生产备份恢复、SELinux、多进程并发：不在已验证范围。
- **Step 2 总状态：BLOCKED，尚未封板。** 不自动合并 main，不推送 Step 2，不创建 v1.4.0 Tag。
