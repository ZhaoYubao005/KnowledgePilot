"""Service layer for the KnowledgePilot V1.1 API."""
from knowledge_pilot.config import SYSTEM_PROMPT
from knowledge_pilot.llm.ollama_client import chat_with_ollama
from knowledge_pilot.vector_store.chroma_store import (
    collection,
    ingest_document,
    delete_document,
    update_document,
)
import uuid
from pathlib import Path

def chat_service(query: str, max_steps: int = 5):
    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT,
        },
        {
            "role": "user",
            "content": query,
        },
    ]

    return chat_with_ollama(messages, max_steps=max_steps)




def create_document(filename: str, content: bytes):
    if not filename.lower().endswith(".txt"):
        raise ValueError("only txt files are supported")

    if not content:
        raise ValueError("file cannot be empty")

    text = content.decode("utf-8")

    if not text.strip():
        raise ValueError("file content cannot be blank")

    document_id = str(uuid.uuid4())

    safe_filename = Path(filename).name

    document_dir = Path("data/raw_documents") / document_id
    document_dir.mkdir(parents=True, exist_ok=True)

    file_path = document_dir / safe_filename
    file_path.write_bytes(content)
    try:
        ingest_document(
            str(file_path),
            document_id,
            collection,
        )
    except Exception:
        if file_path.exists():
            file_path.unlink()

        if document_dir.exists():
            document_dir.rmdir()

        raise

    result = collection.get(
        where={
            "document_id": document_id
        }
    )

    chunk_count = len(result["ids"])

    return {
        "document_id": document_id,
        "source": safe_filename,
        "chunk_count": chunk_count,
    }
def list_documents():
    result = collection.get(
        include=["metadatas"],
    )

    documents = {}

    for metadata in result["metadatas"] or []:
        document_id = metadata["document_id"]

        if document_id not in documents:
            documents[document_id] = {
                "document_id": document_id,
                "source": Path(metadata["source"]).name,
                "chunk_count": 0,
            }

        documents[document_id]["chunk_count"] += 1

    return list(documents.values())
def delete_document_service(document_id: str):
    result = collection.get(
        where={
            "document_id": document_id
        },
        include=["metadatas"],
    )

    if not result["metadatas"]:
        raise KeyError(document_id)

    source = result["metadatas"][0]["source"]

    delete_document(
        document_id,
        collection,
    )

    file_path = Path(source)
    raw_root = Path("data/raw_documents")

    if file_path.is_relative_to(raw_root):
        if file_path.exists():
            file_path.unlink()

        document_dir = file_path.parent

        if document_dir.exists():
            document_dir.rmdir()

    return {
        "document_id": document_id,
        "status": "deleted",
    }
def update_document_service(
    document_id: str,
    filename: str,
    content: bytes,
):
    result = collection.get(
        where={
            "document_id": document_id
        },
        include=["metadatas"],
    )

    if not result["metadatas"]:
        raise KeyError(document_id)

    old_source = result["metadatas"][0]["source"]
    if not filename.lower().endswith(".txt"):
        raise ValueError("only txt files are supported")

    if not content:
        raise ValueError("file cannot be empty")

    text = content.decode("utf-8")

    if not text.strip():
        raise ValueError("file content cannot be blank")
    safe_filename = Path(filename).name
    raw_root = Path("data/raw_documents")

    document_dir = raw_root / document_id
    document_dir.mkdir(parents=True, exist_ok=True)

    new_file_path = document_dir / safe_filename
    old_file_path = Path(old_source)

    old_raw_content = None

    if old_file_path.is_relative_to(raw_root) and old_file_path.exists():
        old_raw_content = old_file_path.read_bytes()
    new_file_path.write_bytes(content)

    try:
        update_document(
            str(new_file_path),
            document_id,
            collection,
        )

    except Exception:
        if new_file_path == old_file_path and old_raw_content is not None:
            old_file_path.write_bytes(old_raw_content)

        elif new_file_path.exists():
            new_file_path.unlink()

        raise
    if (
            old_file_path.is_relative_to(raw_root)
            and old_file_path != new_file_path
            and old_file_path.exists()
    ):
        old_file_path.unlink()

    result = collection.get(
        where={
            "document_id": document_id
        }
    )

    chunk_count = len(result["ids"])

    return {
        "document_id": document_id,
        "source": safe_filename,
        "chunk_count": chunk_count,
    }
