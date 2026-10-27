# Step 5 真实源码教学交接

本轮没有新增或修改生产函数，也没有新测试实现；核心变更是 README/部署入口修正、最终 Git 集成审查、真实回归与证据、发布就绪判断。不要为教学构造不存在的 Step 5 Service 或新算法。

## 1. 真实工作目录与 Git

`C:\Users\lenovo\.codex\.chatgpt-projects\g-p-6a9c0574f0648191afc307eb07a1456b\KnowledgePilot-v14-step5`

分支 `v1.4-step5-release-readiness` 从 Step 4 `07f0dc3` 创建。main268887c → Step1d7463c9 → Step2eb53686 → Step3d63547d → Step407f0dc3，全部直接父子关系，Step 5 无需重做合并。Step 2 没有独立远程分支不代表内容没推送；它已经可从 Step 3/4 的提交图到达。完整 SHA 见本轮集成报告，最终 Step 5 SHA 以 git log -1 为准。

## 2. 已有真实函数及阅读位置

以下均为本轮未修改的真实函数；绝对链接指向本次教学工作区。

- [配置](C:/Users/lenovo/.codex/.chatgpt-projects/g-p-6a9c0574f0648191afc307eb07a1456b/KnowledgePilot-v14-step5/src/knowledge_pilot/config.py:9)：`_setting(name, default)` 与模块导入时读取。重点区分进程环境和 .env、显式绝对路径与兼容默认相对路径。
- [HTTP 入口](C:/Users/lenovo/.codex/.chatgpt-projects/g-p-6a9c0574f0648191afc307eb07a1456b/KnowledgePilot-v14-step5/src/knowledge_pilot/api/app.py:29)：`app`、`health()`；先 configure_logging，再导入 Service/Chroma，安装可靠性层。`/health` 不探测模型，不等于 readiness。
- [Service](C:/Users/lenovo/.codex/.chatgpt-projects/g-p-6a9c0574f0648191afc307eb07a1456b/KnowledgePilot-v14-step5/src/knowledge_pilot/api/services.py:14)：`chat_service(query: str, max_steps: int = 5)`；第 134 行 `update_document_service(document_id: str, filename: str, content: bytes)`。
- [Agent](C:/Users/lenovo/.codex/.chatgpt-projects/g-p-6a9c0574f0648191afc307eb07a1456b/KnowledgePilot-v14-step5/src/knowledge_pilot/llm/ollama_client.py:20)：`chat_with_ollama(messages, max_steps=5)`。工具仍顺序执行、Observation 写回、决策轮次与 Trace 未改。
- [实际库更新](C:/Users/lenovo/.codex/.chatgpt-projects/g-p-6a9c0574f0648191afc307eb07a1456b/KnowledgePilot-v14-step5/src/knowledge_pilot/vector_store/chroma_store.py:69)：`update_document(file_path, document_id, collection)`；第 75 行 `search(query, collection, top_k=3, document_id=None)`，仍为原 Dense 查询。
- [请求可靠性](C:/Users/lenovo/.codex/.chatgpt-projects/g-p-6a9c0574f0648191afc307eb07a1456b/KnowledgePilot-v14-step5/src/knowledge_pilot/api/reliability.py:64)：`RequestLoggingMiddleware`；第 109 行 `install_reliability(app) -> None`。
- [安全日志](C:/Users/lenovo/.codex/.chatgpt-projects/g-p-6a9c0574f0648191afc307eb07a1456b/KnowledgePilot-v14-step5/src/knowledge_pilot/logging_config.py:12)：`SafeJSONFormatter`；第 43 行 `configure_logging(level: str = 'INFO', *, stream=None) -> None`，只输出允许元数据与值脱敏帧。
- [验收主函数](C:/Users/lenovo/.codex/.chatgpt-projects/g-p-6a9c0574f0648191afc307eb07a1456b/KnowledgePilot-v14-step5/scripts/verify_step4_api.py:259)：`run_suite(test_root: Path, evidence_root: Path, *, real_ollama=None, docker=None, compose_plugin=None) -> tuple[dict, Path]`。第 340 行 `run_real_ollama(test_root, origin, nonce)` 单独检查真实上游。
- [真实集成测试](C:/Users/lenovo/.codex/.chatgpt-projects/g-p-6a9c0574f0648191afc307eb07a1456b/KnowledgePilot-v14-step5/tests/integration/test_api_e2e.py:53)：`RealHttpIntegrationTests`。复用 Step 4 实现，没有模拟新的产品代码。

## 3. 三条真实调用链

配置：launcher 导出 KP_ 环境 → config 模块校验 → app 配置日志并导入 services → chroma_store 初始化配置目录。Docker CMD 指向同一 app，不存在另一个演示服务。

聊天：实际 HTTP → Uvicorn → RequestLoggingMiddleware → Pydantic/Route → chat_service → 原 Agent → post_json → 模拟上游或真实 Ollama → 可能的原工具执行 → 响应模型 → request ID 和 JSON 完成日志。上游来源必须根据具体证据识别。

更新：PUT → 参数/输入校验 → update_document_service 写 raw → update_document 删除旧 Chunk → ingest_document 调用实际 Embedding 后 upsert → 响应。异常时 raw 的尝试恢复不覆盖已删除索引。正常路径 PASS 不能推出失败事务性。

## 4. 学习顺序与边界

先看提交图理解“包含祖先”与“有没有独立远程分支”的区别，再看环境配置与 Docker 数据边界，随后阅读实际测试中更新后库查询和故障状态，最后比较 JSON 的 mandatory_local_api、real_ollama、docker、native_linux 状态。

用户应掌握：证据范围、失败原子性、liveness/readiness、请求与索引断言的区别、发布候选和正式封版的区别。无需逐行学习代理执行的 multipart 拼装、随机目录、重复启停、Git allowlist 与 SHA 核对等机械步骤。

本轮 479/1；真实本地 HTTP 29/23；真实 Ollama 最小 PASS；Docker BLOCKED；原生 Linux DEFERRED_DEBT。不要把这些合并成“所有环境部署通过”。完整结果与可复现命令见 [验证记录](step5-validation.md)。真实模型本轮没有自主多工具选择验收或冻结评测重跑。

## 5. 对 ChatGPT 的交接

直接打开上述真实路径教学；配合 [Step 5 集成报告](step5-integration-report.md) 与本轮 JSON。Step 3/4 教学报告保留历史身份，当前路径以上述 Step 5 链接为准。用户无需先学习假设代码，也无需重复已由工程代理执行的机械测试。
