"""RAG / Agent Evaluation 独立启动入口。

无参数运行只检查环境，不打开 Chroma 或调用模型；--run-* 显式执行评测。
父进程创建新的 Python 子进程，在首次导入业务模块前固定
Evaluation CWD 和绝对 PYTHONPATH，避免连接开发知识库。
"""

import argparse
import json
import os
from importlib.machinery import PathFinder
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone

PROJECT = Path(__file__).resolve().parents[1]
SRC = PROJECT / "src"
RUNTIME = PROJECT / "data/evaluation/runtime/corpus_v1"
STORE = RUNTIME / "data/vector_store"
DATASET = PROJECT / "data/evaluation/cases_v1.json"


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _check_environment() -> dict:
    """只读检查独立启动环境；不导入业务模块、不连接数据库。"""
    _require(sys.version_info >= (3, 11), "项目要求 Python >= 3.11。")
    _require(Path.cwd().resolve() == RUNTIME, "CWD 必须是独立 Evaluation runtime。")
    _require(RUNTIME.resolve() == RUNTIME, "Evaluation CWD 不能重定向到其他目录。")
    _require(STORE.resolve() == STORE, "Evaluation Chroma 路径不能重定向。")
    _require(STORE != (PROJECT / "data/vector_store").resolve(), "禁止使用开发数据库。")

    pythonpath = os.environ.get("PYTHONPATH", "")
    _require(Path(pythonpath).is_absolute(), "PYTHONPATH 必须是绝对路径。")
    _require(Path(pythonpath).resolve() == SRC, "PYTHONPATH 必须仅指向项目 src。")
    _require(
        SRC in {Path(entry).resolve() for entry in sys.path if entry},
        "解释器的 sys.path 未包含项目 src。",
    )
    _require(sys.dont_write_bytecode, "请使用 python -B 启动。")
    _require(
        not any(
            name == "knowledge_pilot" or name.startswith("knowledge_pilot.")
            or name == "chromadb" or name.startswith("chromadb.")
            for name in sys.modules
        ),
        "环境检查前不应导入 KnowledgePilot 或 Chroma。",
    )
    spec = PathFinder.find_spec("knowledge_pilot", sys.path)
    _require(
        spec is not None and spec.origin is not None
        and Path(spec.origin).resolve() == SRC / "knowledge_pilot/__init__.py",
        "knowledge_pilot 将从其他项目位置导入。",
    )

    database = STORE / "chroma.sqlite3"
    _require(database.is_file(), "独立 Evaluation 数据库不存在；本入口不会自动建库。")
    _require(database.resolve() == database, "Evaluation SQLite 文件不能重定向。")
    _require(DATASET.is_absolute() and DATASET.is_file(), "正式 Dataset 路径无效。")
    _require(DATASET.resolve() == DATASET, "正式 Dataset 不能重定向。")
    dataset = json.loads(DATASET.read_text(encoding="utf-8"))
    _require(
        dataset.get("dataset_status") == "FROZEN"
        and dataset.get("frozen") is True
        and dataset.get("dataset_version") == "v1",
        "仅接受已冻结的 Dataset V1。",
    )
    _require(isinstance(dataset.get("cases"), list), "Dataset 缺少 cases 列表。")

    initialization = json.loads(
        (RUNTIME / "initialization_manifest.json").read_text(encoding="utf-8")
    )
    _require(
        Path(initialization["actual_chroma_path"]).resolve() == STORE,
        "初始化清单的数据库路径与独立环境不一致。",
    )
    _require(
        initialization["collection_name"] == "knowledge_pilot_docs",
        "初始化清单的 Collection 名称不符。",
    )

    return {
        "mode": "environment_check_only",
        "status": "READY",
        "project_root": str(PROJECT),
        "python_executable": sys.executable,
        "cwd": str(Path.cwd().resolve()),
        "pythonpath": pythonpath,
        "dataset_path": str(DATASET),
        "dataset_version": dataset["dataset_version"],
        "dataset_cases": len(dataset["cases"]),
        "expected_chroma_path": str(STORE),
        "collection_name_from_initialization_manifest": initialization["collection_name"],
        "business_modules_imported": False,
        "database_opened": False,
        "batch_evaluation_executed": False,
    }

