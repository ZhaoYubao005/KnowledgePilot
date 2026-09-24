"""FastAPI routes for KnowledgePilot V1.1.

Routes use the API service layer to access the existing Agent and document
capabilities. Importing the service layer initializes the Chroma collection.
"""
from fastapi import FastAPI, UploadFile, File, HTTPException
from knowledge_pilot.api.schemas import (
    ChatRequest,
    ChatResponse,
    DocumentResponse,
    DeleteDocumentResponse,
)
from requests.exceptions import JSONDecodeError as RequestsJSONDecodeError
from knowledge_pilot.api.services import (
    chat_service,
    create_document,
    list_documents,
    delete_document_service,
    update_document_service,
)
from requests.exceptions import ConnectionError as RequestsConnectionError

app = FastAPI(version="1.1.0")

@app.get("/health")
def health():
    return {
        "status": "ok"
    }

@app.post(
    path="/chat",
    response_model=ChatResponse,
    responses={
        502: {"description": "LLM service returned an invalid response"},
        503: {"description": "LLM service unavailable"},
    },
)
def chat(request: ChatRequest):
    try:
        result = chat_service(
            query=request.query,
            max_steps=request.max_steps,
        )
    except RequestsJSONDecodeError:
        raise HTTPException(
            status_code=502,
            detail="LLM service returned an invalid response",
        )

    except RequestsConnectionError:
        raise HTTPException(
            status_code=503,
            detail="LLM service is unavailable",
        )

    return result
@app.post(
    path="/documents",
    response_model=DocumentResponse,
    status_code=201,
    responses={
        400: {"description": "Invalid document"},
        502: {"description": "Embedding service returned an invalid response"},
        503: {"description": "Embedding service unavailable"},
    },
)
def upload_document(file: UploadFile = File(...)):
    content = file.file.read()
    filename = file.filename or ""

    try:
        result = create_document(
            filename=filename,
            content=content,
        )

    except UnicodeDecodeError:
        raise HTTPException(
            status_code=400,
            detail="file must be UTF-8 encoded",
        )
    except RequestsJSONDecodeError:
        raise HTTPException(
            status_code=502,
            detail="embedding service returned an invalid response",
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )

    except RequestsConnectionError:
        raise HTTPException(
            status_code=503,
            detail="embedding service is unavailable",
        )

    return result
@app.get(
    "/documents",
    response_model=list[DocumentResponse],
)
def get_documents():
    documents = list_documents()

    return documents
@app.delete(
    "/documents/{document_id}",
    response_model=DeleteDocumentResponse,
    responses={
        404: {"description": "Document not found"},
    },
)
def remove_document(document_id: str):
    try:
        result = delete_document_service(document_id)

    except KeyError:
        raise HTTPException(
            status_code=404,
            detail="document not found",
        )

    return result
@app.put(
    "/documents/{document_id}",
    response_model=DocumentResponse,
    responses={
        400: {"description": "Invalid document"},
        404: {"description": "Document not found"},
        502: {"description": "Embedding service returned an invalid response"},
        503: {"description": "Embedding service unavailable"},
    },
)
def update_document_route(
    document_id: str,
    file: UploadFile = File(...),
):
    content = file.file.read()
    filename = file.filename or ""

    try:
        result = update_document_service(
            document_id=document_id,
            filename=filename,
            content=content,
        )

    except KeyError:
        raise HTTPException(
            status_code=404,
            detail="document not found",
        )

    except UnicodeDecodeError:
        raise HTTPException(
            status_code=400,
            detail="file must be UTF-8 encoded",
        )

    except RequestsJSONDecodeError:
        raise HTTPException(
            status_code=502,
            detail="embedding service returned an invalid response",
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        )

    except RequestsConnectionError:
        raise HTTPException(
            status_code=503,
            detail="embedding service is unavailable",
        )

    return result
