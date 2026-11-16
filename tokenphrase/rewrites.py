"""Public one-step rewrite compiler (deliverable A).

The compiler turns a token sequence plus directional rewrite rules into a
segment DAG over the *source* positions.  Every complete explanation of a
source interval is exactly one source-to-boundary path in this DAG:

* boundary ``i`` is the source position between tokens ``i-1`` and ``i``;
* an identity edge ``i -> i+1`` keeps source token ``i``;
* a rule edge ``i -> j`` exists only when a rule lhs equals the whole source
  segment ``[i, j)`` and is labelled with that rule's rhs tokens;
* edge labels are plain output tokens.  They never start new edges, so
  generated tokens are never rewritten (rules are one-step, non-recursive);
* edges consume disjoint contiguous source segments, so a path can neither
  enter nor leave the interior of a replacement, nor splice the interiors of
  mutually exclusive branches.

The DAG is polynomial-sized and never stores an expanded explanation.  A
:class:`TokenNFA` view over any nonempty source interval exposes the interval's
output language; generic NFA algorithms (product construction) decide language
intersection without enumerating explanations.
"""
from dataclasses import dataclass

from .model import token_tuple

_IDENTITY_KIND = "identity"
_RULE_KIND = "rule"


def _valid_side(side: object, label: str) -> tuple[str, ...]:
    if not isinstance(side, (list, tuple)) or not side:
        raise ValueError(f"{label} must be a nonempty list or tuple of tokens")
    if any(not isinstance(token, str) or not token for token in side):
        raise ValueError(f"{label} tokens must be nonempty strings")
    return tuple(side)


def validate_rules(rules: object) -> tuple[tuple[tuple[str, ...], tuple[str, ...]], ...]:
    """Validate rules and return an independent deduplicated snapshot.

    Exact duplicate ``(lhs, rhs)`` pairs never change the set of accepted
    explanations, so the snapshot keeps one copy of each distinct pair while
    preserving first-seen order.
    """
    if not isinstance(rules, (list, tuple)):
        raise ValueError("rules must be a list or tuple of (lhs, rhs) pairs")
    snapshot: list[tuple[tuple[str, ...], tuple[str, ...]]] = []
    seen: set[tuple[tuple[str, ...], tuple[str, ...]]] = set()
    for rule in rules:
        if not isinstance(rule, (list, tuple)) or len(rule) != 2:
            raise ValueError("each rule must be a (lhs, rhs) pair")
        lhs, rhs = rule
        pair = (_valid_side(lhs, "rule lhs"), _valid_side(rhs, "rule rhs"))
        if pair not in seen:
            seen.add(pair)
            snapshot.append(pair)
    return tuple(snapshot)


@dataclass(frozen=True, slots=True)
class RewriteEdge:
    """One public DAG edge covering the nonempty source span ``[start, end)``.

    ``output`` is the full token sequence produced by the segment.  Identity
    edges keep the single source token; rule edges carry the matched rule's
    rhs.  ``rule`` is the originating ``(lhs, rhs)`` pair for rule edges and
    ``None`` for identity edges; ``rule_index`` is its position in
    :attr:`CompiledRewrites.rules`, or ``-1`` for identity edges.
    """

    start: int
    end: int
    output: tuple[str, ...]
    kind: str
    rule: tuple[tuple[str, ...], tuple[str, ...]] | None
    rule_index: int

    @property
    def is_identity(self) -> bool:
        return self.kind == _IDENTITY_KIND


@dataclass(frozen=True, slots=True)
class TokenNFA:
    """Public token-labelled NFA for the output language of one source span.

    States ``0 .. source_end - source_start`` are *boundary states*, one per
    source position of the span.  All other states are private chain states
    materialising a multi-token edge label and can never be accepted as a
    source boundary.  Every transition consumes exactly one token; there are
    no epsilon transitions.
    """

    n_states: int
    start: int
    accept: int
    adjacency: tuple[tuple[tuple[str, int], ...], ...]
    transitions: tuple[tuple[int, str, int], ...]
    source_start: int
    source_end: int

    def boundary_at(self, state: int) -> int | None:
        """Return the source coordinate of a boundary state, else ``None``."""
        if 0 <= state <= self.source_end - self.source_start:
            return self.source_start + state
        return None

    def is_accept_state(self, state: int) -> bool:
        return state == self.accept

    def accepts(self, sequence: object) -> bool:
        """Membership test for one concrete output (polynomial state sets)."""
        if not isinstance(sequence, (list, tuple)) or not sequence:
            return False
        if any(not isinstance(token, str) or not token for token in sequence):
            return False
        current = {self.start}
        for token in sequence:
            following: set[int] = set()
            for state in current:
                for label, target in self.adjacency[state]:
                    if label == token:
                        following.add(target)
            current = following
            if not current:
                return False
        return self.accept in current