def _run_one_case(case_id: str, k: int) -> None:
    # 1. 必须先检查独立环境
    _check_environment()
    _require(k > 0, "k 必须大于 0。")

    # 2. 读取冻结 Dataset，找到目标 Case
    dataset = json.loads(DATASET.read_text(encoding="utf-8"))

    cases = [
        case for case in dataset["cases"]
        if case["id"] == case_id
        and case["case_type"] == "retrieval"
    ]

    _require(len(cases) == 1, "未找到唯一的 Retrieval Case。")

    # 3. 环境检查通过后，才允许导入 Chroma
    from knowledge_pilot.vector_store.chroma_store import (
        collection,
        search,
    )
    from knowledge_pilot.evaluation.rag_runner import (
        run_rag_evaluation,
    )

    # 4. Search Adapter：适配真实 Chroma
    retrieved_ids = []

    def search_adapter(query, top_k):
        rows = search(
            query=query,
            collection=collection,
            top_k=top_k,
        )

        for _, _, metadata in rows:
            retrieved_ids.append([
                metadata["document_id"],
                metadata["chunk_index"],
            ])

        return rows

    # 5. 调用我们已经写好的 Runner
    results = run_rag_evaluation(
        cases,
        search_adapter,
        k=k,
    )

    # 6. 打印实际评分结果
    print(json.dumps({
        "case_id": case_id,
        "k": k,
        "retrieved_chunks": retrieved_ids,
        "scores": results[0],
    }, ensure_ascii=False, indent=2))


def _run_all_cases(k: int) -> None:
    # Step 1：先验证独立 Evaluation 环境
    _check_environment()
    _require(k > 0, "k 必须大于 0。")

    # Step 2：读取冻结 Dataset
    dataset = json.loads(DATASET.read_text(encoding="utf-8"))

    retrieval_cases = [
        case for case in dataset["cases"]
        if case["case_type"] == "retrieval"
    ]

    _require(
        len(retrieval_cases) == 16,
        "Dataset V1 应包含 16 条 Retrieval Case。"
    )

    # Step 3：环境检查通过后，才能导入 Chroma
    from knowledge_pilot.vector_store.chroma_store import (
        collection,
        search,
    )
    from knowledge_pilot.evaluation.rag_runner import (
        run_rag_evaluation,
    )

    # Step 4：Search Adapter
    def search_adapter(query, top_k):
        return search(
            query=query,
            collection=collection,
            top_k=top_k,
        )

    # Step 5：批量执行
    scores = run_rag_evaluation(
        retrieval_cases,
        search_adapter,
        k=k,
    )

    _require(
        len(scores) == len(retrieval_cases),
        "实际评测数量与 Retrieval Case 数量不一致。"
    )

    # Step 6：整体指标汇总
    def average(field):
        values = [
            row[field]
            for row in scores
            if row.get(field) is not None
        ]

        if not values:
            return None

        return sum(values) / len(values)

    summary = {
        "hit_rate": average("hit"),
        "mean_recall": average("recall"),
        "mrr": average("rr"),
        "mean_fact_coverage": average("fact_coverage"),
        "evidence_sufficient_rate": average("evidence_sufficient"),
        "average_latency_ms": average("latency_ms"),
    }
    error_count = sum(
        1 for row in scores
        if "error" in row
    )

    success_count = len(scores) - error_count

    summary["success_count"] = success_count
    summary["error_count"] = error_count

    summary["error_rate"] = (
        error_count / len(scores)
        if scores else None
    )

    # Step 7：输出报告
    report = {
        "dataset_version": dataset["dataset_version"],
        "k": k,
        "retrieval_case_count": len(scores),
        "summary": summary,
        "cases": scores,
    }

    # 1. 记录评测时间（UTC）
    run_time = datetime.now(timezone.utc)

    report["generated_at_utc"] = run_time.isoformat()

    # 2. 定义报告目录
    report_dir = PROJECT / "data" / "evaluation" / "reports"

    # 3. 确保目录存在
    report_dir.mkdir(parents=True, exist_ok=True)

    # 4. 创建唯一的报告文件名
    timestamp = run_time.strftime("%Y%m%dT%H%M%S_%fZ")

    report_path = report_dir / f"rag_baseline_v1_k{k}_{timestamp}.json"

    # 5. 保存 JSON 文件
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"Report saved: {report_path}")

    print(json.dumps(report, ensure_ascii=False, indent=2))

