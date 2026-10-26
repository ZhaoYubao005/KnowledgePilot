# KnowledgePilot V1.4 Step 3：真实源码教学与工程交接

交付日期：2026-10-26（Asia/Singapore）。本文件对应已经实现的真实源码，不是伪代码。

## 1. 工程身份与验收边界

- 主仓库 `D:\AI_develop\KnowledgePilot` 仍是 main / V1.3，不能在那里寻找未合并的 Step 3。
- Step 2 已安全提交：`eb53686253905e6b4e427a552d156708b7c49a0a`，分支 `v1.4-step2-linux-runtime`。其 Docker/原生 Linux 验收仍为 BLOCKED，报告没有改成 PASS。
- Step 3 分支：`v1.4-step3-service-reliability`；独立工作区：`C:\Users\lenovo\.codex\.chatgpt-projects\g-p-6a9c0574f0648191afc307eb07a1456b\KnowledgePilot-v14-step3`。
- Step 3 完成源码实现、离线回归和真实本地 HTTP 故障注入验证；不是 Docker/Linux 部署验收，也不声称真实 Ollama 已验收。最终 Step 3 提交身份由该分支的 `git log -1` 与交付回复确认。
- 未合并 main、未推送本轮分支、未创建 Tag。Docker 排障不属于本轮操作。

## 2. 文件清单

新增生产模块：

- `src/knowledge_pilot/errors.py`：明确的配置、输入、模型和内部错误类型。
- `src/knowledge_pilot/logging_config.py`：安全 JSON formatter、请求 ContextVar、幂等应用日志配置。
- `src/knowledge_pilot/llm/transport.py`：有界 HTTP、状态检查、JSON 对象解析和错误转换。
- `src/knowledge_pilot/api/reliability.py`：纯 ASGI 请求边界、错误处理器、422 脱敏与安装函数。

修改的原有文件：

- `config.py`：配置错误分类，新增日志等级与 connect/read 超时设置。
- `llm/ollama_client.py`：只替换上游通信/响应校验并加入工具异常诊断；不改决策轮、工具顺序、Observation、Trace 或停止条件。
- `retrieval/embedding.py`：只加强上游边界和向量形状/数值校验。
- `api/app.py`：安装日志/错误边界，收紧任意 ValueError/KeyError 的错误映射，声明 500/504。
- `api/services.py`：原有文档校验改为 InputError，仍为 ValueError 子类；不重写 CRUD、存储或非原子更新流程。
- `.env.example`、`compose.yaml`：透传日志与超时配置，不改变 Step 1 拓扑或数据挂载。

新增/修改验证材料：`tests/test_service_reliability.py`、`tests/test_configuration.py`、`scripts/verify_step3_local.py`、`docs/engineering/step3-plan.md`、本报告和三份本地运行 evidence JSON。失败记录保留，不覆盖历史事实。

## 3. 从哪里开始读源码

以下行号已在本轮实际文件上核实；后续改代码后应重新核对，不能把行号当作永久 API。

### 新实现：异常类型

打开 [errors.py](C:/Users/lenovo/.codex/.chatgpt-projects/g-p-6a9c0574f0648191afc307eb07a1456b/KnowledgePilot-v14-step3/src/knowledge_pilot/errors.py:4)。

- `ConfigurationError(ValueError)`，第 4 行；非法部署配置仍可被既有 `except ValueError` 调用者捕获。
- `InputError(ValueError)`，第 8 行；显式输入校验与内部计算错误分开。
- `InternalServiceError(Exception)`，第 12 行。
- `ModelError.__init__(self, operation: str)`，第 17 行；只保存安全的 llm/embedding 操作标识。
- `ModelUnavailable`、`ModelTimeout`、`ModelResponseError`，第 22、26、30 行；分别表示连接、超时、HTTP/JSON/schema 异常。

### 新实现：安全日志

打开 [logging_config.py](C:/Users/lenovo/.codex/.chatgpt-projects/g-p-6a9c0574f0648191afc307eb07a1456b/KnowledgePilot-v14-step3/src/knowledge_pilot/logging_config.py:12)。

- `SafeJSONFormatter.format(self, record: logging.LogRecord) -> str`，第 19 行。
- `configure_logging(level: str = 'INFO', *, stream=None) -> None`，第 43 行。
- `request_id` 是 ContextVar，不是全局可变字符串；每个异步请求有自己的值，FastAPI 的同步 worker 会继承其上下文。

