"""Unit and integration tests for the V1.3 BM25 retrieval modules."""

import math
import unittest

from knowledge_pilot.evaluation.bm25 import BM25Index, tokenize
from knowledge_pilot.evaluation.bm25_baseline import run_bm25_cases, summarize_bm25_cases


def chunk(document_id, chunk_index, text):
    return {"document_id": document_id, "chunk_index": chunk_index, "text": text,
            "source": f"{document_id}.txt"}


def case(case_id="rag_001", relevant_index=0):
    return {"id": case_id, "case_type": "retrieval", "query": "知识 BM25",
            "relevant_chunks": [{"document_id": "doc", "chunk_index": relevant_index}]}


class TokenizerTests(unittest.TestCase):
    def test_preserves_python_identifier_api_path_and_hyphenated_model(self):
        tokens = tokenize("search_knowledge_base /documents/{document_id} BM25 RRF bge-m3")
        self.assertIn("search_knowledge_base", tokens)
        self.assertIn("/documents/{document_id}", tokens)
        self.assertIn("bm25", tokens)
        self.assertIn("rrf", tokens)
        self.assertIn("bge-m3", tokens)

    def test_cjk_uses_unigrams_and_bigrams_consistently(self):
        self.assertEqual(tokenize("知识"), ["知", "识", "知识"])
        self.assertEqual(tokenize("知识"), tokenize("  知识，"))

    def test_empty_and_punctuation_only_text_have_no_tokens(self):
        self.assertEqual(tokenize(" \t，。!?"), [])


class BM25IndexTests(unittest.TestCase):
    def test_idf_uses_documented_okapi_smoothing(self):
        index = BM25Index([chunk("a", 0, "term"), chunk("b", 0, "other")])
        expected = math.log(1 + (2 - 1 + 0.5) / (1 + 0.5))
        self.assertAlmostEqual(index.idf["term"], expected)

    def test_tf_saturation_and_length_normalization(self):
        index = BM25Index([chunk("short", 0, "x"), chunk("long", 0, "x x x x")])
        scores = {hit["document_id"]: hit["score"] for hit in index.search("x", 2)}
        self.assertGreater(scores["long"], scores["short"])
        self.assertLess(scores["long"], scores["short"] * 4)

    def test_repeated_query_terms_accumulate_scores(self):
        index = BM25Index([chunk("doc", 0, "term")])
        once = index.search("term", 1)[0]["score"]
        twice = index.search("term term", 1)[0]["score"]
        self.assertAlmostEqual(twice, once * 2)

    def test_zero_match_returns_no_arbitrary_candidates(self):
        index = BM25Index([chunk("doc", 0, "known")])
        self.assertEqual(index.search("missing", 3), [])
        self.assertEqual(index.search("", 3), [])

    def test_score_ties_use_document_id_then_chunk_index(self):
        index = BM25Index([chunk("z", 2, "same"), chunk("a", 4, "same"), chunk("a", 1, "same")])
        hits = index.search("same", 3)
        self.assertEqual([(hit["document_id"], hit["chunk_index"]) for hit in hits],
                         [("a", 1), ("a", 4), ("z", 2)])

    def test_chunk_identity_text_and_score_semantics_are_preserved(self):
        index = BM25Index([chunk("doc", 7, "BM25 原文")])
        hit = index.search("BM25", 1)[0]
        self.assertEqual((hit["document_id"], hit["chunk_index"], hit["text"]),
                         ("doc", 7, "BM25 原文"))
        self.assertEqual(hit["rank"], 1)
        self.assertEqual(hit["score_type"], "bm25_okapi")
        self.assertNotIn("similarity", hit)


class BM25BaselineTests(unittest.TestCase):
    def test_success_and_zero_hit_cases_are_scored_without_fake_candidates(self):
        index = BM25Index([chunk("doc", 0, "知识 BM25")])
        cases = [case("hit", 0), {**case("miss", 1), "query": "不存在词xyz"}]
        records = run_bm25_cases(cases, index.search, k=3)
        self.assertEqual([record["status"] for record in records], ["success", "success"])
        self.assertEqual(records[0]["metrics"], {"hit": 1, "recall": 1.0, "rr": 1.0})
        self.assertEqual(records[1]["candidates"], [])
        self.assertEqual(records[1]["metrics"], {"hit": 0, "recall": 0.0, "rr": 0.0})

    def test_failures_and_summary_denominators_are_explicit(self):
        def search(query, k):
            if query == "bad":
                raise RuntimeError("failure")
            return []
        cases = [{**case("bad"), "query": "bad"}, {**case("ok"), "query": "none"}]
        records = run_bm25_cases(cases, search)
        summary = summarize_bm25_cases(records)
        self.assertEqual(summary["case_counts"], {"total": 2, "success": 1,
                         "retrieval_failed": 1, "scoring_failed": 0})
        self.assertEqual(summary["metric_denominators"], {"hit_rate": 1,
                         "mean_recall": 1, "mrr": 1})


if __name__ == "__main__":
    unittest.main()
