"""Immutable collection and source-evidence lookup."""
from collections.abc import Mapping
from dataclasses import dataclass

from .matching import find_spans
from .model import Document, document_id, token_tuple


@dataclass(frozen=True, slots=True, init=False)
class Corpus:
    documents: tuple[Document, ...]

    def __init__(self, documents: Mapping[str, list[str] | tuple[str, ...]]):
        if not isinstance(documents, Mapping):
            raise ValueError("documents must be a mapping")
        frozen = [Document(key, value) for key, value in documents.items()]
        frozen.sort(key=lambda document: document.id)
        object.__setattr__(self, "documents", tuple(frozen))

    def get(self, doc_id: str) -> tuple[str, ...]:
        document_id(doc_id)
        for document in self.documents:
            if document.id == doc_id:
                return document.tokens
        raise KeyError(doc_id)

    def find(self, query: object) -> list[tuple[str, int, int]]:
        phrase = token_tuple(query, "query")
        return [
            (document.id, start, end)
            for document in self.documents
            for start, end in find_spans(document.tokens, phrase)
        ]

    def evidence(self, hit: object) -> tuple[str, ...]:
        """Resolve a nonempty source span; the span need not be a prior hit."""
        if not isinstance(hit, (list, tuple)) or len(hit) != 3:
            raise ValueError("hit must contain document ID, start, end")
        doc_id, start, end = hit
        tokens = self.get(doc_id)
        if any(type(index) is not int for index in (start, end)):
            raise ValueError("span endpoints must be non-boolean integers")
        if not 0 <= start < end <= len(tokens):
            raise ValueError("span must be nonempty and within the document")
        return tokens[start:end]
