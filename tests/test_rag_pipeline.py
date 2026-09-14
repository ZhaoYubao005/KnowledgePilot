import importlib
import sys
import types
import unittest
from unittest.mock import Mock, patch


class RagPipelineTests(unittest.TestCase):
    def setUp(self):
        self.collection = object()
        self.search = Mock(
            return_value=[
                (
                    "机器学习是从数据中学习规律的方法。",
                    0.9,
                    {
                        "document_id": "machine_learning",
                        "source": "data/machine_learning.txt",
                    },
                )
            ]
        )
        self.chat_with_ollama = Mock(
            return_value={
                "answer": "机器学习可以从数据中学习规律。",
                "trace": [],
                "stop_reason": "completed",
            }
        )

        fake_chroma_store = types.ModuleType(
            "knowledge_pilot.vector_store.chroma_store"
        )
        fake_chroma_store.collection = self.collection
        fake_chroma_store.search = self.search

        fake_ollama_client = types.ModuleType(
            "knowledge_pilot.llm.ollama_client"
        )
        fake_ollama_client.chat_with_ollama = self.chat_with_ollama

        self.module_patch = patch.dict(
            sys.modules,
            {
                "knowledge_pilot.vector_store.chroma_store": (
                    fake_chroma_store
                ),
                "knowledge_pilot.llm.ollama_client": fake_ollama_client,
            },
        )
        self.module_patch.start()
        sys.modules.pop("knowledge_pilot.rag.pipeline", None)
        self.pipeline = importlib.import_module(
            "knowledge_pilot.rag.pipeline"
        )

    def tearDown(self):
        sys.modules.pop("knowledge_pilot.rag.pipeline", None)
        self.module_patch.stop()

    def test_answer_with_rag_returns_answer_text_from_agent_result(self):
        answer, sources = self.pipeline.answer_with_rag(
            query="什么是机器学习？",
            collection=self.collection,
        )

        self.assertEqual(answer, "机器学习可以从数据中学习规律。")
        self.assertIsInstance(answer, str)
        self.assertEqual(
            sources,
            [
                {
                    "document_id": "machine_learning",
                    "source": "data/machine_learning.txt",
                }
            ],
        )


if __name__ == "__main__":
    unittest.main()
