"""Exact phrase retrieval over immutable pre-tokenized documents."""
from .corpus import Corpus
from .model import Document
from .matching import find_spans

__all__ = ["Corpus", "Document", "find_spans"]
