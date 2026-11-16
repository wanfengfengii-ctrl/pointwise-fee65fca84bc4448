"""Full scan reference implementation of literal phrase matching."""
from .model import token_tuple


def find_spans(tokens: object, query: object) -> list[tuple[int, int]]:
    """Return every exact half-open span, including overlapping occurrences."""
    source = token_tuple(tokens, "document")
    phrase = token_tuple(query, "query")
    width = len(phrase)
    spans = []
    for start in range(len(source) - width + 1):
        for offset, token in enumerate(phrase):
            if source[start + offset] != token:
                break
        else:
            spans.append((start, start + width))
    return spans
