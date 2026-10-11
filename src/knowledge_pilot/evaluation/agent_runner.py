from knowledge_pilot.evaluation.agent_evaluator import (
    evaluate_agent_case,
)


def run_agent_evaluation(
    cases,
    agent_fn,
    registered_tools,
    system_prompt,
):
    results = []

    for case in cases:
        if case["case_type"] != "agent":
            continue

        # 每条 Case 独立创建 Messages
        messages = [
            {
                "role": "system",
                "content": system_prompt,
            },
            {
                "role": "user",
                "content": case["query"],
            },
        ]

        try:
            # 调用 Agent Loop
            agent_result = agent_fn(
                messages,
                max_steps=case["max_steps"]
            )

            # 调用 Agent Evaluator
            score = evaluate_agent_case(
                case,
                agent_result,
                registered_tools
            )

            # 保留答案和 Trace，供人工复核
            score["answer"] = agent_result.get("answer", "")
            score["trace"] = agent_result.get("trace", [])

            results.append(score)

        except Exception as error:
            results.append({
                "case_id": case["id"],
                "error": {
                    "type": type(error).__name__,
                    "message": str(error),
                },
            })

    return results