formatter 只接受固定 event 和元数据字段，忽略任意 msg 参数、body、额外字段与异常文本。Traceback 保留模块、函数、行号和异常类型/因果链，排除绝对路径、源代码行、局部变量与异常 message。不会通过正则猜测哪些字符串是密钥。

日志默认发到 stderr，不创建日志文件或轮转任务。只配置 `knowledge_pilot` logger；不改变 root handlers。单独关闭 `uvicorn.access`，因为其默认访问日志包含真实路径/查询串，由安全的路由模板日志替代；不接管其他第三方 logger。

### 新实现：上游 HTTP 边界

打开 [transport.py](C:/Users/lenovo/.codex/.chatgpt-projects/g-p-6a9c0574f0648191afc307eb07a1456b/KnowledgePilot-v14-step3/src/knowledge_pilot/llm/transport.py:12)。

`post_json(url: str, payload: dict, *, operation: str, post) -> dict`：

1. 使用显式 connect/read timeout 调用传入的 requests.post。
2. `raise_for_status()` 拦截非成功 HTTP，之后才解析 JSON。
3. 用 `raise ... from error` 保留异常因果；不把原始异常文本用作公开错误信息。
4. 拒绝非 JSON object；记录安全的上游完成/失败事件，不记录 URL、模型响应、用户消息或文档。

保留 post 参数使原调用点与已有 requests.post 测试接缝可继续使用；没有引入新的 HTTP SDK，也没有自动重试。`upstream_complete` 只代表 HTTP/JSON object 阶段完成，后续模型 schema 校验仍可能失败。

### 新实现：请求与错误边界

打开 [reliability.py](C:/Users/lenovo/.codex/.chatgpt-projects/g-p-6a9c0574f0648191afc307eb07a1456b/KnowledgePilot-v14-step3/src/knowledge_pilot/api/reliability.py:19)。

- `safe_input_detail(error: ValueError) -> str`，第 19 行：只返回白名单固定校验信息。
- `async service_error_handler(request, error: Exception) -> JSONResponse`，第 25 行。
- `async validation_error_handler(request, error: RequestValidationError) -> JSONResponse`，第 45 行。
- `async http_error_handler(request, error: HTTPException) -> JSONResponse`，第 54 行。
- `RequestLoggingMiddleware.__call__(self, scope, receive, send)`，第 70 行。
- `install_reliability(app) -> None`，第 109 行。

服务错误处理器负责固定状态/安全 detail；middleware 负责 request ID、耗时、未处理异常和最终访问记录。422 保留 detail 列表及 loc/type/msg 结构，但移除 input/ctx 并使用安全 message，避免回显无效用户输入。请求 ID 由服务端生成，不信任客户端任意 ID。

若响应头已经发送，再发一个 500 会破坏 HTTP 协议。该路径先记录安全原异常 traceback，再抛出固定文本的 InternalServiceError；request_complete 的 status 是已经发出的状态，不表示响应体一定完成。当前六个 API 均为普通 JSON 响应，不宣称已做流式/后台任务完整验收。

### 原有函数：经过最小修改

