"""Hit@K / Recall@K 的行为契约；指标尚未实现时应保持红灯。"""


import unittest

from knowledge_pilot.evaluation.rag_metrics import (
    hit_at_k,
    recall_at_k,
    reciprocal_rank_at_k,
    mean_reciprocal_rank,
    fact_coverage_at_k,
    evidence_sufficient_at_k,
)



RAG_0 = ("eval_rag", 0)
RAG_1 = ("eval_rag", 1)
AGENT_0 = ("eval_agent", 0)


class HitAtKTests(unittest.TestCase):
    def test_negative_k(self):
        with self.assertRaises(ValueError):
            hit_at_k(
                [("eval_rag", 0)],
                {("eval_rag", 0)},
                k=-1
            )
    def test_hit_at_last_position_within_k(self):
        self.assertEqual(hit_at_k([AGENT_0, RAG_0], {RAG_0}, k=2), 1)

    def test_no_relevant_chunk_retrieved(self):
        self.assertEqual(hit_at_k([RAG_1], {RAG_0}, k=1), 0)

    def test_hit_after_k_is_ignored(self):
        self.assertEqual(hit_at_k([AGENT_0, RAG_0], {RAG_0}, k=1), 0)

    def test_duplicate_hits_still_return_one(self):
        self.assertEqual(hit_at_k([RAG_0, RAG_0], {RAG_0}, k=2), 1)

    def test_duplicate_results_still_occupy_top_k_positions(self):
        self.assertEqual(
            hit_at_k([AGENT_0, AGENT_0, RAG_0], {RAG_0}, k=2),
            0,
        )

    def test_duplicate_relevant_chunks_do_not_change_hit(self):
        self.assertEqual(hit_at_k([RAG_0], [RAG_0, RAG_0], k=1), 1)

    def test_same_index_in_another_document_is_not_a_hit(self):
        self.assertEqual(hit_at_k([AGENT_0], {RAG_0}, k=1), 0)

    def test_empty_retrieval_with_nonempty_relevant_returns_zero(self):
        self.assertEqual(hit_at_k([], {RAG_0}, k=3), 0)

    def test_empty_relevant_returns_none(self):
        self.assertIsNone(hit_at_k([RAG_0], set(), k=1))

    def test_zero_k_with_nonempty_relevant_returns_zero(self):
        self.assertEqual(hit_at_k([RAG_0], {RAG_0}, k=0), 0)

    def test_empty_relevant_takes_priority_over_zero_k(self):
        self.assertIsNone(hit_at_k([RAG_0], set(), k=0))


class RecallAtKTests(unittest.TestCase):
    def test_negative_k(self):
        with self.assertRaises(ValueError):
            recall_at_k(
                [("eval_rag", 0)],
                {("eval_rag", 0)},
                k=-1
            )
    def test_partial_recall_at_last_position_within_k(self):
        self.assertEqual(
            recall_at_k([AGENT_0, RAG_0], {RAG_0, RAG_1}, k=2),
            0.5,
        )

    def test_all_relevant_chunks_retrieved_returns_one(self):
        self.assertEqual(
            recall_at_k([RAG_0, RAG_1], {RAG_0, RAG_1}, k=2),
            1.0,
        )

    def test_no_relevant_chunk_retrieved(self):
        self.assertEqual(recall_at_k([RAG_1], {RAG_0}, k=1), 0.0)

    def test_hit_after_k_is_ignored(self):
        self.assertEqual(
            recall_at_k([AGENT_0, RAG_0], {RAG_0, RAG_1}, k=1),
            0.0,
        )

    def test_duplicate_results_count_once_and_occupy_top_k_positions(self):
        self.assertEqual(
            recall_at_k([RAG_0, RAG_0, RAG_1], {RAG_0, RAG_1}, k=2),
            0.5,
        )

    def test_duplicate_relevant_chunks_count_once_in_denominator(self):
        self.assertEqual(
            recall_at_k([RAG_0], [RAG_0, RAG_0, RAG_1], k=1),
            0.5,
        )

    def test_same_index_in_another_document_is_not_relevant(self):
        self.assertEqual(recall_at_k([AGENT_0], {RAG_0}, k=1), 0.0)

    def test_empty_retrieval_with_nonempty_relevant_returns_zero(self):
        self.assertEqual(recall_at_k([], {RAG_0}, k=3), 0.0)

    def test_empty_relevant_returns_none(self):
        self.assertIsNone(recall_at_k([RAG_0], set(), k=1))

    def test_zero_k_with_nonempty_relevant_returns_zero(self):
        self.assertEqual(recall_at_k([RAG_0], {RAG_0}, k=0), 0.0)

    def test_empty_relevant_takes_priority_over_zero_k(self):
        self.assertIsNone(recall_at_k([RAG_0], set(), k=0))

