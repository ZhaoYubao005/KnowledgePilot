"""Ollama native HTTP adapter; no Agent Loop or LangChain model wrapper."""
import json
import requests
from knowledge_pilot.config import MODEL_NAME, OLLAMA_URL
from knowledge_pilot.errors import ModelResponseError
from knowledge_pilot.llm.transport import post_json


def ollama_message(messages: list[dict], schema: dict | None = None):
    payload = {'model': MODEL_NAME, 'messages': messages, 'stream': False,
               'options': {'temperature': 0}}
    if schema is not None:
        payload['format'] = schema
    data = post_json(OLLAMA_URL, payload, operation='llm', post=requests.post)
    message = data.get('message')
    if (not isinstance(message, dict) or message.get('tool_calls')
            or not isinstance(message.get('content'), str) or not message['content'].strip()):
        raise ModelResponseError('llm')
    if schema is not None:
        try:
            return json.loads(message['content'])
        except ValueError:
            raise ModelResponseError('llm') from None
    return message['content']
