"""tests/test_matrix.py — the spreadsheet brain's mechanical laws."""

import os
import random
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from engine.matrix import Matrix, canon, clamp01, slugify  # noqa: E402


class TestMatrix(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.m = Matrix(self.dir)

    def test_node_idempotent_by_label(self):
        a = self.m.add_node("moth", origin_round=0)
        b = self.m.add_node("moth", origin_round=9)
        self.assertEqual(a, b)
        self.assertEqual(self.m.nodes[a]["origin_round"], 0)  # first write wins

    def test_distinct_labels_get_distinct_ids(self):
        a = self.m.add_node("song")
        c = self.m.add_node("song!")  # slugifies to "song" → suffix
        self.assertNotEqual(a, c)

    def test_edge_upsert_merges_not_stomps(self):
        na = self.m.add_node("joy")
        nb = self.m.add_node("entropy")
        e1 = self.m.upsert_edge(na, nb, "resonates", 0.8, 0.2, 0.6)
        e2 = self.m.upsert_edge(na, nb, "resonates", 0.4, 0.6, 0.2)
        self.assertEqual(e1, e2)
        row = self.m.edges[e1]
        self.assertAlmostEqual(row["joy"], 0.6)     # (0.8+0.4)/2
        self.assertAlmostEqual(row["entropy"], 0.4)
        self.assertAlmostEqual(row["value"], 0.4)

    def test_hash_stable_across_roundtrip(self):
        na = self.m.add_node("moth")
        nb = self.m.add_node("dawn")
        self.m.upsert_edge(na, nb, "echoes", 0.5, 0.5, 0.5, origin_round=1)
        h1 = self.m.matrix_hash()
        self.m.save()
        m2 = Matrix(self.dir).load()
        self.assertEqual(h1, m2.matrix_hash())

    def test_hash_changes_on_mutation(self):
        na = self.m.add_node("moth")
        h1 = self.m.matrix_hash()
        self.m.add_node("dawn")
        self.assertNotEqual(h1, self.m.matrix_hash())

    def test_slice_limited_view(self):
        na = self.m.add_node("hub")
        for i in range(8):
            nb = self.m.add_node(f" spoke-{i}")
            self.m.upsert_edge(na, nb, "echoes", 0.5, 0.5, 0.5)
        paper = self.m.slice_for(na, k=3)
        self.assertEqual(len(paper), 3)  # the cell's paper is LIMITED on purpose

    def test_tension_pairs_found(self):
        na, nb = self.m.add_node("a"), self.m.add_node("b")
        self.m.upsert_edge(na, nb, "contradicts", 0.2, 0.9, 0.5)   # high entropy
        self.m.upsert_edge(nb, na, "contradicts", 0.9, 0.2, 0.5)   # high joy
        self.assertEqual(len(self.m.tension_pairs()), 1)

    def test_jev_balance_bounds(self):
        self.assertGreaterEqual(self.m.jev_balance(), 0.0)
        self.assertLessEqual(self.m.jev_balance(), 1.0)

    def test_canon_determinism(self):
        self.assertEqual(canon({"b": 1, "a": 2}), canon({"a": 2, "b": 1}))

    def test_clamp_and_slug(self):
        self.assertEqual(clamp01(1.5), 1.0)
        self.assertEqual(clamp01(-0.1), 0.0)
        self.assertEqual(slugify("Dawn-Chorus!"), "dawn-chorus")


if __name__ == "__main__":
    unittest.main()
