"""Regression for the public rewrite compiler and rule retrieval view.

The independent reference in this module enumerates source partitions and rule
choices directly; it never imports compiler or matcher internals, so its
expected answer is built from the specification rather than the implementation.
"""
import itertools
import random
import unittest

from samples import DOCUMENTS
from tokenphrase import (
    Corpus,
    Document,
    compile_rewrites,
    find_spans,
    languages_intersect,
    product_reachable,
)


# --------------------------------------------------------------------------
# Independent reference: enumerate partitions and rule choices by hand.
# --------------------------------------------------------------------------

def partitions(length):
    """Every partition of range(length) into nonempty contiguous pieces."""
    for cuts in itertools.product((False, True), repeat=length - 1):
        starts = [0]
        starts.extend(index + 1 for index, cut in enumerate(cuts) if cut)
        ends = starts[1:] + [length]
        yield tuple(zip(starts, ends))


def explanation_set(tokens, rules):
    """Set of complete output token sequences for the whole token sequence."""
    outputs = set()
    for pieces in partitions(len(tokens)):
        choices = []
        for start, end in pieces:
            segment = tuple(tokens[start:end])
            options = [segment]  # keep the original segment
            options.extend(rhs for lhs, rhs in rules if lhs == segment)
            choices.append(options)
        for option in itertools.product(*choices):
            outputs.add(tuple(itertools.chain.from_iterable(option)))
    return outputs


def span_outputs(tokens, rules, start, end):
    return explanation_set(list(tokens[start:end]), rules)


def nfa_outputs(nfa):
    """Enumerate every accepted sequence via public NFA edges (small cases).

    The recognizer is an acyclic DAG whose only sink is the accept boundary,
    so all paths terminate there; each path is one complete explanation.
    """
    results = set()

    def walk(state, produced):
        if state == nfa.accept:
            results.add(tuple(produced))
            return
        for label, target in nfa.adjacency[state]:
            walk(target, produced + [label])

    walk(nfa.start, [])
    return results


def reference_hits(documents, rules, query):
    """Expected hits from independently enumerated span/query explanations."""
    hits = set()
    query_explanations = explanation_set(list(query), rules)
    for doc_id in sorted(documents):
        tokens = tuple(documents[doc_id])
        for start in range(len(tokens)):
            for end in range(start + 1, len(tokens) + 1):
                if span_outputs(tokens, rules, start, end) & query_explanations:
                    hits.add((doc_id, start, end))
    return sorted(hits)


# --------------------------------------------------------------------------
# Concrete spec scenarios.
# --------------------------------------------------------------------------

class SpecExampleTests(unittest.TestCase):
    def test_rewrites_doc_examples(self):
        rules = [
            (("a", "b"), ("x", "y")),
            (("a", "b"), ("u", "v")),
        ]
        corpus = Corpus({"d": ["a", "b"]})
        view = corpus.with_rules(rules)
        self.assertEqual(view.find(["x", "y"]), [("d", 0, 2)])
        self.assertEqual(view.find(["x", "v"]), [])
        self.assertEqual(view.find(["y"]), [])
        hit = view.find(["x", "y"])[0]
        self.assertEqual(corpus.evidence(hit), ("a", "b"))
        # Literal retrieval is unchanged.
        self.assertEqual(corpus.find(["x", "y"]), [])
        self.assertEqual(compile_rewrites(["a", "b"], rules).source_tokens, ("a", "b"))

        medical = Corpus({"d": ["心肌", "梗死"]})
        aliases = [(("心肌", "梗死"), ("心梗",))]
        self.assertEqual(medical.with_rules(aliases).find(["心梗"]), [("d", 0, 2)])

        both = [(("a",), ("x", "y")), (("c",), ("x", "y"))]
        self.assertEqual(Corpus({"d": ["a"]}).with_rules(both).find(["c"]), [("d", 0, 1)])

        nonrecursive = [(("a",), ("b",)), (("b",), ("c",))]
        self.assertEqual(Corpus({"d": ["a"]}).with_rules(nonrecursive).find(["c"]), [])

    def test_medical_aliases_on_sample_documents(self):
        aliases = [
            (("心肌", "梗死"), ("心梗",)),
            (("心肌", "梗死"), ("心肌梗塞",)),
        ]
        corpus = Corpus(DOCUMENTS)
        view = corpus.with_rules(aliases)
        hits = view.find(["心梗"])
        self.assertEqual(hits, [("guide-a", 0, 2), ("guide-b", 0, 1)])
        for hit in hits:
            # Evidence always returns the full original source segment.
            self.assertEqual(corpus.evidence(hit), tuple(DOCUMENTS[hit[0]][hit[1]:hit[2]]))
        self.assertEqual(corpus.evidence(("guide-a", 0, 2)), ("心肌", "梗死"))
        self.assertEqual(corpus.evidence(("guide-b", 0, 1)), ("心梗",))
        # The second alias only rewrites the split phrase; the literal
        # "心梗" document has no rule explaining it as "心肌梗塞".
        self.assertEqual(view.find(["心肌梗塞"]), [("guide-a", 0, 2)])
        # The alias does not invent a phrase that is not a complete explanation.
        self.assertEqual(view.find(["心肌", "心梗"]), [])
        # Original literal behavior stays intact.
        self.assertEqual(corpus.find(["心梗"]), [("guide-b", 0, 1)])
        self.assertEqual(corpus.find(["心肌", "梗死"]), [("guide-a", 0, 2)])


