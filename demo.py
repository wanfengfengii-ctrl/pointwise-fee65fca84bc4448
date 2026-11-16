"""Print literal hits, rewrite/alias hits with source evidence, and resources.

The literal report preserves the original project behavior exactly.  The
rewrite report searches through the public compiler plus rule view, and every
hit is resolved back to its complete original source segment via evidence().
"""
import json
import time

from samples import DOCUMENTS
from tokenphrase import Corpus, compile_rewrites, product_reachable


LITERAL_QUERIES = (
    ["心肌", "梗死"],
    ["心梗"],
    ["患者", "需要"],
    ["复查", "复查"],
    ["边界", "不可"],
)

# Directional aliases for the clinical concept myocardial infarction.
# Highlighted evidence always stays in the original source tokens: the alias
# only decides matching, never fabricates a phrase not present in the source.
ALIAS_RULES = [
    (("心肌", "梗死"), ("心梗",)),
    (("心肌", "梗死"), ("心肌梗塞",)),
]
ALIAS_QUERIES = (
    ["心梗"],
    ["心肌梗塞"],
    ["心肌", "梗死"],
    ["患者", "需要"],
)


def report_literal(corpus):
    return [
        {
            "query": query,
            "hits": [
                {
                    "doc_id": doc_id,
                    "start": start,
                    "end": end,
                    "source_evidence": list(corpus.evidence((doc_id, start, end))),
                }
                for doc_id, start, end in corpus.find(query)
            ],
        }
        for query in LITERAL_QUERIES
    ]


def report_rewrites(corpus):
    view = corpus.with_rules(ALIAS_RULES)
    reports = []
    for query in ALIAS_QUERIES:
        hits = view.find(query)
        reports.append(
            {
                "query": query,
                "hits": [
                    {
                        "doc_id": doc_id,
                        "start": start,
                        "end": end,
                        "source_evidence": list(corpus.evidence((doc_id, start, end))),
                    }
                    for doc_id, start, end in hits
                ],
            }
        )
    return reports


def branch_chain_resource_report():
    """Exponential explanations, polynomial representation and search work."""
    n = 60
    tokens = ["a"] * n
    rules = [(("a",), ("b",))]
    compiled = compile_rewrites(tokens, rules)
    full_nfa = compiled.recognizer(0, n)

    disjoint_query = ["z"] * n
    query_nfa = compile_rewrites(disjoint_query, rules).recognizer(0, n)

    started = time.perf_counter()
    reachable_pairs = 0
    for start in range(n):
        reachable_pairs += len(product_reachable(query_nfa, compiled.recognizer(start, n)))
    elapsed = time.perf_counter() - started

    view = Corpus({"d": tokens}).with_rules(rules)
    return {
        "segment_count": n,
        "complete_segment_paths": 2 ** n,
        "compiled_edges": len(compiled.edges),
        "recognizer_states": full_nfa.n_states,
        "recognizer_transitions": len(full_nfa.transitions),
        "disjoint_query": disjoint_query,
        "reachable_product_states_during_search": reachable_pairs,
        "search_seconds": round(elapsed, 6),
        "positive_hit_on_full_span": view.find(["b"] * n),
    }


def main() -> None:
    corpus = Corpus(DOCUMENTS)
    print(json.dumps(
        {
            "mode": "literal",
            "reports": report_literal(corpus),
        },
        ensure_ascii=False,
        indent=2,
    ))
    print(json.dumps(
        {
            "mode": "rewrite_aliases",
            "rules": [{"lhs": list(lhs), "rhs": list(rhs)}
                      for lhs, rhs in ALIAS_RULES],
            "reports": report_rewrites(corpus),
        },
        ensure_ascii=False,
        indent=2,
    ))
    print(json.dumps(
        {"mode": "branch_chain_resources", "report": branch_chain_resource_report()},
        ensure_ascii=False,
        indent=2,
    ))


if __name__ == "__main__":
    main()
