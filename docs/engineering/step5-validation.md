# Step 5 最终回归与可复现证据

日期：2026-10-27（Asia/Singapore）。以下为本轮实际命令与结果，不是历史成绩重述。执行目录为 KnowledgePilot-v14-step5 工作区根。Python 3.11.16，Windows 10.0.26200；FastAPI 0.141.1、requests 2.34.2、Chroma 1.5.9、Pydantic 2.13.5、Uvicorn 0.52.4。复用已安装环境，未安装依赖。

## 全量回归：PASS

```powershell
New-Item -ItemType Directory -Force data/test-tmp,data/step5-runs | Out-Null
$env:TEMP = Join-Path (Get-Location) 'data/test-tmp'
$env:TMP = $env:TEMP
$env:PYTHONPATH = Join-Path (Get-Location) 'src'
$env:KNOWLEDGE_PILOT_RUN_INTEGRATION = '0'
& D:/Anaconda/envs/knowledge-pilot/python.exe -B -m pytest -p no:cacheprovider -q --basetemp ./data/pytest-step5-final
```

实际退出码 0：`479 passed, 1 skipped, 2 warnings, 49 subtests passed in 65.09s (0:01:05)`。与 Step 4 479/1 一致，无新增回归失败。两条警告来自现有 Starlette/httpx 与 anyio 弃用。原有显式依赖开发库的知识库集成测试仍跳过；真实模型另以全新临时数据验证，不启用原库测试。

全量中包含旧单元与 TestClient 测试、新进程树清理测试及真实 Uvicorn/模拟上游集成。不能将全部 479 项描述为真实模型测试。

## 真实本地 HTTP 与可选环境检查

```powershell
& D:/Anaconda/envs/knowledge-pilot/python.exe -B scripts/verify_step4_api.py `
  --test-root (Join-Path (Get-Location) 'data/step5-runs') `
  --real-ollama http://localhost:11434 `
  --docker C:/Users/lenovo/AppData/Local/Programs/DockerDesktop/resources/bin/docker.exe `
  --compose-plugin C:/Users/lenovo/AppData/Local/Programs/DockerDesktop/resources/cli-plugins/docker-compose.exe
```

实际退出码 0；核心 29 请求、23 检查通过。该程序的退出码只表达 mandatory_local_api，必须另外读取 optional 各状态，本轮已核实如下：

- 本地实际网络进程、模拟模型 HTTP 上游：PASS。上传/更新/删除后分别停止 API，用独立 worker 打开实际持久化库查询，再重启 API。原 Service 没有被 Mock。
- 真实宿主 Ollama：PASS。real_chat=200、real_upload=201、real_delete=200，1024 维，实际文档检索 true；不证明真实模型自主多工具选择。
- Compose config：PASS，退出 0。
- Docker Engine：BLOCKED，退出 1，`dockerDesktopLinuxEngine` named pipe 不存在；容器验证 NOT_RUN。本轮无 build/up、无容器 UID 写入或重建持久化成功声明。
- 原生 Linux：DEFERRED_DEBT，本轮未执行。
- 核心与真实 Ollama 的 children_exited、temporary_data_removed 全部 true。

原始 JSON：[step4-evidence-20261027T085100Z-5a1b30.json](step4-evidence-20261027T085100Z-5a1b30.json)，保留每个请求的实际/预期状态、request ID、环境、源码哈希与独立可选状态。运行时间为 2026-10-27，使用 Step 4 runner 所以文件名/schema 不改。证据独占创建，不覆盖旧记录。

## Git 与静态核对

```powershell
git ls-remote --heads origin
git merge-base --is-ancestor main HEAD
git merge-base --is-ancestor v1.4-step1-configuration-docker HEAD
git merge-base --is-ancestor v1.4-step2-linux-runtime HEAD
git merge-base --is-ancestor v1.4-step3-service-reliability HEAD
git diff --exit-code main..HEAD -- src/knowledge_pilot/tools src/knowledge_pilot/rag src/knowledge_pilot/evaluation data/evaluation docs/evaluation
git diff --check
```

上述远程查询和四个祖先检查成功，受保护路径无差异，diff check 通过。本轮所有生产 src 相对 Step 4 不变，不需要对文档编辑重复运行耗时模型验收。独立只读审查未发现新增生产阻断问题，非原子更新保持已知债务。

所有数据测试只在新 owner-marker 临时目录执行；无原始 Chroma、冻结数据、用户文档或原库模型迁移操作。正式备份恢复、生产长时稳定性和多实例并发写入未验收。
