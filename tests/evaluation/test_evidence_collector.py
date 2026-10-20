"""Evidence Collector 的固定样例与验收测试。

所有样例均为合成数据，不读取冻结 Dataset、Corpus、历史报告或数据库。
五项契约测试已启用。

测试计划：
1. 精确输出五字段；保留输入顺序，rank 从 1 开始。
2. 空输入返回空列表。
3. 原始 similarity 原样保留，包括负值。
4. 重复 Chunk 身份仍保留各自记录及排名。
5. 输入列表和嵌套 metadata 不变。

仅运行本文件；在项目根设置绝对 PYTHONPATH=项目的 src 目录，
使用 python -B -m unittest discover -s tests/evaluation
-p test_evidence_collector.py -v（以上命令接为一行）。
"""

from copy import deepcopy
import unittest

from knowledge_pilot.evaluation.evidence_collector import collect_candidates


SAMPLE_RESULTS = [
    ("示例片段 A", 0.42, {
        "document_id": "sample_a", "chunk_index": 3, "source": "fixture_a.txt",
    }),
    ("示例片段 B", 0.91, {
        "document_id": "sample_b", "chunk_index": 0, "source": "fixture_b.txt",
    }),
]

EXPECTED_CANDIDATES = [
    {
        "document_id": "sample_a",
        "chunk_index": 3,
        "rank": 1,
        "text": "示例片段 A",
        "similarity": 0.42,
    },
    {
        "document_id": "sample_b",
        "chunk_index": 0,
        "rank": 2,
        "text": "示例片段 B",
        "similarity": 0.91,
    },
]


class EvidenceCollectorTests(unittest.TestCase):
    def test_exact_fields_and_input_order(self):
        candidates = collect_candidates(deepcopy(SAMPLE_RESULTS))

        self.assertEqual(candidates, EXPECTED_CANDIDATES)

    def test_empty_results(self):
        self.assertEqual(collect_candidates([]), [])

    def test_negative_similarity_is_preserved(self):
        results = [("负相似度样例", -0.25, {
            "document_id": "sample_negative", "chunk_index": 0,
        })]

        self.assertEqual(collect_candidates(results), [{
            "document_id": "sample_negative",
            "chunk_index": 0,
            "rank": 1,
            "text": "负相似度样例",
            "similarity": -0.25,
        }])

    def test_duplicate_chunk_identity_is_preserved(self):
        results = [
            ("第一次出现", 0.7, {"document_id": "sample_a", "chunk_index": 3}),
            ("第二次出现", 0.6, {"document_id": "sample_a", "chunk_index": 3}),
        ]

        self.assertEqual(collect_candidates(results), [
            {
                "document_id": "sample_a", "chunk_index": 3, "rank": 1,
                "text": "第一次出现", "similarity": 0.7,
            },
            {
                "document_id": "sample_a", "chunk_index": 3, "rank": 2,
                "text": "第二次出现", "similarity": 0.6,
            },
        ])

    def test_input_and_metadata_are_unchanged(self):
        results = deepcopy(SAMPLE_RESULTS)
        before = deepcopy(results)

        collect_candidates(results)

        self.assertEqual(results, before)