def _run_one_agent_case(case_id: str) -> None:
    # 1. 必须先完成独立环境检查
    _check_environment()

    # 2. 从冻结 Dataset 中查找 Case
    dataset = json.loads(DATASET.read_text(encoding="utf-8"))

    cases = [
        case for case in dataset["cases"]
        if case["case_type"] == "agent"
        and case["id"] == case_id
    ]

    _require(len(cases) == 1, "未找到唯一的 Agent Case。")

    # 3. 检查通过后再导入业务模块
    from knowledge_pilot.config import SYSTEM_PROMPT
    from knowledge_pilot.llm.ollama_client import chat_with_ollama
    from knowledge_pilot.tools.registry import TOOL_REGISTRY
    from knowledge_pilot.evaluation.agent_runner import (
        run_agent_evaluation,
    )

    # 4. 动态读取已注册的工具
    registered_tools = set(TOOL_REGISTRY.keys())

    # 5. 执行真实 Agent
    results = run_agent_evaluation(
        cases=cases,
        agent_fn=chat_with_ollama,
        registered_tools=registered_tools,
        system_prompt=SYSTEM_PROMPT,
    )

    # 6. 输出结果
    print(json.dumps({
        "case_id": case_id,
        "registered_tools": sorted(registered_tools),
        "results": results,
    }, ensure_ascii=False, indent=2))

def _run_all_agent_cases() -> None:
    # 必须先检查独立 Evaluation 环境
    _check_environment()

    dataset = json.loads(
        DATASET.read_text(encoding="utf-8")
    )

    # 筛选全部 Agent Cases
    agent_cases = [
        case for case in dataset["cases"]
        if case["case_type"] == "agent"
    ]

    _require(
        len(agent_cases) == 8,
        "Dataset V1 应包含 8 条 Agent Case。"
    )

    # 环境检查通过后才能导入业务模块
    from knowledge_pilot.config import SYSTEM_PROMPT
    from knowledge_pilot.llm.ollama_client import chat_with_ollama
    from knowledge_pilot.tools.registry import TOOL_REGISTRY
    from knowledge_pilot.evaluation.agent_runner import (
        run_agent_evaluation,
    )

    registered_tools = set(TOOL_REGISTRY.keys())

    results = run_agent_evaluation(
        cases=agent_cases,
        agent_fn=chat_with_ollama,
        registered_tools=registered_tools,
        system_prompt=SYSTEM_PROMPT,
    )

    _require(
        len(results) == 8,
        "Agent 评测结果数量不符合预期。"
    )

    report = {
        "dataset_version": dataset["dataset_version"],
        "agent_case_count": len(results),
        "registered_tools": sorted(registered_tools),
        "cases": results,
    }

    print(json.dumps(report, ensure_ascii=False, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)

    parser.add_argument(
        "--check-env",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument("--run-one", metavar="CASE_ID")
    parser.add_argument(
        "--execute-one",
        metavar="CASE_ID",
        help=argparse.SUPPRESS,
    )
    parser.add_argument("--k", type=int, default=3)
    parser.add_argument("--run-all", action="store_true")

    parser.add_argument(
        "--execute-all",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument("--run-agent-one", metavar="CASE_ID")
    parser.add_argument(
        "--run-agent-all",
        action="store_true",
    )

    parser.add_argument(
        "--execute-agent-all",
        action="store_true",
        help=argparse.SUPPRESS,
    )

    parser.add_argument(
        "--execute-agent-one",
        metavar="CASE_ID",
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args()


    # 子进程：只检查环境
    if args.check_env:
        try:
            details = _check_environment()
        except (OSError, ValueError, KeyError) as error:
            parser.error(str(error))

        print(json.dumps(details, ensure_ascii=False, indent=2))
        return 0

    # 子进程：执行单条真实评测
    if args.execute_one is not None:
        _run_one_case(args.execute_one, args.k)
        return 0
    if args.execute_agent_all:
        _run_all_agent_cases()
        return 0
    if args.execute_all:
        _run_all_cases(args.k)
        return 0
    if args.execute_agent_one is not None:
        _run_one_agent_case(args.execute_agent_one)
        return 0

    # 父进程：准备独立环境
    if not SRC.is_dir() or not RUNTIME.is_dir():
        parser.error("项目 src 或 Evaluation runtime 不存在。")

    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(SRC)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["ANONYMIZED_TELEMETRY"] = "False"

    command = [
        sys.executable,
        "-B",
        str(Path(__file__).resolve()),
    ]

    if args.run_one is not None:
        command.extend([
            "--execute-one",
            args.run_one,
            "--k",
            str(args.k),
        ])

    elif args.run_all:
        command.extend([
            "--execute-all",
            "--k",
            str(args.k),
        ])
    elif args.run_agent_one is not None:
        command.extend([
            "--execute-agent-one",
            args.run_agent_one,
        ])

    elif args.run_agent_all:
        command.append("--execute-agent-all")

    else:
        command.append("--check-env")

    return subprocess.run(
        command,
        cwd=RUNTIME,
        env=environment,
        check=False,
    ).returncode



if __name__ == "__main__":
    raise SystemExit(main())
