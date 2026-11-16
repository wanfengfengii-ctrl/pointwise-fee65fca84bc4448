"""Validated immutable source tokens; no tokenization or normalization."""
from dataclasses import dataclass


def token_tuple(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or not value:
        raise ValueError(f"{label} must be a nonempty list or tuple of tokens")
    if any(not isinstance(token, str) or not token for token in value):
        raise ValueError(f"{label} tokens must be nonempty strings")
    return tuple(value)


def document_id(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("document ID must be a nonempty string")
    return value


@dataclass(frozen=True, slots=True)
class Document:
    id: str
    tokens: tuple[str, ...]

    def __post_init__(self) -> None:
        document_id(self.id)
        object.__setattr__(self, "tokens", token_tuple(self.tokens, "document"))