- [config.py:9](C:/Users/lenovo/.codex/.chatgpt-projects/g-p-6a9c0574f0648191afc307eb07a1456b/KnowledgePilot-v14-step3/src/knowledge_pilot/config.py:9)：`_setting(name, default)` 是原函数，改为明确 ConfigurationError；`_positive_seconds(name: str, default: str) -> float`（第 36 行）为新增函数。
- [ollama_client.py:20](C:/Users/lenovo/.codex/.chatgpt-projects/g-p-6a9c0574f0648191afc307eb07a1456b/KnowledgePilot-v14-step3/src/knowledge_pilot/llm/ollama_client.py:20)：`chat_with_ollama(messages, max_steps=5)` 是原函数。保留 tool-only message 可以没有 content 的既有行为；只在确实没有 tool_calls 的最终回答时要求字符串 content。
- [embedding.py:8](C:/Users/lenovo/.codex/.chatgpt-projects/g-p-6a9c0574f0648191afc307eb07a1456b/KnowledgePilot-v14-step3/src/knowledge_pilot/retrieval/embedding.py:8)：`embed_text(text)` 是原函数，加入列表、非空、单向量、有限数值校验，排除 bool/NaN/Infinity/超大整数溢出。没有固定维度到 1024，避免擅自限制已配置模型；索引维度一致性仍由现有存储约束。
- [services.py:31](C:/Users/lenovo/.codex/.chatgpt-projects/g-p-6a9c0574f0648191afc307eb07a1456b/KnowledgePilot-v14-step3/src/knowledge_pilot/api/services.py:31)：`create_document(filename: str, content: bytes)`；第 134 行 `update_document_service(document_id: str, filename: str, content: bytes)`。仅将三项已知输入检查改成 InputError。
- [app.py:47](C:/Users/lenovo/.codex/.chatgpt-projects/g-p-6a9c0574f0648191afc307eb07a1456b/KnowledgePilot-v14-step3/src/knowledge_pilot/api/app.py:47)：原有 `chat(request: ChatRequest)`，业务调用未重写；原有 upload/delete/update 的错误分支收紧。`upload_document(file: UploadFile = File(...))` 第 77 行、`remove_document(document_id: str)` 第 127 行、`update_document_route(document_id: str, file: UploadFile = File(...))` 第 151 行。

health()/get_documents()/chat_service()/embed_chunks() 的函数体未改；统一 middleware 使其请求也拥有安全访问记录。RAG pipeline、Dense/BM25/Hybrid/RRF、工具注册/执行器、Chroma 实现和冻结数据均未改。

## 4. 真实调用链

启动：Uvicorn 加载 `knowledge_pilot.api.app:app` → config 读取并验证环境 → 配置应用日志 → 原 services 导入/Chroma 初始化 → 创建 FastAPI 并安装 middleware/handlers。非法启动配置直接失败，不伪装成已经 ready 的服务。

正常聊天：请求 → middleware 生成 request ID → FastAPI/Pydantic → 原 chat route → 原 chat_service → 原 chat_with_ollama → post_json → requests.post → 原工具/Observation 循环 → ChatResponse → middleware 加 X-Request-ID → 一条 request_complete 路由模板日志 → finally 重置 ContextVar。

错误聊天：模型连接失败 → post_json 抛 ModelUnavailable 并保留 cause → service_error_handler 记录安全 traceback 与类别 → 503 固定 detail → 同一个 request ID 的完成日志。JSON/schema 异常为 502，超时为 504。

其他错误：显式输入错误为 400，请求模型校验为 422；未知 ValueError/不匹配 document_id 的 KeyError 为内部 500。已知文档不存在仍为 404。未知异常不反射到客户端，middleware 记录 value-free traceback 并返回固定 500。

上传：原 upload route → 原 create_document 的 InputError/UTF-8 校验 → 原 Chroma ingest → 改进后的 embed_text/post_json。原文落盘、分块和更新顺序没有重写。

## 5. 设计取舍与兼容性

- 使用标准 logging、ContextVar、已有 FastAPI/requests，不增加框架或依赖，不把日志系统做成新的服务。
- HTTP detail 兼容已知错误；新增 504 与内部 500。422 的输入回显被主动删除，这是有意的隐私增强。
- 显式输入类型是 ValueError 子类；配置类型也是 ValueError 子类。测试由“stderr 必含 ValueError 字面量”更新为验证 ConfigurationError 与继承兼容性，没有删除非法配置失败测试。
- connect/read 默认 5/120 秒，可由 `KP_OLLAMA_CONNECT_TIMEOUT_SECONDS` / `KP_OLLAMA_READ_TIMEOUT_SECONDS` 设置为有限正数。read timeout 不等于整个 Agent 请求总时限；本轮没有承诺请求总 SLA，也不改 max_steps 的既有契约。
- `KP_LOG_LEVEL` 默认 INFO；DEBUG 不会自动开启第三方 HTTP 客户端的 debug 日志。
- 工具异常仍按原 Agent 契约转成 Observation 和 trace，不改变答案/trace 内容，只加入安全诊断日志。因此业务 trace 不是审计日志，也不能从本次日志脱敏推导为所有业务输出都已过滤。保存/转发业务 trace 仍需调用者审慎处理。
- 原文更新仍非原子；导入 services 仍会初始化 Chroma；本轮未加入 readiness、旧库迁移、事务更新、上传大小限制或自动重试。

## 6. 实际验证与未完成事项

