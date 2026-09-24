"""V1.1 API request and response model definitions."""
from pydantic import BaseModel, Field, field_validator


class ChatRequest(BaseModel):
    query:str=Field(min_length=1)
    max_steps:int=Field(default=5,ge=1)

    @field_validator("query")
    @classmethod
    def validate_query(cls,value:str):
        value = value.strip()
        if not value:
            raise ValueError("query cannot be empty")
        return value
class ChatResponse(BaseModel):
    answer: str
    trace: list
    stop_reason: str
class DocumentResponse(BaseModel):
    document_id: str
    source: str
    chunk_count: int
class DeleteDocumentResponse(BaseModel):
    document_id: str
    status: str