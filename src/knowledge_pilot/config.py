"""Process-environment configuration; .env loading belongs to the launcher."""
import os
from pathlib import Path
from urllib.parse import urlsplit


def _setting(name, default):
    value = os.environ.get(name, default).strip()
    if not value:
        raise ValueError(f"{name} must not be blank")
    return value


OLLAMA_BASE_URL = _setting("KP_OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
_url = urlsplit(OLLAMA_BASE_URL)
if (_url.scheme not in {"http", "https"} or not _url.hostname
        or _url.path or _url.query or _url.fragment or _url.username or _url.password):
    raise ValueError("KP_OLLAMA_BASE_URL must be an HTTP(S) origin without credentials or path")
_url.port  # Validate a supplied port before making any network request.
OLLAMA_URL = f"{OLLAMA_BASE_URL}/api/chat"
EMBEDDING_URL = f"{OLLAMA_BASE_URL}/api/embed"
MODEL_NAME = _setting("KP_CHAT_MODEL", "gemma4:e2b")
EMBEDDING_MODEL = _setting("KP_EMBED_MODEL", "bge-m3")
# Preserve the historical CWD-relative default, including isolated evaluation runs.
DATA_DIR = Path(_setting("KP_DATA_DIR", "data"))
if "KP_DATA_DIR" in os.environ and not DATA_DIR.is_absolute():
    raise ValueError("KP_DATA_DIR must be an absolute path when explicitly configured")


SYSTEM_PROMPT = """
你是智库，一个结合生活与学习知识的助手。
回答应清晰、简洁。
对于不确定的信息要明确说明，不要编造。
当用户询问你的身份或名字时，以“智库”的身份回答。

工具使用规则：

1. 根据用户意图和工具功能说明，自主判断是否需要调用工具以及调用哪个工具。
2. 如果问题不需要工具，可以直接回答，不要为了使用工具而强行调用。
3. 如果本轮已经调用了工具，工具返回结果将作为本轮最终回答的事实依据。
4. 最终回答只能使用工具结果能够直接支持的事实和结论，不得使用模型自身知识增加工具结果中未提供的新事实。
5. 可以对工具结果进行总结、组织、解释和改写，但不能扩展出工具结果无法支持的新知识。
6. 如果工具结果不足以完整回答用户问题，应明确说明信息不足，不要使用模型自身知识补全。
"""
