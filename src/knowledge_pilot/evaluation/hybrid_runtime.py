"""Bounded Dense service adapter and a guard against opening frozen Chroma."""
from collections.abc import Callable
import math
from pathlib import Path
from typing import Any

from knowledge_pilot.evaluation.evidence_collector import SearchResult
from knowledge_pilot.evaluation.hybrid import RetrievalError


def validate_isolated_runtime(runtime: Path, temporary_root: Path, frozen: Path) -> Path:
    runtime = runtime.resolve(strict=True)
    temporary_root = temporary_root.resolve(strict=True)
    frozen = frozen.resolve(strict=True)
    if runtime == frozen or runtime.is_relative_to(frozen) or frozen.is_relative_to(runtime):
        raise ValueError('Refuse opening original frozen runtime')
    if not runtime.is_relative_to(temporary_root) or runtime == temporary_root:
        raise ValueError('Runtime must be a child of the dedicated temporary directory')
    return runtime


def make_dense_search(
    collection: Any, *, post: Callable[..., Any],
    service_errors: tuple[type[Exception], ...], model: str = 'bge-m3', dimensions: int = 1024,
) -> Callable[[str, int], list[SearchResult]]:
    """Same embedding model, Chroma query and 1-distance as the Dense baseline.

    Transport/Chroma error classes are provided by the real runtime, never imported
    here. Malformed model responses are explicit service failures; code defects
    and malformed local collection records are allowed to propagate.
    """
    def search(query: str, k: int) -> list[SearchResult]:
        try:
            response = post('http://localhost:11434/api/embed',
                            json={'model': model, 'input': query}, timeout=(5,120))
            response.raise_for_status()
        except service_errors as error:
            raise RetrievalError(f'{type(error).__name__}: {error}', stage='embedding') from error
        try:
            data = response.json()
        except ValueError as error:
            raise RetrievalError(f'Invalid embedding JSON: {error}', stage='embedding_response') from error
        vectors = data.get('embeddings') if isinstance(data, dict) else None
        if (not isinstance(vectors, list) or len(vectors) != 1 or
                not isinstance(vectors[0], list) or len(vectors[0]) != dimensions or
                any(not isinstance(v,(int,float)) or not math.isfinite(v) for v in vectors[0])):
            raise RetrievalError(f'Invalid embedding response: {data.get("error") if isinstance(data,dict) else type(data).__name__}',
                                 stage='embedding_response')
        try:
            raw = collection.query(query_embeddings=vectors, n_results=k,
                                   include=['documents','metadatas','distances'], where=None)
        except service_errors as error:
            raise RetrievalError(f'{type(error).__name__}: {error}', stage='dense_query') from error
        documents, distances, metadatas = raw['documents'][0], raw['distances'][0], raw['metadatas'][0]
        if not (len(documents) == len(distances) == len(metadatas)):
            raise ValueError('Inconsistent Chroma candidate arrays')
        return [(text, 1-distance, metadata) for text,distance,metadata in zip(documents,distances,metadatas)]
    return search
