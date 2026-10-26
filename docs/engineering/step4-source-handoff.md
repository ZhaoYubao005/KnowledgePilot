# KnowledgePilot V1.4 Step 4：真实源码与集成测试教学交接

日期：2026-10-26（Asia/Singapore）。教学对象为当前实际文件，不是示意实现。

## 1. 代码身份与范围

从本地与 origin 核实的最新 Step 3 `d63547de128482fdca3a01676273be002fd10faf` 建立 `v1.4-step4-api-integration`，独立工作区：

`C:\Users\lenovo\.codex\.chatgpt-projects\g-p-6a9c0574f0648191afc307eb07a1456b\KnowledgePilot-v14-step4`

main 不是本轮教学目录。Step 4 的正式 Commit 见本分支 `git log -1` 与交付回复；证据保存了运行时基线 SHA、dirty 状态和源码指纹，不能把运行时的未提交文件误认成旧 Commit 的内容。

本轮没有修改任何生产 `src/` 文件，也没有修改六个 API、Agent/RAG/检索语义、冻结评测材料或默认 Dense。没有需要最小修复的 Step 3 产品 Bug。代码审查修正的两处问题都属于新测试工具：超时后的进程树清理、真实模型检索的合理等待期限。

## 2. 新增文件

- `scripts/verify_step4_api.py`：可独立执行的真实 HTTP/Chroma 集成验收器、store worker、可选真实 Ollama 与有限 Docker 检查。
- `scripts/integration/model_fixture.py`：明确标记的模拟 Ollama HTTP 服务，生成确定性向量和分轮 Tool Calling 响应。
- `scripts/integration/processes.py`：验收子进程超时后的整棵自有进程树清理。
- `tests/integration/test_api_e2e.py`：实际运行验收子进程的测试，以及数据隔离/失败证据保护测试。
- `tests/integration/test_process_cleanup.py`：真正创建父/子进程、触发超时并核对两者退出。
- `docs/engineering/step4-plan.md`：现有覆盖审计与本轮边界。
- 本教学报告、`step4-acceptance-20261026.md` 与结构化运行证据。

没有改写旧的 test_api_contract、test_service_reliability 或 verify_step3_local；它们保留各自的单元/TestClient/历史本地验证职责。

## 3. 原有覆盖与缺口

`tests/test_api_contract.py` 在导入 app 前替换整个 Service，能证明路由调用与返回码，不能证明真实 Chroma 入库。

`tests/test_service_reliability.py` 已证明异常分类、日志、并发请求 ID 和校验脱敏；无需在 Step 4 再逐项复制所有 Mock 矩阵。

`scripts/verify_step3_local.py` 已启动真实 API，覆盖正常聊天、错误状态与单次上传。但没有更新/删除后的实际索引查询，也没有实际 calculator + knowledge_base 的多轮调用。Step 4 重点补这些协同链路。

## 4. 新实现函数与真实位置

下列行号在本轮源码上核实；后续修改需重新定位。

打开 [verify_step4_api.py](C:/Users/lenovo/.codex/.chatgpt-projects/g-p-6a9c0574f0648191afc307eb07a1456b/KnowledgePilot-v14-step4/scripts/verify_step4_api.py:25)：