@dataclass(frozen=True, slots=True)
class CompiledRewrites:
    """Public compiled result: source tokens, rule snapshot and segment DAG.

    ``boundaries`` is the tuple ``0..n`` of source positions; ``edges`` are
    all public segment edges; ``adjacency[i]`` groups edges leaving boundary
    ``i`` in a deterministic order.  A complete explanation of source span
    ``[s, e)`` is any path from boundary ``s`` to boundary ``e``; the path's
    output tokens, in edge order, are the explained token sequence.
    """

    source_tokens: tuple[str, ...]
    rules: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...]
    boundaries: tuple[int, ...]
    edges: tuple[RewriteEdge, ...]
    adjacency: tuple[tuple[RewriteEdge, ...], ...]

    def _check_span(self, start: object, end: object) -> tuple[int, int]:
        if type(start) is not int or type(end) is not int:
            raise ValueError("span endpoints must be non-boolean integers")
        limit = len(self.source_tokens)
        if not 0 <= start < end <= limit:
            raise ValueError("span must be nonempty and within the compiled tokens")
        return start, end

    def recognizer(self, start: int, end: int) -> TokenNFA:
        """Compile the public NFA of the output language of ``[start, end)``.

        Only edges beginning at or after ``start`` and ending at or before
        ``end`` are included, so a replacement interior can never be used as
        an entry point or a stopping point.  Multi-token outputs get private
        chain states; only source boundaries are candidate accept states.
        """
        start, end = self._check_span(start, end)
        length = end - start
        adjacency: list[list[tuple[str, int]]] = [[] for _ in range(length + 1)]
        transitions: list[tuple[int, str, int]] = []
        next_state = length + 1
        for local_state in range(length):
            source_pos = start + local_state
            for edge in self.adjacency[source_pos]:
                if edge.end > end:
                    continue
                target = edge.end - start
                current = local_state
                width = len(edge.output)
                for offset, token in enumerate(edge.output):
                    if offset == width - 1:
                        following = target
                    else:
                        following = next_state
                        adjacency.append([])
                        next_state += 1
                    adjacency[current].append((token, following))
                    transitions.append((current, token, following))
                    current = following
        return TokenNFA(
            n_states=next_state,
            start=0,
            accept=length,
            adjacency=tuple(tuple(rows) for rows in adjacency),
            transitions=tuple(transitions),
            source_start=start,
            source_end=end,
        )

    def span_edges(self, start: int, end: int) -> tuple[RewriteEdge, ...]:
        """Public read helper: edges usable inside source span ``[start, end)``."""
        start, end = self._check_span(start, end)
        return tuple(
            edge
            for position in range(start, end)
            for edge in self.adjacency[position]
            if edge.end <= end
        )


def compile_rewrites(
    tokens: object, rules: object
) -> CompiledRewrites:
    """Compile ``tokens`` with directional ``rules`` into a public segment DAG."""
    source = token_tuple(tokens, "tokens")
    rule_snapshot = validate_rules(rules)
    total = len(source)
    edges: list[RewriteEdge] = [
        RewriteEdge(i, i + 1, (source[i],), _IDENTITY_KIND, None, -1)
        for i in range(total)
    ]
    for rule_index, (lhs, rhs) in enumerate(rule_snapshot):
        width = len(lhs)
        for position in range(total - width + 1):
            if all(source[position + offset] == lhs[offset] for offset in range(width)):
                edges.append(
                    RewriteEdge(
                        position,
                        position + width,
                        rhs,
                        _RULE_KIND,
                        (lhs, rhs),
                        rule_index,
                    )
                )
    edges.sort(
        key=lambda edge: (
            edge.start,
            edge.end,
            edge.kind,
            edge.output,
            edge.rule_index,
        )
    )
    adjacency = tuple(
        tuple(edge for edge in edges if edge.start == position)
        for position in range(total)
    )
    return CompiledRewrites(
        source_tokens=source,
        rules=rule_snapshot,
        boundaries=tuple(range(total + 1)),
        edges=tuple(edges),
        adjacency=adjacency,
    )


def product_reachable(first: TokenNFA, second: TokenNFA) -> frozenset[tuple[int, int]]:
    """Reachable state pairs of two public token NFAs under synchronized labels.

    This is a generic automaton operation reading only public NFA fields: it
    knows nothing about rules.  Work is proportional to reachable product
    states, never to the number of accepted paths or expanded texts.
    """
    seen = {(first.start, second.start)}
    stack = [(first.start, second.start)]
    while stack:
        left_state, right_state = stack.pop()
        for left_label, left_next in first.adjacency[left_state]:
            for right_label, right_next in second.adjacency[right_state]:
                if left_label == right_label and (left_next, right_next) not in seen:
                    pair = (left_next, right_next)
                    seen.add(pair)
                    stack.append(pair)
    return frozenset(seen)


def languages_intersect(first: TokenNFA, second: TokenNFA) -> bool:
    """Return whether the two public NFAs accept one common token sequence."""
    return any(
        left_state == first.accept and right_state == second.accept
        for left_state, right_state in product_reachable(first, second)
    )
