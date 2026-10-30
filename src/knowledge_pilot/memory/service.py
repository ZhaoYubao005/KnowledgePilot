"""Session boundary: snapshot -> bounded messages -> inference -> CAS commit."""
from knowledge_pilot.config import DATA_DIR, SYSTEM_PROMPT
from knowledge_pilot.runtime_settings import bounded_integer
from knowledge_pilot.memory.store import SessionStore
from knowledge_pilot.memory.context import history_messages


def get_session_store() -> SessionStore:
    return SessionStore(DATA_DIR / 'sessions.sqlite3',
        max_turns=bounded_integer('KP_SESSION_MAX_TURNS', 10, 1, 100),
        max_chars=bounded_integer('KP_SESSION_MAX_CHARS', 12000, 256, 100000))


def with_session(session_id: str, query: str, execute):
    if not query.strip() or len(query) > 8000:
        from knowledge_pilot.errors import InputError
        raise InputError('invalid session query')
    store = get_session_store()
    snapshot = store.read(session_id)
    result = execute(history_messages(snapshot['turns']))
    if result.get('status') == 'completed' or result.get('stop_reason') == 'completed':
        if not isinstance(result.get('answer'), str) or not result['answer'].strip():
            from knowledge_pilot.errors import ModelResponseError
            raise ModelResponseError('llm')
        store.append(session_id, query, result['answer'], expected_revision=snapshot['revision'])
    return result


def session_chat(query: str, session_id: str, *, max_steps: int = 5, agent=None):
    if agent is None:
        from knowledge_pilot.llm.ollama_client import chat_with_ollama
        agent = chat_with_ollama
    def execute(history):
        messages = [{'role': 'system', 'content': SYSTEM_PROMPT}] + history + [
            {'role': 'user', 'content': query}]
        return agent(messages, max_steps=max_steps)
    return with_session(session_id, query, execute)