- `validate_owned_root(root: Path, nonce: str) -> None`，第 25 行：没有本轮 ownership marker/nonce 的目录拒绝打开。
- `api_environment(root: Path, origin: str, *, inherited=None, real=False) -> dict`，第 31 行：清除继承的 KP_ 配置，固定新 data 目录与当前 src，避免误开开发库。
- `record_request(records: list, label: str, method: str, route: str, actual: int | None, expected: int, request_id: str) -> None`，第 45 行：先记录实际/预期与失败状态，再抛断言，不能把错误状态写成成功。
- `ApiProcess.__init__(self, root: Path, nonce: str, origin: str, records: list, *, real=False)`，第 56 行。
- `ApiProcess.start(self)` / `stop(self)`，第 71 / 93 行：真正启动、等待和关闭 Uvicorn，不替换 Service。
- `ApiProcess.request(self, label, method, path, expected, **kwargs)`，第 106 行：发实际 HTTP，记录状态码与服务端 request ID；网络失败记录 actual_status=null。
- `ApiProcess.inspect_store(self, query='blue', document_id=None)`，第 122 行：先停止 API，再创建独立 store worker，避免并发打开嵌入式库。
- `probe_store(root, nonce, query, document_id)`，第 139 行：实际 `collection.get()`、原 `search()` 和实际 Embedding；输出文档/metadata/结果与向量维度，禁止输出完整向量。
- `require(evidence, name, condition, **details)`，第 151 行；`check_logs(evidence, api)`，第 157 行。
- `core_scenarios(evidence, api, fixture)`，第 173 行：完整 CRUD、Agent 和故障场景。
- `run_suite(test_root: Path, evidence_root: Path, *, real_ollama=None, docker=None, compose_plugin=None) -> tuple[dict, Path]`，第 259 行。
- `check_docker(docker, compose_plugin=None)`，第 320 行：一次有界只读检查，不进行修复、安装或 daemon 变更。
- `run_real_ollama(test_root, origin, nonce)`，第 340 行：仅接受无凭据 loopback origin，确认已有模型后在另一个临时库执行真实最小验证。
- `main()`，第 411 行：CLI 与独立 store worker 入口。

打开 [model_fixture.py](C:/Users/lenovo/.codex/.chatgpt-projects/g-p-6a9c0574f0648191afc307eb07a1456b/KnowledgePilot-v14-step4/scripts/integration/model_fixture.py:12)：

- `ModelFixture`，第 12 行；`start(self)` / `close(self)`，第 63 / 67 行。
- 它是模拟上游，不是模型推理。含 red 的文本得到第一个单元向量，blue 得到第二个；更新后的 blue 查询必须与实际新向量相似度 >0.99，故不能仅用“API 返回 200”冒充检索正确。
- tool_loop 模式按已观察到的工具数量返回：calculator → search_knowledge_base → 最终消息。计算与检索由生产工具执行器完成，不在 fixture 中伪造工具结果。

打开 [processes.py](C:/Users/lenovo/.codex/.chatgpt-projects/g-p-6a9c0574f0648191afc307eb07a1456b/KnowledgePilot-v14-step4/scripts/integration/processes.py:7)：

- `run_owned(command, *, cwd, env, timeout)`：平时返回 CompletedProcess；超时只终止本函数创建的 PID 树。Windows 用明确 PID 的 taskkill /T，POSIX 用自己的新 session/process group。没有进程名通配符，也不停止用户 Ollama。

所有上列函数都是 Step 4 新实现；生产 Service、Agent、Embedding、Chroma 函数均为原有未改函数。

## 5. 适合学习的真实测试

打开 [test_api_e2e.py](C:/Users/lenovo/.codex/.chatgpt-projects/g-p-6a9c0574f0648191afc307eb07a1456b/KnowledgePilot-v14-step4/tests/integration/test_api_e2e.py:53)：

- `RealHttpIntegrationTests.setUpClass(cls)` 第 55 行，启动一次真实验收进程，读取其唯一 evidence，再由三个测试审查跨模块结果；不是 Mock Service。
- `test_crud_and_actual_store_queries(self)` 第 71 行，要求上传、更新、删除三次 store inspection 与原文字节检查均通过。
- `test_agent_tool_loop_and_error_contracts(self)` 第 77 行，要求真实 calculator/search 轨迹和九种实际 HTTP 状态。
- `test_logs_ids_cleanup_and_upstream_provenance(self)` 第 84 行，要求日志关联与清理，并明确默认 pytest 不执行真实 Ollama。

打开 [test_process_cleanup.py](C:/Users/lenovo/.codex/.chatgpt-projects/g-p-6a9c0574f0648191afc307eb07a1456b/KnowledgePilot-v14-step4/tests/integration/test_process_cleanup.py:17)：

- `test_timeout_stops_parent_and_descendant(self)`：真实创建 sleep 父/子进程，触发 2 秒超时，再用系统进程状态检查两者退出。该测试是进程清理的证据，不能用来声称 API 功能通过。

学习时先运行/阅读 `record_request` 的失败保护测试，理解“状态码一致”与“业务正确”是不同断言。再阅读 core_scenarios 中 upload → inspect_store → update → inspect_store → chat_tools → delete → inspect_store 的实际代码。