Step 2 提交前回归：455 passed、1 skipped、2 warnings（2026-10-26，26.30s），保留 BLOCKED。

Step 3 目标回归命令：

```powershell
$env:PYTHONPATH = Join-Path (Get-Location) 'src'
& D:/Anaconda/envs/knowledge-pilot/python.exe -B -m pytest -p no:cacheprovider -q tests/test_service_reliability.py tests/test_api_contract.py tests/test_agent_loop.py tests/test_configuration.py
```

结果：49 passed、2 warnings、27 subtests passed，3.95s。

Step 3 最终全量（工作目录为 Step 3，TEMP/TMP 指向 data/test-tmp，显式关闭原有真实知识库集成开关）：

```powershell
$env:TEMP = Join-Path (Get-Location) 'data/test-tmp'
$env:TMP = $env:TEMP
$env:PYTHONPATH = Join-Path (Get-Location) 'src'
$env:KNOWLEDGE_PILOT_RUN_INTEGRATION = '0'
& D:/Anaconda/envs/knowledge-pilot/python.exe -B -m pytest -p no:cacheprovider -q --basetemp ./data/pytest-step3-final-20261026
git diff --check
```

结果：**472 passed、1 skipped、2 warnings、49 subtests passed，10.26s**。唯一跳过项仍是原有真实知识库测试；两条警告仍来自现有 Starlette/httpx 和 anyio 弃用。没有安装替代包。MSYS shell 测试在授权沙箱外运行，数据仅在当前 worktree 临时目录。

真实本地 HTTP 故障注入命令：`D:/Anaconda/envs/knowledge-pilot/python.exe -B scripts/verify_step3_local.py`。使用真实 Uvicorn/FastAPI 和临时 Chroma；模型服务是明确标注的本地 HTTP fixture，不是实际 Ollama。验证 200、201、422、502、503、504、唯一请求 ID、真实进程日志无 synthetic 敏感正文及安全 traceback 帧。

最新通过证据：[step3-evidence-20261026T111332Z-18bd82.json](step3-evidence-20261026T111332Z-18bd82.json)。初次失败（连接期限 0.2 秒先触发 Windows timeout，而非 connection refused）与修正为默认 5 秒后的通过证据均保留；没有将失败改成成功，也没有为此修改生产错误分类。

只读代码复核无 Critical/Important；发现的超大整数向量 OverflowError 已先复现再修正为 ModelResponseError。另补充 tool-only content 兼容、KeyError 分类、并发 request ID、响应开始后的异常与 OpenAPI 500/504 测试。

未完成：本轮真实 Ollama 端到端、Docker 镜像/容器、原生 Linux、容器持久化和压测均未执行；Step 2 的 BLOCKED 仍成立。本轮可认定工程/本地验证完成，不认定完整部署验收。

## 7. ChatGPT 教学顺序

需要用户亲自掌握：

1. 先用 errors.py 理解“异常类型”和“公开错误消息”为什么是两个概念；再看 raise ... from 保留因果。
2. 跟踪一次 503：transport → handler → JSONResponse → middleware，确认业务成功结构没被重写。
3. 跟踪一次 422 与 500，理解为何不能返回 `str(exc)`、validation input 或完整 traceback。
4. 用 formatter 和并发测试理解安全字段白名单、ContextVar、线程上下文与 finally reset。
5. 阅读 ollama_client.py 的最小 diff，指出哪些行是通信边界，哪些是必须保持稳定的 Agent 决策逻辑。
6. 能解释单测、本地 fixture 故障注入、真实 Ollama、Docker 与原生 Linux 五类证据的区别。

重复性工程可由代理承担：枚举状态码、补齐 OpenAPI、环境示例、参数矩阵、日志样板、运行回归与整理证据。用户不需要逐行背这些文件；应能指出入口、边界、失败路径与验收范围。

不要先拿假设代码教学。按本报告链接打开当前 Step 3 worktree 的真实函数，再结合对应测试阅读；后续合并改变位置时，以 Git 提交身份和实际源码重新定位。

官方设计依据：[FastAPI 异常与校验处理](https://fastapi.tiangolo.com/tutorial/handling-errors/)、[Starlette 纯 ASGI middleware](https://www.starlette.io/middleware/)。资料用于解释框架边界，本报告的通过状态来自实际测试输出。