class BoundaryAndBranchTests(unittest.TestCase):
    def test_mutually_exclusive_branches_do_not_splice(self):
        rules = [(("a", "b"), ("x", "y")), (("a", "b"), ("u", "v"))]
        view = Corpus({"d": ["a", "b"]}).with_rules(rules)
        self.assertEqual(view.find(["x", "y"]), [("d", 0, 2)])
        self.assertEqual(view.find(["u", "v"]), [("d", 0, 2)])
        for impossible in (["x"], ["y"], ["u"], ["v"], ["x", "v"], ["u", "y"],
                          ["a", "y"], ["x", "b"]):
            self.assertEqual(view.find(impossible), [], impossible)

    def test_no_start_or_end_inside_a_replacement(self):
        rules = [(("a", "b"), ("x",))]
        compiled = compile_rewrites(["a", "b"], rules)
        nfa = compiled.recognizer(0, 2)
        # Boundary states are exactly the source positions 0..2; the rule
        # edge jumps straight from boundary 0 to boundary 2 and introduces no
        # chain (interior) state for the single-token output.
        self.assertEqual(nfa.boundary_at(0), 0)
        self.assertEqual(nfa.boundary_at(1), 1)
        self.assertEqual(nfa.boundary_at(2), 2)
        self.assertEqual(nfa.n_states, 3)
        self.assertFalse(nfa.accepts(["x", "y"]))
        # A rule match cannot start at its interior position: at boundary 1
        # only the identity "b" edge exists.
        self.assertFalse(compiled.recognizer(1, 2).accepts(["x"]))
        # Nor stop at the interior: the span ending at boundary 1 contains
        # only token "a" and cannot take the whole-segment rule.
        self.assertFalse(compiled.recognizer(0, 1).accepts(["x"]))
        view = Corpus({"d": ["a", "b"]}).with_rules(rules)
        self.assertEqual(view.find(["x"]), [("d", 0, 2)])
        self.assertEqual(view.find(["a"]), [("d", 0, 1)])
        self.assertEqual(view.find(["b"]), [("d", 1, 2)])

    def test_multi_token_replacement_interior_is_not_a_boundary(self):
        rules = [(("a", "b"), ("x", "y"))]
        compiled = compile_rewrites(["a", "b"], rules)
        nfa = compiled.recognizer(0, 2)
        # State 3 is the private chain state between output tokens "x" and
        # "y": it is not a source boundary and can never be an accept.
        self.assertEqual(nfa.n_states, 4)
        self.assertIsNone(nfa.boundary_at(3))
        self.assertEqual(sorted(nfa.boundary_at(state) for state in range(3)),
                         [0, 1, 2])
        self.assertTrue(nfa.accepts(["x", "y"]))
        self.assertFalse(nfa.accepts(["x"]))
        self.assertFalse(nfa.accepts(["y"]))

    def test_overlapping_rules_keep_all_spans(self):
        rules = [(("a",), ("p",)), (("a", "a"), ("q",))]
        tokens = ["a", "a", "a"]
        view = Corpus({"d": tokens}).with_rules(rules)
        self.assertEqual(reference_hits({"d": tokens}, rules, ["q"]),
                         [("d", 0, 2), ("d", 1, 3)])
        self.assertEqual(view.find(["q"]), [("d", 0, 2), ("d", 1, 3)])
        self.assertEqual(view.find(["p", "p", "p"]), [("d", 0, 3)])
        self.assertEqual(view.find(["q", "p"]), [("d", 0, 3)])
        self.assertEqual(view.find(["p", "q"]), [("d", 0, 3)])

    def test_variable_length_outputs_and_identity_segments(self):
        rules = [(("a",), ("x", "y", "z")), (("b", "c"), ("w",))]
        tokens = ["a", "b", "c"]
        view = Corpus({"d": tokens}).with_rules(rules)
        self.assertEqual(view.find(["x", "y", "z", "w"]), [("d", 0, 3)])
        self.assertEqual(view.find(["a", "w"]), [("d", 0, 3)])
        self.assertEqual(view.find(["x", "y", "z", "b", "c"]), [("d", 0, 3)])
        self.assertEqual(view.find(["w"]), [("d", 1, 3)])

    def test_identity_and_duplicate_rules(self):
        rules = [
            (("a",), ("a",)),
            (("a",), ("b",)),
            (("a",), ("b",)),
        ]
        corpus = Corpus({"d": ["a", "a"]})
        compiled = compile_rewrites(["a", "a"], rules)
        # Duplicate pair appears once in the snapshot; identity still present.
        self.assertEqual(compiled.rules, ((("a",), ("a",)), (("a",), ("b",))))
        view = corpus.with_rules(rules)
        self.assertEqual(view.find(["b", "b"]), [("d", 0, 2)])
        self.assertEqual(view.find(["a", "b"]), [("d", 0, 2)])
        # The same span is returned exactly once despite many explanations.
        self.assertEqual(len(view.find(["a", "a"])), 1)

    def test_rules_are_directional(self):
        # The rhs has two tokens.  No reverse rule is synthesized, so a
        # document made of rhs tokens cannot produce a phrase that does not
        # occur on any lhs.
        rules = [(("l1", "l2"), ("r1", "r2"))]
        corpus = Corpus({"d": ["r1", "r2"]})
        view = corpus.with_rules(rules)
        # "q" appears on no lhs and no document segment: no explanation on
        # either side can bridge this gap.
        self.assertEqual(view.find(["q"]), [])
        # The literal phrase still matches via identity retention.
        self.assertEqual(view.find(["r1", "r2"]), [("d", 0, 2)])
        # Forward direction on a document containing the lhs works, and the
        # lhs phrase itself remains a complete identity explanation.
        forward = Corpus({"d": ["l1", "l2"]}).with_rules(rules)
        self.assertEqual(forward.find(["r1", "r2"]), [("d", 0, 2)])
        self.assertEqual(forward.find(["l1", "l2"]), [("d", 0, 2)])

    def test_empty_rules_act_like_literal_retrieval(self):
        corpus = Corpus({"z": ["a", "a", "a"], "m": ["a", "b"]})
        view = corpus.with_rules([])
        self.assertEqual(view.find(["a", "a"]), corpus.find(["a", "a"]))
        self.assertEqual(view.find(["b"]), corpus.find(["b"]))
        self.assertEqual(view.find(["x"]), [])


