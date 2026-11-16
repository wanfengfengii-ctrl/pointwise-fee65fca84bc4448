"""Exact phrase retrieval and one-step rewrite search over tokenized text."""
from .corpus import Corpus
from .model import Document
from .matching import find_spans
from .rewrites import (
    CompiledRewrites,
    RewriteEdge,
    TokenNFA,
    compile_rewrites,
    languages_intersect,
    product_reachable,
    validate_rules,
)
from .rules import RuleView

__all__ = [
    "CompiledRewrites",
    "Corpus",
    "Document",
    "RewriteEdge",
    "RuleView",
    "TokenNFA",
    "compile_rewrites",
    "find_spans",
    "languages_intersect",
    "product_reachable",
    "validate_rules",
]
