"""Contract tests for the V1.1 HTTP routes, without external services."""

import importlib
import sys
import types
import unittest
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
from requests.exceptions import ConnectionError as RequestsConnectionError
from requests.exceptions import JSONDecodeError as RequestsJSONDecodeError


SERVICE_NAMES = (
    "chat_service",
    "create_document",
    "list_documents",
    "update_document_service",
    "delete_document_service",
)
DOCUMENT_ID = "test-document-id"
DOCUMENT_RESULT = {
    "document_id": DOCUMENT_ID,
    "source": "example.txt",
    "chunk_count": 1,
}
CHAT_RESULT = {
    "answer": "Test answer",
    "trace": [],
    "stop_reason": "completed",
}
MISSING = object()


def invalid_json_error():
    return RequestsJSONDecodeError("Invalid JSON", "not-json", 0)


def invalid_utf8_error():
    return UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte")


class ApiContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        # app.py imports these names directly. Stub services *before* importing
        # app.py so its real module cannot initialize the Chroma collection.
        stub_services = types.ModuleType("knowledge_pilot.api.services")
        for name in SERVICE_NAMES:
            setattr(stub_services, name, Mock(name=name))

        cls.services_patch = patch.dict(
            sys.modules,
            {"knowledge_pilot.api.services": stub_services},
        )
        cls.services_patch.start()
        cls.addClassCleanup(cls.services_patch.stop)

        cls.api_package = importlib.import_module("knowledge_pilot.api")
        cls.previous_app_attribute = vars(cls.api_package).get("app", MISSING)
        cls.previous_app = sys.modules.pop("knowledge_pilot.api.app", None)
        cls.addClassCleanup(cls.restore_app_module)
        cls.app_module = importlib.import_module("knowledge_pilot.api.app")

    @classmethod
    def restore_app_module(cls):
        sys.modules.pop("knowledge_pilot.api.app", None)
        if cls.previous_app is not None:
            sys.modules["knowledge_pilot.api.app"] = cls.previous_app
        if cls.previous_app_attribute is MISSING:
            delattr(cls.api_package, "app")
        else:
            cls.api_package.app = cls.previous_app_attribute

    def setUp(self):
        self.client = TestClient(self.app_module.app)
        self.addCleanup(self.client.close)

    def upload(self):
        return self.client.post(
            "/documents",
            files={"file": ("example.txt", b"Test document", "text/plain")},
        )

    def update(self):
        return self.client.put(
            f"/documents/{DOCUMENT_ID}",
            files={"file": ("example.txt", b"Updated document", "text/plain")},
        )

    def test_health_returns_200(self):
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_chat_success_returns_200(self):
        with patch(
            "knowledge_pilot.api.app.chat_service", return_value=CHAT_RESULT
        ) as service:
            response = self.client.post(
                "/chat", json={"query": "  hello  ", "max_steps": 3}
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), CHAT_RESULT)
        service.assert_called_once_with(query="hello", max_steps=3)

    def test_chat_invalid_query_returns_422(self):
        with patch("knowledge_pilot.api.app.chat_service") as service:
            response = self.client.post("/chat", json={"query": "   "})

        self.assertEqual(response.status_code, 422)
        service.assert_not_called()

    def test_chat_connection_error_returns_503(self):
        with patch(
            "knowledge_pilot.api.app.chat_service",
            side_effect=RequestsConnectionError("Ollama unavailable"),
        ):
            response = self.client.post("/chat", json={"query": "hello"})

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"], "LLM service is unavailable")

    def test_chat_json_decode_error_returns_502(self):
        with patch(
            "knowledge_pilot.api.app.chat_service", side_effect=invalid_json_error()
        ):
            response = self.client.post("/chat", json={"query": "hello"})

        self.assertEqual(response.status_code, 502)
        self.assertEqual(
            response.json()["detail"], "LLM service returned an invalid response"
        )

    def test_create_document_success_returns_201(self):
        with patch(
            "knowledge_pilot.api.app.create_document", return_value=DOCUMENT_RESULT
        ) as service:
            response = self.upload()

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json(), DOCUMENT_RESULT)
        service.assert_called_once_with(
            filename="example.txt", content=b"Test document"
        )

    def test_create_document_value_error_returns_400(self):
        with patch(
            "knowledge_pilot.api.app.create_document",
            side_effect=ValueError("invalid document"),
        ):
            response = self.upload()

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "invalid document")

    def test_create_document_unicode_error_returns_400(self):
        with patch(
            "knowledge_pilot.api.app.create_document",
            side_effect=invalid_utf8_error(),
        ):
            response = self.upload()

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "file must be UTF-8 encoded")

    def test_create_document_json_decode_error_returns_502(self):
        with patch(
            "knowledge_pilot.api.app.create_document",
            side_effect=invalid_json_error(),
        ):
            response = self.upload()

        self.assertEqual(response.status_code, 502)
        self.assertEqual(
            response.json()["detail"],
            "embedding service returned an invalid response",
        )

    def test_create_document_connection_error_returns_503(self):
        with patch(
            "knowledge_pilot.api.app.create_document",
            side_effect=RequestsConnectionError("Embedding unavailable"),
        ):
            response = self.upload()

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json()["detail"], "embedding service is unavailable"
        )

    def test_list_documents_success_returns_document_response_list(self):
        documents = [DOCUMENT_RESULT, {**DOCUMENT_RESULT, "document_id": "doc-2"}]
        service_documents = [
            {**document, "internal_note": "not part of DocumentResponse"}
            for document in documents
        ]
        with patch(
            "knowledge_pilot.api.app.list_documents", return_value=service_documents
        ) as service:
            response = self.client.get("/documents")

        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.json(), list)
        self.assertEqual(response.json(), documents)
        service.assert_called_once_with()

    def test_update_document_success_returns_200(self):
        with patch(
            "knowledge_pilot.api.app.update_document_service",
            return_value=DOCUMENT_RESULT,
        ) as service:
            response = self.update()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), DOCUMENT_RESULT)
        service.assert_called_once_with(
            document_id=DOCUMENT_ID,
            filename="example.txt",
            content=b"Updated document",
        )

    def test_update_document_key_error_returns_404(self):
        with patch(
            "knowledge_pilot.api.app.update_document_service",
            side_effect=KeyError(DOCUMENT_ID),
        ):
            response = self.update()

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "document not found")

    def test_update_document_value_error_returns_400(self):
        with patch(
            "knowledge_pilot.api.app.update_document_service",
            side_effect=ValueError("invalid document"),
        ):
            response = self.update()

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "invalid document")

    def test_update_document_unicode_error_returns_400(self):
        with patch(
            "knowledge_pilot.api.app.update_document_service",
            side_effect=invalid_utf8_error(),
        ):
            response = self.update()

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "file must be UTF-8 encoded")

    def test_update_document_json_decode_error_returns_502(self):
        with patch(
            "knowledge_pilot.api.app.update_document_service",
            side_effect=invalid_json_error(),
        ):
            response = self.update()

        self.assertEqual(response.status_code, 502)
        self.assertEqual(
            response.json()["detail"],
            "embedding service returned an invalid response",
        )

    def test_update_document_connection_error_returns_503(self):
        with patch(
            "knowledge_pilot.api.app.update_document_service",
            side_effect=RequestsConnectionError("Embedding unavailable"),
        ):
            response = self.update()

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json()["detail"], "embedding service is unavailable"
        )

    def test_delete_document_success_returns_200(self):
        result = {"document_id": DOCUMENT_ID, "status": "deleted"}
        with patch(
            "knowledge_pilot.api.app.delete_document_service", return_value=result
        ) as service:
            response = self.client.delete(f"/documents/{DOCUMENT_ID}")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), result)
        service.assert_called_once_with(DOCUMENT_ID)

    def test_delete_document_key_error_returns_404(self):
        with patch(
            "knowledge_pilot.api.app.delete_document_service",
            side_effect=KeyError(DOCUMENT_ID),
        ):
            response = self.client.delete(f"/documents/{DOCUMENT_ID}")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "document not found")


if __name__ == "__main__":
    unittest.main()
