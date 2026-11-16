import itertools
from dataclasses import FrozenInstanceError
import unittest

from samples import DOCUMENTS
from tokenphrase import Corpus, Document, find_spans


def reference(documents, query):
    # Enumerate source intervals independently of the matcher's fixed-width scan.
    result = []
    for doc_id in sorted(documents):
        tokens = list(documents[doc_id])
        for start in range(len(tokens)):
            for end in range(start + 1, len(tokens) + 1):
                if tokens[start:end] == list(query):
                    result.append((doc_id, start, end))
    return result


class LiteralTests(unittest.TestCase):
    def test_sample_evidence_handoff(self):
        corpus = Corpus(DOCUMENTS)
        hits = corpus.find(["患者", "需要"])
        self.assertEqual(hits, [("guide-a", 2, 4), ("guide-b", 1, 3)])
        for hit in hits:
            self.assertEqual(corpus.evidence(hit), ("患者", "需要"))
        self.assertEqual(corpus.find(["心梗"]), [("guide-b", 0, 1)])
        self.assertEqual(corpus.find(["心肌", "梗死"]), [("guide-a", 0, 2)])
        self.assertEqual(corpus.find(["边界", "不可"]), [])

    def test_all_boundaries_overlaps_and_sorting(self):
        corpus = Corpus({"z": ["a", "a", "a"], "a": ["a", "a"], "中": ["a"]})
        self.assertEqual(corpus.find(["a", "a"]),
                         [("a", 0, 2), ("z", 0, 2), ("z", 1, 3)])
        self.assertEqual(corpus.find(["a", "a", "a"]), [("z", 0, 3)])
        self.assertEqual(corpus.find(["a"])[-1], ("中", 0, 1))
        self.assertEqual(corpus.find(["a"] * 4), [])
        self.assertEqual(corpus.find(["missing"]), [])
        self.assertEqual(find_spans(["x", "y", "x"], ["x"]), [(0, 1), (2, 3)])

    def test_exact_tokens_without_normalization(self):
        corpus = Corpus({"d": ["A", "a", "é", "e\u0301", " ", "x y", "x", "y"]})
        for token, position in [("A", 0), ("a", 1), ("é", 2), ("e\u0301", 3), (" ", 4), ("x y", 5)]:
            self.assertEqual(corpus.find([token]), [("d", position, position + 1)])
        self.assertEqual(corpus.find(["x", "y"]), [("d", 6, 8)])

    def test_snapshot_and_result_isolation(self):
        rows = ["a", "b"]
        source = {"d": rows}
        corpus = Corpus(source)
        rows[:] = ["changed"]
        source.clear()
        self.assertEqual(corpus.get("d"), ("a", "b"))
        query = ["a"]
        hits = corpus.find(query)
        query[0] = "b"
        hits.clear()
        self.assertEqual(corpus.find(["a"]), [("d", 0, 1)])
        self.assertEqual(corpus.evidence(("d", 0, 2)), ("a", "b"))
        with self.assertRaises(FrozenInstanceError):
            corpus.documents = ()
        with self.assertRaises(FrozenInstanceError):
            corpus.documents[0].tokens = ("changed",)
        standalone = Document("item", ["a"])
        self.assertEqual(standalone.tokens, ("a",))

    def test_empty_corpus(self):
        corpus = Corpus({})
        self.assertEqual(corpus.documents, ())
        self.assertEqual(corpus.find(["x"]), [])
        with self.assertRaises(ValueError):
            corpus.find([])
        with self.assertRaises(KeyError):
            corpus.get("missing")

    def test_invalid_construction_and_queries(self):
        for invalid in (None, [], "d", 3):
            with self.subTest(mapping=invalid), self.assertRaises(ValueError):
                Corpus(invalid)
        for invalid_id in ("", 1, None, False):
            with self.subTest(doc_id=invalid_id), self.assertRaises(ValueError):
                Corpus({invalid_id: ["x"]})
        invalid_tokens = ([], (), "", "abc", None, 3, {"x"}, [""] , ["x", 2], [None])
        for invalid in invalid_tokens:
            with self.subTest(tokens=invalid):
                with self.assertRaises(ValueError):
                    Corpus({"d": invalid})
                with self.assertRaises(ValueError):
                    Document("d", invalid)
                with self.assertRaises(ValueError):
                    find_spans(invalid, ["x"])
                with self.assertRaises(ValueError):
                    Corpus({"d": ["x"]}).find(invalid)
                with self.assertRaises(ValueError):
                    find_spans(["x"], invalid)

    def test_evidence_validation(self):
        corpus = Corpus({"d": ["a", "b"]})
        for invalid in (None, (), ("d", 0), ("d", 0, 1, 2),
                        ("d", -1, 1), ("d", 0, 3), ("d", 1, 1),
                        ("d", 2, 1), ("d", False, 1), ("d", 0, 1.0), ("", 0, 1)):
            with self.subTest(hit=invalid), self.assertRaises(ValueError):
                corpus.evidence(invalid)
        with self.assertRaises(KeyError):
            corpus.evidence(("unknown", 0, 1))
        self.assertEqual(corpus.evidence(["d", 1, 2]), ("b",))

    def test_exhaustive_short_sequences(self):
        sequences = [tokens for size in range(1, 6)
                     for tokens in itertools.product(("a", "b"), repeat=size)]
        queries = [tokens for size in range(1, 5)
                   for tokens in itertools.product(("a", "b"), repeat=size)]
        for index, sequence in enumerate(sequences):
            documents = {"z": sequence, "a": tuple(reversed(sequence))}
            corpus = Corpus(documents)
            for query in queries:
                with self.subTest(sequence=index, query=query):
                    actual = corpus.find(query)
                    self.assertEqual(actual, reference(documents, query))
                    self.assertEqual(actual, sorted(set(actual)))
                    for hit in actual:
                        self.assertEqual(corpus.evidence(hit), query)


if __name__ == "__main__":
    unittest.main()
