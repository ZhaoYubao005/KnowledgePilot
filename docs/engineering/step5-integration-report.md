# V1.4 Step 5 工程审查与最终集成报告

日期：2026-10-27，Asia/Singapore。状态：工程集成完成，等待人工审查；未正式封版。

## 1. Git 身份与安全隔离

独立目录：`C:\Users\lenovo\.codex\.chatgpt-projects\g-p-6a9c0574f0648191afc307eb07a1456b\KnowledgePilot-v14-step5`。
分支：`v1.4-step5-release-readiness`。从经远程核实的 Step 4 建立，没有从旧 main 开发。

核实的提交链，每个箭头均为直接父子关系：

```text
main / v1.3.0  268887c0bd7f1c987317fd07d0b4e221d38b84df
  → Step 1     d7463c9701a1e1869caf4ebfcb2d8e28fa889b10
  → Step 2     eb53686253905e6b4e427a552d156708b7c49a0a
  → Step 3     d63547de128482fdca3a01676273be002fd10faf
  → Step 4     07f0dc3cb8f734814ba41dcbdcbcf60721df90b0
  → Step 5     本分支最终提交，见 git log -1 和工程交付回复
```

`git merge-base --is-ancestor` 对 main、Step 1、Step 2、Step 3 均退出 0。Step 4 完整包含前序必要改动，无需重复 cherry-pick 或合并。远程核实 main、Step 1、Step 3、Step 4 SHA 与本地一致；远程没有 Step 2 命名分支，但其提交已经是远程 Step 3/4 的祖先，不是代码缺失。

原 main 未提交的 `docs/interview/` 保留；Step 1～4 worktree 状态干净。初次受限查询 main 出现工作树识别错误，随后显式指定 `--work-tree=D:/AI_develop/KnowledgePilot` 成功读取状态；没有 reset、配置修改或清理。

## 2. 最终集成审查

- 配置：默认本地地址、模型与 CWD/data 保留；显式 KP_DATA_DIR 必须绝对。原文及向量库统一数据根。Python 不自动读 .env；Compose 和 Linux 启动器的环境规则已在当前文档区分。
- Docker：真实入口为 `python -m uvicorn knowledge_pilot.api.app:app`，单 worker、UID 10001；Compose 固定内部 /app/data，宿主绑定目录须存在，127.0.0.1 端口映射，外部宿主 Ollama。构建上下文按 allowlist 排除数据与 .env。
- Linux 工具：宿主路径/权限/URL 检查不等于容器检查；up.sh 在同挂载内运行 UID 10001 实际写入探针。没有把 Windows 结果认作原生 Linux 验收。
- 日志与异常：JSON allowlist、请求 ID、值脱敏 traceback；输入 400/404/422、模型 502/503/504、未知内部错误 500 保持 Step 3 契约。/health 是轻量 liveness，不是上游 readiness。
- 跨模块：六条 API 路由通过原 Service、原 Agent/工具、Embedding 与真实 Chroma；独立进程及 owner marker 防止打开用户库。
- 兼容性：main..候选的 tools、rag、evaluation 源码与 data/evaluation、docs/evaluation 无 diff；Chroma 生产变更仅为可配置数据路径。Agent 的变化限于既有 Step 3 传输/响应校验与工具异常日志，没有改最大轮数、顺序执行、Observation 或 Trace。SYSTEM_PROMPT 保持原文，默认 Dense 不变。

独立只读代码审查未发现需在 Step 5 修复的新增可操作生产问题。Step 5 不修改生产代码、测试实现、依赖、Dockerfile 或 Compose，仅整理文档并保存新运行证据。

## 3. 本轮真实结果

- **PASS：全量 pytest 479 passed、1 skipped、2 warnings、49 subtests，65.09 秒，退出 0。** 与 Step 4 479/1 一致，无新增失败或跳过。
- **PASS：真实本地 Uvicorn + 明确模拟的 HTTP 模型上游，29 请求、23 检查。** 包括 CRUD、真实持久化索引、更新后检索、删除后清除、多轮工具执行、400/404/422/500/502/503/504、请求 ID 与日志隐私、临时资源清理。
- **PASS：真实 Ollama 最小验证。** gemma4:e2b 聊天 200，bge-m3:latest 文档上传 201，实际 1024 维向量及新文档检索，删除 200；子进程与独立临时数据清理成功。
- **PASS：Compose 配置检查，退出 0。**
- **BLOCKED：当前 Docker Engine 不可连接，命名管道 dockerDesktopLinuxEngine 不存在。** 当前候选的镜像构建、容器启动/网络/UID 写入/重建持久化 NOT_RUN；不重装或修复 Desktop，不改 daemon。
- **DEFERRED_DEBT：原生 Linux。** 本轮未运行，不再阻塞本地主线。

新原始证据：[step4-evidence-20261027T085100Z-5a1b30.json](step4-evidence-20261027T085100Z-5a1b30.json)。文件名和 schema 沿用既有 Step 4 验收器，本轮执行目录是 Step 5。运行时源码基线为 07f0dc3，后续 Step 5 仅改文档；不得将该文件描述为运行时已有最终提交 SHA。完整命令和边界见 [验证记录](step5-validation.md)。

Step 1 的 9/9 Docker PASS 是 2026-10-23 的历史结果，不升级为当前候选容器 PASS。真实 Ollama 的最小检查不证明真实模型自主选择了工具、答案语义全面正确或冻结评测成绩有所提升。多轮工具证据属于明确模拟上游驱动、原执行器实际执行的场景。

## 4. 非原子更新与遗留风险

`api/services.py:update_document_service` 写新 raw 内容，调用 `vector_store/chroma_store.py:update_document`；后者先 `delete_document` 再 `ingest_document`。Embedding 或 upsert 失败可造成旧索引丢失。Service 的异常分支仅尝试恢复原文字节/删除新文件，不恢复旧向量，也不提供跨文件与 Chroma 的事务。

这是 V1.1 起的已知技术债，main 到候选中该顺序未改。正常更新通过测试不证明失败原子性。本轮不新增故障数据实验，不将其误报为已修复。对学习/单机受控候选可提交审查；要求更新无损的生产用途为 No-Go。后续单独设计预生成向量、版本切换/补偿与失败恢复测试，不能只交换两行代码就宣称事务安全。

其他边界：未验收完整备份恢复或跨平台 source metadata 迁移；无 API 认证；单 worker/内嵌 Chroma，不宣称多实例共享写入。基础镜像非 digest 固定、传递依赖未全锁定；当前 Compose 开发镜像标签可覆盖，正式镜像应记录不可变身份。没有增加供应链保证或容量/长期稳定性声明。

## 5. Go / No-Go 与交付

**GO：提交、推送 Step 5 开发分支，进入人工源码与工程验收。** 本地回归和 API 集成无新增失败，前序工程成果完整。

**NO-GO：当前自动合并、创建 v1.4.0 Tag 或宣布正式发布。** 必须等待人工审查；当前候选 Docker 重验仍有缺口。审查者需明确决定当前 Docker 验证是否为发布门槛，或接受注明范围的本地工程版本；不得静默沿用旧镜像结果。原生 Linux 按现有决定独立跟踪，不重新提升为主线阻断。

本轮文件：README.md、docs/deployment/release-candidate.md、本报告、step5-validation.md、v1.4-release-readiness.md、step5-source-handoff.md、新原始 JSON，共 7 文件。原部署报告/冻结材料不改写。

发布说明见 [Release Readiness](v1.4-release-readiness.md)，教学入口见 [Step 5 源码交接](step5-source-handoff.md)。