class ExhaustiveReferenceTests(unittest.TestCase):
    RULE_SETS = [
        [],
        [(("a",), ("b",))],
        [(("a",), ("b",)), (("b",), ("c",))],
        [(("a", "a"), ("p",)), (("a",), ("q",))],
        [(("a", "b"), ("x",)), (("a", "b"), ("y", "z"))],
    ]

    def test_compiler_outputs_against_enumerated_partitions(self):
        for length in range(1, 6):
            for tokens in itertools.product(("a", "b"), repeat=length):
                tokens = list(tokens)
                for rules in self.RULE_SETS:
                    compiled = compile_rewrites(tokens, rules)
                    for start in range(length):
                        for end in range(start + 1, length + 1):
                            nfa = compiled.recognizer(start, end)
                            expected = span_outputs(tokens, rules, start, end)
                            actual = nfa_outputs(nfa)
                            # Exact language equality, including dedup of
                            # explanations yielding identical output.
                            self.assertEqual(actual, expected,
                                             (tokens, rules, start, end))
                            for sequence in expected:
                                self.assertTrue(nfa.accepts(sequence))

    def test_view_hits_against_enumerated_reference(self):
        queries = [list(q) for size in range(1, 4)
                   for q in itertools.product(("a", "b", "x", "y"), repeat=size)]
        for length in range(1, 5):
            for sequence in itertools.product(("a", "b"), repeat=length):
                documents = {"z": list(sequence), "a": list(reversed(sequence))}
                corpus = Corpus(documents)
                for rules in self.RULE_SETS:
                    view = corpus.with_rules(rules)
                    for query in queries:
                        expected = reference_hits(documents, rules, query)
                        actual = view.find(query)
                        self.assertEqual(actual, expected, (documents, rules, query))
                        self.assertEqual(actual, sorted(set(actual)))
                        for hit in actual:
                            doc_id, start, end = hit
                            # Evidence always returns the full original segment.
                            self.assertEqual(corpus.evidence(hit),
                                             tuple(documents[doc_id][start:end]))

    def test_fuzz_against_reference(self):
        rng = random.Random(20261116)
        alphabet = ("a", "b", "c")
        rule_pool = [
            (("a",), ("b",)),
            (("b",), ("c",)),
            (("a",), ("x", "y")),
            (("a", "b"), ("x",)),
            (("b", "c"), ("y", "z")),
            (("a", "a"), ("c",)),
        ]
        for _ in range(40):
            rules = rng.sample(rule_pool, rng.randrange(1, len(rule_pool) + 1))
            documents = {
                "d1": [rng.choice(alphabet) for _ in range(rng.randrange(1, 7))],
                "d2": [rng.choice(alphabet) for _ in range(rng.randrange(1, 7))],
            }
            corpus = Corpus(documents)
            view = corpus.with_rules(rules)
            for _ in range(6):
                query = [rng.choice(alphabet + ("x", "y", "z"))
                         for _ in range(rng.randrange(1, 4))]
                self.assertEqual(view.find(query),
                                 reference_hits(documents, rules, query))


