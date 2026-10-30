"""Local session capability API; opaque identifiers are not authentication."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from knowledge_pilot.memory import service
from knowledge_pilot.memory.store import SessionNotFound, SessionConflict

router = APIRouter()


class Turn(BaseModel):
    query: str
    answer: str


class SessionResponse(BaseModel):
    session_id: str
    revision: int
    turns: list[Turn]


def session_http(operation):
    try:
        return operation()
    except SessionNotFound:
        raise HTTPException(404, 'session not found') from None
    except SessionConflict:
        raise HTTPException(409, 'session changed; retry with current history') from None


@router.post('/sessions', response_model=SessionResponse, status_code=201)
def create_session():
    return service.get_session_store().create()


@router.get('/sessions/{session_id}', response_model=SessionResponse)
def read_session(session_id: str):
    return session_http(lambda: service.get_session_store().read(session_id))


@router.delete('/sessions/{session_id}', response_model=SessionResponse)
def clear_session(session_id: str):
    return session_http(lambda: service.get_session_store().clear(session_id))
