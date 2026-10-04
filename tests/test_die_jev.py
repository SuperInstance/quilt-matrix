"""tests/test_die_jev.py — the Die Engine's determinism + the walker's laws."""

import os
import random
import sys
import tempfile
import unittest
from collections import Counter

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from engine import die, jev                      # noqa: E402
from engine.matrix import Matrix                 # noqa: E402


class TestDie(unittest.TestCase):
    def test_determinism(self):
        for seed in ("moth:abc", "sha:r1:x", "edge-case-ü"):
            self.assertEqual(die.d20(seed), die.d20(seed))

    def test_range(self):
        for i in range(500):
            f = die.d20(f"seed-{i}")
            self.assertTrue(1 <= f <= 20, f"face {f} out of range")

    def test_distribution_no_quantization_bias(self):
        """The wave-69 lesson: no float bit-truncation bias allowed.
        20k rolls, expected 1000/face; accept [860, 1140]."""
        c = Counter(die.d20(f"dist-{i}") for i in range(20_000))
        for face in range(1, 21):
            self.assertTrue(860 <= c[face] <= 1140,
                            f"face {face}: {c[face]} (bias?)")

    def test_bucket_mapping(self):
        self.assertEqual(die.bucket(1), "scar_backoff")
        self.assertEqual(die.bucket(20), "double_or_bust")
        self.assertEqual(die.bucket(10), "node_fission")

    def test_seed_provenance_encoded(self):
        s = die.die_seed("ff0a", "mhash", 3, "deadlock")
        self.assertTrue(s.startswith("moth:"))
        s2 = die.die_seed(None, "mhash", 3, "deadlock")
        self.assertTrue(s2.startswith("sha:"))

    def test_drift_plan_shapes(self):
        m = Matrix(tempfile.mkdtemp())
        for w in ("a", "b", "c", "d"):
            m.add_node(w)
        m.upsert_edge("a", "b", "echoes", 0.5, 0.5, 0.5)
        for face in range(1, 21):
            plan = die.drift_plan(face, m, random.Random(face))
            for step in plan:
                self.assertIn(step["op"], {"jitter", "fission", "rewire",
                                           "add_edge", "scar_backoff"})


class TestJev(unittest.TestCase):
    def setUp(self):
        self.m = Matrix(tempfile.mkdtemp())
        ids = [self.m.add_node(w) for w in ("joy", "entropy", "value", "moth", "song")]
        for i in range(len(ids) - 1):
            self.m.upsert_edge(ids[i], ids[i + 1], "resonates", 0.6, 0.3, 0.5)

    def test_bounce_deterministic(self):
        w1 = jev.bounce(self.m, "joy", 5, random.Random(7))
        w2 = jev.bounce(self.m, "joy", 5, random.Random(7))
        self.assertEqual(w1["path"], w2["path"])
        self.assertEqual(w1["edges_walked"], w2["edges_walked"])

    def test_bounce_stops_at_leaf_honestly(self):
        self.m.add_node("island")  # no edges at all — an honest dead end
        w = jev.bounce(self.m, "island", 5, random.Random(1))
        self.assertEqual(w["path"], ["island"])
        self.assertEqual(w["steps"], 0)

    def test_trace_moves_weights(self):
        before = self.m.edges["joy->entropy:resonates"]["joy"]
        jev.bounce(self.m, "joy", 3, random.Random(3))
        after = self.m.edges["joy->entropy:resonates"]["joy"]
        self.assertGreater(after, before)  # walking raises joy, gently

    def test_web_stats_shape(self):
        st = jev.web_stats(self.m)
        self.assertEqual(st["nodes"], 5)
        self.assertEqual(st["edges"], 4)
        self.assertIn("balance", st)
        self.assertIn("tensions", st)


if __name__ == "__main__":
    unittest.main()