## 6. 跨模块调用链与隔离

实际请求：requests 客户端 → 独立 Uvicorn → FastAPI 参数校验/日志 middleware → 原 route → 原 Service → 原 Agent 或 CRUD → 原工具注册器 / Embedding → 实际 Chroma → HTTP 响应。

工具回合：模拟 HTTP 上游只返回工具意图 → 生产 Agent 执行 calculator 得到 12 → 写回 Observation → 下一轮执行 knowledge_base → 调用真实 search/Embedding/Chroma → 再写 Observation → 上游返回最终消息。检查 step=1/2、工具名称、结果与 Trace 字段，不改决策轮数。

索引检查：停止 API → 子进程导入原 chroma_store → 验证 owner marker 与 KP_DATA_DIR → get/query/search → 子进程退出 → 重启 API。这样验证的是持久化真实数据，而不是第二个并发 client 的缓存。

每轮在调用者指定测试根下新建 TemporaryDirectory；KP_DATA_DIR 始终为它的 data 子目录。原始 Chroma、冻结评测库和继承环境的 data 路径都不参与。原文文件与 SQLite 在临时目录中，最终验证 children_exited 与 temporary_data_removed。证据保存于目录外，采用 exclusive create，不覆盖历史。

## 7. 故障验证与隐私

- 400：真实后缀、空文件、空白、UTF-8 校验。
- 404：真实缺失文档的更新与删除。
- 422：真实 Pydantic query/max_steps/file 校验，并检查不回显 synthetic private marker。
- 502/504：模拟上游的 HTTP 错误、非法 JSON、错误 schema 与读取超时。
- 503：关闭模拟 HTTP 服务，真实连接失败后检查原错误映射。
- 500：在 API 停止后，仅将本轮原文目录备份并放置一个同名测试文件，触发真实文件系统错误；finally 恢复后继续验证删除，不 Mock Service、不破坏产品目录。
- 检查每个记录的请求 ID 与实际 JSON request_complete 日志一致、路由为模板、状态对应；完整进程日志不能包含 synthetic 凭据、完整测试文档或模型答案。业务 Trace 按 Step 3 原契约保留，但不复制到公开 evidence。

## 8. 证据阅读规则与运行方式

核心命令：

```powershell
& D:/Anaconda/envs/knowledge-pilot/python.exe -B scripts/verify_step4_api.py --test-root (Join-Path (Get-Location) 'data/step4-runs')
```

只对已存在模型进行可选真实验证时，加 `--real-ollama http://localhost:11434`。`--docker <docker.exe>` 和 `--compose-plugin <docker-compose.exe>` 仅做有限只读环境检查；可达也不等于容器验证通过。

evidence 中 `status` 与 `acceptance_scope=mandatory_local_api` 只评价核心本地集成。`optional.real_ollama`、`optional.docker`、`optional.native_linux` 必须分别读取。每个请求记录 method/route、actual_status、expected_status、request_id 和 HTTP 检查状态；JSON/索引/语义断言另在 checks 中，不能从一行状态码推导全部正确。

验收器只报告模型输出存在且 completed，不宣称真实模型答案语义正确或真实模型一定自主选择了工具。工具选择与多轮链路的确定性证据属于明确标注的 fixture 场景。独立 Linux 继续为 DEFERRED_DEBT，不再阻断本地阶段。

## 9. 教学重点与重复性工作

用户需要掌握：为什么 stub Service 不能证明入库；为什么用真实进程隔离全局导入；如何用不同向量发现更新后旧索引；如何区分模型意图与实际工具执行；为什么 finally、进程树和数据目录都要清理；为什么可选验收必须独立标记。

代理可承担的重复性工程：启动/关闭子进程、构造 multipart、生成 UUID/临时路径、枚举状态码、记录版本/源码 SHA、运行回归、检查远程 SHA 和提交 allowlist。无需让用户手工重跑机械步骤。

教学应直接打开本报告链接指向的实际测试与 runner，结合本次 evidence 阅读。不要先讲假设路由、新模型框架或未执行的 Docker/Linux 操作。
