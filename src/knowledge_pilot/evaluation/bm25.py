"""Small standard-library Okapi BM25 index for frozen evaluation chunks."""

from collections import Counter
from collections.abc import Mapping, Sequence
import math
import re
from typing import Any, Final, TypedDict


TOKENIZER_NAME: Final[str] = "technical_identifier_cjk_unigram_bigram_v1"
TOKENIZER_VERSION: Final[str] = "1"
BM25_SCORE_TYPE: Final[str] = "bm25_okapi"
IDF_FORMULA: Final[str] = "ln(1 + (N - df + 0.5) / (df + 0.5))"

_TOKEN_PATTERN = re.compile(
    r"/[A-Za-z0-9_{}.-]+(?:/[A-Za-z0-9_{}.-]+)*"
    r"|[A-Za-z_][A-Za-z0-9_]*(?:-[A-Za-z0-9_]+)*"
    r"|[0-9]+(?:\.[0-9]+)?"
    r"|[\u4e00-\u9fff]+"
)
_CJK_PATTERN = re.compile(r"^[\u4e00-\u9fff]+$")


class BM25Candidate(TypedDict):
    document_id: str
    chunk_index: int
    rank: int
    text: str
    score: float
    score_type: str
    source: str | None


def tokenize(text: str) -> list[str]:
    """Tokenize technical identifiers and CJK character uni/bi-grams."""
    tokens: list[str] = []
    for match in _TOKEN_PATTERN.finditer(text):
        value = match.group(0).lower()
        if _CJK_PATTERN.fullmatch(value):
            tokens.extend(value)
            tokens.extend(value[index:index + 2] for index in range(len(value) - 1))
        else:
            tokens.append(value)
    return tokens


class BM25Index:
    """Immutable in-memory Okapi BM25 index over caller-supplied frozen chunks."""

    def __init__(self, chunks: Sequence[Mapping[str, Any]], k1: float = 1.2, b: float = 0.75):
        if k1 <= 0:
            raise ValueError("k1 must be positive")
        if not 0 <= b <= 1:
            raise ValueError("b must be between 0 and 1")
        self.k1 = k1
        self.b = b
        self.documents = [dict(chunk) for chunk in chunks]
        identities = [(item["document_id"], item["chunk_index"]) for item in self.documents]
        if len(identities) != len(set(identities)):
            raise ValueError("duplicate chunk identity")
        self.term_frequencies = [Counter(tokenize(item["text"])) for item in self.documents]
        self.document_lengths = [sum(frequencies.values()) for frequencies in self.term_frequencies]
        self.average_document_length = (
            sum(self.document_lengths) / len(self.document_lengths) if self.documents else 0.0
        )
        document_frequency: Counter[str] = Counter()
        for frequencies in self.term_frequencies:
            document_frequency.update(frequencies.keys())
        count = len(self.documents)
        self.idf = {
            term: math.log(1 + (count - frequency + 0.5) / (frequency + 0.5))
            for term, frequency in document_frequency.items()
        }

    def search(self, query: str, k: int = 3) -> list[BM25Candidate]:
        if k < 0:
            raise ValueError("k must be non-negative")
        if k == 0 or not self.documents:
            return []
        query_frequencies = Counter(tokenize(query))
        if not query_frequencies:
            return []
        scored: list[tuple[float, dict[str, Any]]] = []
        for document, frequencies, length in zip(
            self.documents, self.term_frequencies, self.document_lengths
        ):
            score = 0.0
            for term, query_count in query_frequencies.items():
                frequency = frequencies.get(term, 0)
                if frequency == 0:
                    continue
                normalization = 1 - self.b
                if self.average_document_length:
                    normalization += self.b * length / self.average_document_length
                denominator = frequency + self.k1 * normalization
                score += query_count * self.idf[term] * (
                    frequency * (self.k1 + 1) / denominator
                )
            if score > 0:
                scored.append((score, document))
        scored.sort(key=lambda item: (
            -item[0], str(item[1]["document_id"]), int(item[1]["chunk_index"])
        ))
        candidates: list[BM25Candidate] = []
        for rank, (score, document) in enumerate(scored[:k], start=1):
            candidates.append({
                "document_id": document["document_id"],
                "chunk_index": document["chunk_index"],
                "rank": rank,
                "text": document["text"],
                "score": score,
                "score_type": BM25_SCORE_TYPE,
                "source": document.get("source"),
            })
        return candidates

