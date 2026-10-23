# V1.4 Step 1 安全整合方案

日期：2026-10-23。状态：方案已核对，尚未执行 Git 提交或合并。

## 当前事实

- 独立 worktree 处于 detached HEAD，基线为 `v1.3.0` / `268887c0bd7f1c987317fd07d0b4e221d38b84df`。
- main 仍指向同一提交；tracked diff 和 staged diff 均为空。main 中原有 12 个 `docs/interview/` 未跟踪文件必须原样保留。
- Step 1 有 4 个已跟踪源码修改和一组新增工程、测试、脚本与文档文件。当前尚无 Step 1 提交，不能直接对 detached HEAD 执行常规 merge。
- 最终 Docker evidence 为 `passed`；9 项检查、14 条命令退出码均为 0。失败 evidence 与诊断报告是历史证据，不可覆盖最终报告。
- `data/docker-step1-*` 被现有 `.gitignore` 排除，只保留在本机作为验收数据；不进入 Git。

## 精确整合顺序

1. 在独立 worktree 从当前 detached HEAD 创建命名分支 `v1.4-step1-configuration-docker`。这一步只建立引用，不移动或覆盖文件。
2. 重新执行 Python 全量回归和 `git diff --check`；读取最终 Docker JSON 做一致性检查，不重复完整 Docker 验收。
3. 使用显式 allowlist 暂存下列 Step 1 文件，禁止 `git add .` / `git add -A`：

```text
.dockerignore
.env.example
Dockerfile
compose.yaml
src/knowledge_pilot/config.py
src/knowledge_pilot/retrieval/embedding.py
src/knowledge_pilot/vector_store/chroma_store.py
src/knowledge_pilot/api/services.py
tests/test_configuration.py
scripts/verify_step1_local.py
scripts/verify_step1_docker.py
docs/deployment/step1-plan.md
docs/deployment/step1.md
docs/deployment/step1-docker-validation.md
docs/deployment/step1-docker-acceptance-20261023.md
docs/deployment/docker-evidence-20261023T070821Z-5cf687.json
docs/deployment/docker-evidence-20261023T075418Z-8fba4c.json
docs/deployment/step1-integration-plan.md
docs/deployment/step2-linux-runtime-plan.md
```

4. 检查 `git diff --cached --name-status` 必须与 allowlist 完全一致；检查 staged diff 不包含 `data/`、`.env`、数据库、缓存、`docs/interview/`、冻结评测数据或算法实现。
5. 创建一个 Step 1 提交，建议消息：`feat: add v1.4 configuration and Docker deployment`。不创建 Tag、不推送。
6. 在 main 再次核对 HEAD、tracked/staged 状态和 12 个未跟踪文件。由于 main 与功能分支同基线，优先使用 `git merge --ff-only v1.4-step1-configuration-docker`；若不能快进则停止，不自动处理冲突。
7. 在合并后的 main 运行 Python 全量回归和配置测试；读取 Docker 通过证据。只有源码或容器配置在整合中发生变化时，才重跑完整 Docker 验收。
8. 保留独立 worktree，直到 main 验证完成且用户确认可清理；不删除本地验收数据、分支或 worktree。

## 为什么不直接复制文件到 main

复制会失去一组可审计的提交边界，也容易覆盖 main 中未来新增文件。分支化后精确暂存再快进，可以完整保留外部验收报告、失败/成功证据和现有用户资料，同时允许合并前审查每个路径。

## 当前决定点

本轮只提出并记录方案。执行整合属于下一次明确 Git 操作；在执行前仍需重新核对 main 是否有新提交或新 tracked 修改。