class SnapshotValidationAndPublicSurfaceTests(unittest.TestCase):
    def test_rule_snapshot_isolation(self):
        rules = [(("a",), ("b",))]
        view = Corpus({"d": ["a"]}).with_rules(rules)
        rules.append((("b",), ("c",)))
        self.assertEqual(len(view.rules), 1)
        # Even with the added rule, generated tokens never rewrite.
        self.assertEqual(view.find(["c"]), [])
        recompiled = compile_rewrites(["a"], view.rules)
        self.assertIsNot(recompiled.rules, view.rules)
        self.assertEqual(recompiled.source_tokens, ("a",))

    def test_source_container_isolation(self):
        tokens = ["a", "b"]
        compiled = compile_rewrites(tokens, [(("a", "b"), ("x",))])
        tokens.append("c")
        self.assertEqual(compiled.source_tokens, ("a", "b"))
        self.assertEqual(len(compiled.boundaries), 3)

    def test_public_dag_read_surface(self):
        rules = [(("a", "b"), ("x", "y"))]
        compiled = compile_rewrites(["a", "b"], rules)
        self.assertEqual(compiled.boundaries, (0, 1, 2))
        kinds = {(edge.start, edge.end, edge.kind): edge for edge in compiled.edges}
        self.assertEqual(kinds[(0, 1, "identity")].output, ("a",))
        self.assertEqual(kinds[(1, 2, "identity")].output, ("b",))
        rule_edge = kinds[(0, 2, "rule")]
        self.assertEqual(rule_edge.output, ("x", "y"))
        self.assertEqual(rule_edge.rule, (("a", "b"), ("x", "y")))
        self.assertEqual(rule_edge.rule_index, 0)
        self.assertTrue(compiled.adjacency[0][0].is_identity)
        # span_edges never leaks an edge crossing the requested span.
        self.assertEqual([edge.end for edge in compiled.span_edges(1, 2)], [2])
        nfa = compiled.recognizer(0, 2)
        self.assertTrue(languages_intersect(nfa, nfa))
        self.assertTrue(nfa.accepts(["a", "b"]))
        self.assertTrue(nfa.accepts(["x", "y"]))
        self.assertFalse(nfa.accepts(["x"]))

    def test_invalid_inputs_raise_value_error(self):
        good_rules = [(("a",), ("b",))]
        for bad_tokens in ([], (), "", 3, None, [""], ["x", 2]):
            with self.subTest(bad_tokens=bad_tokens):
                with self.assertRaises(ValueError):
                    compile_rewrites(bad_tokens, good_rules)
        bad_rules = (
            None,
            "x",
            3,
            [()],
            [("a",)],
            [(("a",),)],
            [(("",), ("b",))],
            [(("a",), ("",))],
            [((), ("b",))],
            [(("a",), ())],
            [("a", "b")],
            [((1,), ("b",))],
        )
        for bad in bad_rules:
            with self.subTest(bad_rules=bad):
                with self.assertRaises(ValueError):
                    compile_rewrites(["a"], bad)
                with self.assertRaises(ValueError):
                    Corpus({"d": ["a"]}).with_rules(bad)
        view = Corpus({"d": ["a"]}).with_rules(good_rules)
        for bad_query in ([], (), None, 3, [""], ["x", 1]):
            with self.subTest(bad_query=bad_query):
                with self.assertRaises(ValueError):
                    view.find(bad_query)
        compiled = compile_rewrites(["a", "b"], good_rules)
        for bad_span in ((-1, 2), (0, 3), (1, 1), (2, 1), (False, 1), (0, 1.0)):
            with self.subTest(bad_span=bad_span):
                with self.assertRaises(ValueError):
                    compiled.recognizer(*bad_span)

    def test_literal_api_unchanged(self):
        corpus = Corpus(DOCUMENTS)
        view = corpus.with_rules([(("心肌", "梗死"), ("心梗",))])
        self.assertIsNot(view, corpus)
        self.assertEqual(find_spans(["a", "a", "a"], ["a", "a"]), [(0, 2), (1, 3)])
        self.assertEqual(Document("d", ["a"]).tokens, ("a",))
        self.assertEqual(corpus.find(["心梗"]), [("guide-b", 0, 1)])
        self.assertEqual(view.corpus, corpus)


