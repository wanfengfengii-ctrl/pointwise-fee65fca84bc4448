"""Rule-aware retrieval view built only from public compiler results.

The matcher never implements rule matching itself: it compiles query and
document spans with :func:`tokenphrase.rewrites.compile_rewrites`, asks the
public result for public :class:`tokenphrase.rewrites.TokenNFA` recognizers,
and decides each source interval with the generic public NFA product
operation.  No expanded explanation text is ever enumerated.
"""
from dataclasses import dataclass

from .model import token_tuple
from .rewrites import compile_rewrites, product_reachable, validate_rules


@dataclass(frozen=True, slots=True, init=False)
class RuleView:
    corpus: object
    rules: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...]

    def __init__(self, corpus: object, rules: object) -> None:
        object.__setattr__(self, "corpus", corpus)
        # Independent validated snapshot: later mutation of the caller's rule
        # list cannot change this view.
        object.__setattr__(self, "rules", validate_rules(rules))

    def find(self, query: object) -> list[tuple[str, int, int]]:
        phrase = token_tuple(query, "query")
        query_compiled = compile_rewrites(phrase, self.rules)
        query_nfa = query_compiled.recognizer(0, len(phrase))
        hits: set[tuple[str, int, int]] = set()
        for document in self.corpus.documents:
            tokens = document.tokens
            compiled = compile_rewrites(tokens, self.rules)
            total = len(tokens)
            for start in range(total):
                # One public NFA per starting boundary.  The product is built
                # on the fly by product_reachable, so accepted paths and
                # expanded texts are never enumerated.
                nfa = compiled.recognizer(start, total)
                reachable = product_reachable(query_nfa, nfa)
                for query_state, doc_state in reachable:
                    if query_state != query_nfa.accept:
                        continue
                    source_end = nfa.boundary_at(doc_state)
                    # Only source boundaries are accept candidates; chain
                    # states (replacement interiors) report None.
                    if source_end is not None and source_end > start:
                        hits.add((document.id, start, source_end))
        return sorted(hits)