class ReciprocalRankAtKTests(unittest.TestCase):
    def test_negative_k(self):
        with self.assertRaises(ValueError):
            reciprocal_rank_at_k(
                [("eval_rag", 0)],
                {("eval_rag", 0)},
                k=-1
            )

    def test_first_and_second_rank(self):
        relevant = {("eval_rag", 1)}

        retrieved = [
            ("eval_tools", 0),
            ("eval_rag", 1)
        ]

        self.assertEqual(
            reciprocal_rank_at_k(retrieved, relevant, k=1),
            0.0
        )

        self.assertEqual(
            reciprocal_rank_at_k(retrieved, relevant, k=2),
            0.5
        )

    def test_empty_relevant(self):
        self.assertIsNone(
            reciprocal_rank_at_k(
                [("eval_rag", 1)],
                set(),
                k=1
            )
        )

    def test_first_rank_hit(self):
        self.assertEqual(
            reciprocal_rank_at_k(
                [("eval_rag", 1)],
                {("eval_rag", 1)},
                k=1
            ),
            1.0
        )


class MeanReciprocalRankTests(unittest.TestCase):

    def test_normal_scores(self):
        result = mean_reciprocal_rank([1.0, 0.5, 0.0])
        self.assertEqual(result, 0.5)

    def test_exclude_none(self):
        result = mean_reciprocal_rank([None, 0.0, 0.5])
        self.assertEqual(result, 0.25)

    def test_all_none(self):
        result = mean_reciprocal_rank([None, None])
        self.assertIsNone(result)

    def test_empty_scores(self):
        result = mean_reciprocal_rank([])
        self.assertIsNone(result)


class FactCoverageAtKTests(unittest.TestCase):
    def test_negative_k(self):
        with self.assertRaises(ValueError):
            fact_coverage_at_k(
                [("eval_agent", 0)],
                {"A"},
                {("eval_agent", 0): {"A"}},
                k=-1
            )

    def test_partial_coverage(self):
        retrieved = [
            ("eval_agent", 0),
            ("eval_agent", 1),
            ("eval_tools", 0)
        ]

        required = {"A", "B", "C"}

        coverage = {
            ("eval_agent", 0): {"A"},
            ("eval_agent", 1): {"A", "B"},
            ("eval_tools", 0): {"A"}
        }

        result = fact_coverage_at_k(
            retrieved, required, coverage, k=3
        )

        self.assertAlmostEqual(result, 2 / 3)

    def test_full_coverage(self):
        retrieved = [("eval_agent", 0)]
        required = {"A", "B"}

        coverage = {
            ("eval_agent", 0): {"A", "B"}
        }

        self.assertEqual(
            fact_coverage_at_k(retrieved, required, coverage, 1),
            1.0
        )

    def test_no_required_facts(self):
        self.assertIsNone(
            fact_coverage_at_k([], set(), {}, 3)
        )

    def test_k_zero(self):
        self.assertEqual(
            fact_coverage_at_k(
                [("eval_agent", 0)],
                {"A"},
                {("eval_agent", 0): {"A"}},
                0
            ),
            0.0
        )

    def test_unknown_chunk(self):
        self.assertEqual(
            fact_coverage_at_k(
                [("eval_tools", 0)],
                {"A"},
                {},
                1
            ),
            0.0
        )


class EvidenceSufficientAtKTests(unittest.TestCase):
    def test_negative_k(self):
        with self.assertRaises(ValueError):
            evidence_sufficient_at_k(
                [("eval_agent", 0)],
                {"A"},
                {("eval_agent", 0): {"A"}},
                k=-1
            )

    def test_full_evidence(self):
        retrieved = [
            ("eval_agent", 0),
            ("eval_agent", 1)
        ]
        required = {"A", "B"}
        coverage = {
            ("eval_agent", 0): {"A"},
            ("eval_agent", 1): {"B"}
        }

        result = evidence_sufficient_at_k(
            retrieved, required, coverage, k=2
        )
        self.assertEqual(result, 1)

    def test_partial_evidence(self):
        retrieved = [("eval_agent", 0)]
        required = {"A", "B"}
        coverage = {
            ("eval_agent", 0): {"A"}
        }

        result = evidence_sufficient_at_k(
            retrieved, required, coverage, k=1
        )
        self.assertEqual(result, 0)

    def test_no_required_facts(self):
        self.assertIsNone(
            evidence_sufficient_at_k([], set(), {}, 3)
        )

    def test_k_zero(self):
        self.assertEqual(
            evidence_sufficient_at_k(
                [("eval_agent", 0)],
                {"A"},
                {("eval_agent", 0): {"A"}},
                0
            ),
            0
        )

    def test_duplicate_evidence_not_enough(self):
        retrieved = [
            ("eval_agent", 0),
            ("eval_agent", 0)
        ]
        required = {"A", "B"}
        coverage = {
            ("eval_agent", 0): {"A"}
        }

        result = evidence_sufficient_at_k(
            retrieved, required, coverage, k=2
        )
        self.assertEqual(result, 0)

if __name__ == "__main__":
    unittest.main()
