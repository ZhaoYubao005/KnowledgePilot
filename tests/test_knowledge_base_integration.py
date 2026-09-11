import os
import unittest


@unittest.skipUnless(
    os.environ.get("KNOWLEDGE_PILOT_RUN_INTEGRATION") == "1",
    "set KNOWLEDGE_PILOT_RUN_INTEGRATION=1 to use Ollama and Chroma",
)
class KnowledgeBaseIntegrationTests(unittest.TestCase):
    def test_search_returns_three_content_source_results(self):
        from knowledge_pilot.tools.knowledge_base_tool import (
            collection,
            search_knowledge_base,
        )

        results = search_knowledge_base(
            query="什么是机器学习",
            top_k=3,
        )

        self.assertEqual(collection.name, "knowledge_pilot_docs")
        self.assertEqual(collection.count(), 30)
        self.assertIsInstance(results, list)
        self.assertEqual(len(results), 3)
        for result in results:
            self.assertEqual(set(result), {"content", "source"})
            self.assertTrue(result["content"])
            self.assertIsNotNone(result["source"])


if __name__ == "__main__":
    unittest.main()