class BranchChainResourceTests(unittest.TestCase):
    """Exponential explanations must not mean exponential storage or work."""

    def test_branch_chain_resources(self):
        n = 60
        tokens = ["a"] * n
        rules = [(("a",), ("b",))]  # each segment: keep "a" or take "b"
        compiled = compile_rewrites(tokens, rules)

        # Storage: n identity edges + n rule edges, no expanded texts.
        self.assertEqual(len(compiled.edges), 2 * n)
        rule_edges = [edge for edge in compiled.edges if edge.kind == "rule"]
        self.assertEqual(len(rule_edges), n)
        self.assertTrue(all(len(edge.output) == 1 for edge in compiled.edges))

        nfa = compiled.recognizer(0, n)
        self.assertEqual(nfa.n_states, n + 1)
        self.assertEqual(len(nfa.transitions), 2 * n)

        # A query with a complete explanation matches the full span once,
        # although the chain has 2**n accepted segment paths.
        view = Corpus({"d": tokens}).with_rules(rules)
        self.assertEqual(view.find(["b"] * n), [("d", 0, n)])
        # Every length-k suffix span also offers a complete explanation.
        self.assertEqual(
            view.find(["b"] * 10),
            [("d", start, start + 10) for start in range(n - 10 + 1)],
        )

        # Fully disjoint query: the product dies at the first symbol.
        disjoint_nfa = compile_rewrites(["z"] * n, rules).recognizer(0, n)
        reachable = product_reachable(disjoint_nfa, nfa)
        self.assertEqual(reachable, frozenset({(0, 0)}))
        self.assertFalse(languages_intersect(disjoint_nfa, nfa))
        self.assertEqual(view.find(["z"] * n), [])

        # Near-miss query with a failing tail.  "z" is generated by no rule,
        # so the product can advance only along synchronized identity edges;
        # the two prefix symbols reach exactly the diagonal pairs
        # (0,0), (1,1), (2,2), after which every "z" transition is dead.
        near_miss = ["a", "a"] + ["z"] * (n - 2)
        near_nfa = compile_rewrites(near_miss, rules).recognizer(0, n)
        near_reachable = product_reachable(near_nfa, nfa)
        self.assertFalse(languages_intersect(near_nfa, nfa))
        self.assertEqual(view.find(near_miss), [])
        self.assertEqual(near_reachable, frozenset({(0, 0), (1, 1), (2, 2)}))

        # A richer branch chain (multi-token rhs) gives a polynomial product
        # fan-out that still stays far below the exponential path count.
        wide_rules = [(("a",), ("b", "c")), (("a",), ("d", "e"))]
        wide_compiled = compile_rewrites(tokens, wide_rules)
        wide_nfa = wide_compiled.recognizer(0, n)
        wide_query = compile_rewrites(["a", "a", "a"], wide_rules).recognizer(0, 3)
        wide_reachable = product_reachable(wide_query, wide_nfa)
        # The query length caps the product depth: 4 query states times a
        # document reach bounded by 2*3 source positions, a small polynomial
        # independent of the 2**n segment paths of the document chain.
        self.assertEqual(len(wide_reachable), 10)
        self.assertGreater(2 ** n, len(wide_reachable) * 1_000_000)

        # Whole-view search workload, accumulated per starting boundary:
        # a disjoint symbol leaves only the initial product state per start.
        cumulative = 0
        for start in range(n):
            span_nfa = compiled.recognizer(start, n)
            cumulative += len(product_reachable(disjoint_nfa, span_nfa))
        self.assertEqual(cumulative, n)
        self.assertLess(nfa.n_states * near_nfa.n_states, 2 ** n // 1024)
        self.assertGreater(2 ** n, len(near_reachable) * 1_000_000)


if __name__ == "__main__":
    unittest.main()
