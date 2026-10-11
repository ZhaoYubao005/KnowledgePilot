import time
from knowledge_pilot.evaluation.rag_evaluator import (
    evaluate_retrieval_case,
)



def run_rag_evaluation(cases, search_fn, k=3):
    results = []

    for case in cases:
        # 只评测 Retrieval Case
        if case["case_type"] != "retrieval":
            continue

        start = time.perf_counter()
        stage = "search"

        try:
            # Step 1：执行检索
            retrieved = search_fn(case["query"], k)

            latency_ms = (
                time.perf_counter() - start
            ) * 1000

            # Step 2：计算指标
            stage = "evaluation"

            score = evaluate_retrieval_case(
                case,
                retrieved,
                k,
            )

        except Exception as error:
            # 记录失败 Case，不伪造评分
            results.append({
                "case_id": case["id"],
                "error": {
                    "stage": stage,
                    "type": type(error).__name__,
                    "message": str(error),
                },
            })

            # 继续评测下一条
            continue

        # Step 3：正常评分结果
        score["latency_ms"] = latency_ms
        results.append(score)

    return results
