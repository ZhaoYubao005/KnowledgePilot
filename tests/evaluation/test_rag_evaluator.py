import json
from pathlib import Path
import unittest

from knowledge_pilot.evaluation.rag_evaluator import (
    evaluate_retrieval_case,
)


class RAGEvaluatorTests(unittest.TestCase):

    def test_second_rank_hit(self):
        case = {
            "id": "rag_demo",
            "relevant_chunks": [
                {"document_id": "eval_rag", "chunk_index": 2}
            ]
        }

        results = [
            ("文本A", 0.91, {
                "document_id": "eval_tools",
                "chunk_index": 0
            }),
            ("文本B", 0.85, {
                "document_id": "eval_rag",
                "chunk_index": 2
            })
        ]

        result = evaluate_retrieval_case(case, results, k=2)

        self.assertEqual(result["case_id"], "rag_demo")
        self.assertEqual(result["hit"], 1)
        self.assertEqual(result["recall"], 1.0)
        self.assertEqual(result["rr"], 0.5)

    def test_first_rank_no_hit(self):
        case = {
            "id": "rag_demo",
            "relevant_chunks": [
                {"document_id": "eval_rag", "chunk_index": 2}
            ]
        }

        results = [
            ("文本A", 0.91, {
                "document_id": "eval_tools",
                "chunk_index": 0
            }),
            ("文本B", 0.85, {
                "document_id": "eval_rag",
                "chunk_index": 2
            })
        ]

        result = evaluate_retrieval_case(case, results, k=1)

        self.assertEqual(result["hit"], 0)
        self.assertEqual(result["recall"], 0.0)
        self.assertEqual(result["rr"], 0.0)

    def test_rag_008_multi_chunk_scoring(self):
            # 读取真实冻结 Dataset
            dataset_path = (
                    Path(__file__).resolve().parents[2]
                    / "data/evaluation/cases_v1.json"
            )

            with dataset_path.open(encoding="utf-8") as f:
                dataset = json.load(f)

            case = next(
                c for c in dataset["cases"]
                if c["id"] == "rag_008"
            )

            # 模拟检索结果：两个 Chunk 分别提供不同事实
            results = [
                ("文本A", 0.91, {
                    "document_id": "eval_tools",
                    "chunk_index": 0
                }),
                ("文本B", 0.85, {
                    "document_id": "eval_agent",
                    "chunk_index": 1
                })
            ]

            # 只检索第一个 Chunk：覆盖 1/3 的事实
            result_k1 = evaluate_retrieval_case(case, results, k=1)

            self.assertAlmostEqual(result_k1["fact_coverage"], 1 / 3)
            self.assertEqual(result_k1["evidence_sufficient"], 0)

            # 检索两个 Chunk：覆盖全部 3 个事实
            result_k2 = evaluate_retrieval_case(case, results, k=2)

            self.assertEqual(result_k2["fact_coverage"], 1.0)
            self.assertEqual(result_k2["evidence_sufficient"], 1)
