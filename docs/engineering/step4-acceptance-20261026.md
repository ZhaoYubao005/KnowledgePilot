# V1.4 Step 4 工程验收记录

日期：2026-10-26（Asia/Singapore）。分支：`v1.4-step4-api-integration`；基线：`d63547de128482fdca3a01676273be002fd10faf`。正式交付 SHA 以该分支提交记录为准；JSON 记录的是运行当时的基线、dirty 状态和源码指纹。

## 阶段结论

Step 4 本地 API 集成阶段 PASS。Docker 容器验证 BLOCKED；原生 Linux 为 DEFERRED_DEBT。本结论不是完整生产部署验收，也没有把模拟模型作为真实 Ollama。

- 最终全量回归：**479 passed、1 skipped、2 warnings、49 subtests，37.57 秒**，退出码 0；Step 3 基线为 472 passed、1 skipped。
- 真实独立 Uvicorn + 模拟模型 HTTP 上游 + 原 Service/Agent/Embedding/Chroma：**29 个请求、23 项检查通过**。
- 真实宿主机 Ollama：聊天 200、上传 201、删除 200；已有 `gemma4:e2b` 与 `bge-m3:latest`；实际向量 1024 维、实际新文档检索通过。没有下载模型，没有声称真实模型一定自主选择工具或答案语义正确。
- 模拟上游场景通过实际 calculator → knowledge_base → 最终回复的 Agent 循环，原执行器实际计算与检索；不是 Service Mock。
- 请求 ID、实际 JSON 日志关联、敏感内容不泄露、子进程退出、临时数据删除通过。

最终证据：[step4-evidence-20261026T114901Z-9dc9a6.json](step4-evidence-20261026T114901Z-9dc9a6.json)。另保留首次真实 Ollama 成功的 [初次证据](step4-evidence-20261026T114109Z-8f915b.json)，其 Docker 为 NOT_RUN，不能代替最终 Docker 检查结果。

## 实际环境和执行命令

Windows、Python 3.11.16；独立 Step 4 worktree；复用现有环境，不安装依赖。以下命令均在该 worktree 根执行。

```powershell
$env:TEMP = Join-Path (Get-Location) 'data/test-tmp'
$env:TMP = $env:TEMP
$env:PYTHONPATH = Join-Path (Get-Location) 'src'
$env:KNOWLEDGE_PILOT_RUN_INTEGRATION = '0'
& D:/Anaconda/envs/knowledge-pilot/python.exe -B -m pytest -p no:cacheprovider -q --basetemp ./data/pytest-step4-final-reviewed
git diff --check
```

最终全量结果如上；差异检查退出码 0。目标 API 集成测试曾单独执行并得到 6 passed；新进程树超时清理测试单独执行得到 1 passed（2.34 秒），之后均纳入最终 479 项回归。TDD 初始缺失 runner/helper 的失败属于开发过程，不记为验收通过。

最终独立验收命令，退出码 0：

```powershell
& D:/Anaconda/envs/knowledge-pilot/python.exe -B scripts/verify_step4_api.py `
  --test-root (Join-Path (Get-Location) 'data/step4-runs') `
  --real-ollama http://localhost:11434 `
  --docker C:/Users/lenovo/AppData/Local/Programs/DockerDesktop/resources/bin/docker.exe `
  --compose-plugin C:/Users/lenovo/AppData/Local/Programs/DockerDesktop/resources/cli-plugins/docker-compose.exe
```

测试根已预先创建。验收器在其中新建独占临时目录，证据放在目录之外。完整命令实际参数、环境、状态码、request ID、源码指纹和清理状态见 JSON。

## 集成覆盖和隔离

六个既有 API 均保持原样。上传、列表、更新、删除实际通过 Service 与持久化库；上传后检查实际记录、1024 维向量及查询相似度；更新后核对新正文、新索引与原文文件；删除后检查索引计数和原文清除。直接检查库前停止 API，再使用独立短生命 worker，避免同时打开嵌入式客户端。

400、404、422 使用实际输入与不存在文档；502、504 使用明确模拟上游；503 关闭模拟服务后触发实际连接失败；500 使用本轮临时目录内可恢复的文件系统阻断。所有响应与原 Step 3 契约一致，未修改生产错误映射。

清除继承的 KP_ 配置；仅打开带本轮 ownership marker 的新数据目录。真实 Ollama 验证另用一套临时目录。未清空、复制或上传用户 Chroma；不提交 SQLite、缓存、真实文档或进程日志。公开 JSON 只包含必要元数据，不包含完整用户输入、凭据或向量。

单元/TestClient 覆盖沿用旧测试；本轮新增跨模块验证使用真正网络进程。pytest 默认不运行真实 Ollama；真实 Ollama 的独立运行证据单列在 optional 中。

## Docker 与技术债

最终 Compose 配置检查退出码 0。Docker Engine 检查退出码 1：`dockerDesktopLinuxEngine` 命名管道不存在，无法连接 Engine。因此本轮未构建镜像、未启动容器、未进行容器持久化验证，明确 BLOCKED/NOT_RUN。没有反复排障、重装、恢复出厂设置或修改 daemon 全局配置。

原生 Linux 继续为 DEFERRED_DEBT；Windows 本地进程和 Compose 配置不能作为原生 Linux 或容器 UID 写入验收。

## 交付和审查

新增文件：三个 scripts（runner、模拟上游、进程管理）、两个 integration tests、覆盖计划、源码教学交接、本验收报告、两份 JSON 证据。生产 src 和既有测试未修改。

独立代码审查发现的新测试工具问题已修复：外层超时必须清理自有子进程树；真实 Embedding 探针等待时间需覆盖模型读取期限。修复后审查无新增可操作问题，最终全量回归通过。没有发现需要修复的 Step 3 产品 Bug。

`git diff --exit-code d63547d -- src data/evaluation docs/evaluation` 通过；main 保持 V1.3 SHA `268887c0bd7f1c987317fd07d0b4e221d38b84df`。既有工作区、历史证据和用户未跟踪材料保留。不合并 main、不创建正式 Tag。

源码路径、函数签名、真实调用链、教学重点与测试阅读顺序见 [step4-source-handoff.md](step4-source-handoff.md)。后续优先代码审查；Docker 恢复后补容器验收，原生 Linux 独立追踪，不扩大本阶段产品范围。
