"""tests/test_pool_gate.py — the vast question index + the mechanical gates."""

import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "scripts"))

from questions.build_pool import build_pool, load_index, spec_sha  # noqa: E402
from engine.matrix import Matrix                                   # noqa: E402
from engine.receipts import ScarLog                                # noqa: E402
from run_rounds import apply_family, gate_candidate                # noqa: E402


class TestPool(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p1 = build_pool([], seed=42)
        cls.p2 = build_pool([], seed=42)

    def test_vast(self):
        """'Vast' is a receipted number: the pool must exceed 400 instances."""
        self.assertGreater(len(self.p1), 400)

    def test_all_families_present(self):
        fams = {r["family"] for r in self.p1}
        self.assertEqual(fams, {"REL-BOND", "DECOMP", "BRIDGE", "TENSION", "TMSEQ",
                                "SOUND", "MOTHDRIFT", "GUARD", "ECHO", "PLAY"})

    def test_deterministic(self):
        self.assertEqual(
            [json.dumps(r, sort_keys=True) for r in self.p1],
            [json.dumps(r, sort_keys=True) for r in self.p2])

    def test_spec_sha_stable_and_short(self):
        idx = load_index()
        for fam in idx["families"]:
            s = spec_sha(fam)
            self.assertEqual(len(s), 16)
            self.assertEqual(s, spec_sha(fam))  # stable within process

    def test_unique_qids(self):
        ids = [r["qid"] for r in self.p1]
        self.assertEqual(len(ids), len(set(ids)))

    def test_rel_bond_questions_fully_instantiated(self):
        row = next(r for r in self.p1 if r["family"] == "REL-BOND")
        self.assertNotIn("{a}", row["questions"]["resonates"]["instructions"])
        self.assertNotIn("{b}", row["questions"]["strength"]["instructions"])
        self.assertEqual(len(row["questions"]), 3)  # batched System One pass


class TestGates(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.m = Matrix(os.path.join(self.dir, "matrix"))
        self.m.add_node("moth")
        self.m.add_node("dawn")
        self.scars = ScarLog(os.path.join(self.dir, "scars.jsonl"))
        self.aux = {"sound": ([], None), "guards": ([], None), "games": ([], None)}

    def test_gate_self_loop(self):
        ok, why = gate_candidate(self.m, "REL-BOND", {"a": "moth", "b": "moth"}, set())
        self.assertFalse(ok)
        self.assertEqual(why, "self loop")

    def test_gate_missing_endpoint(self):
        ok, why = gate_candidate(self.m, "REL-BOND", {"a": "moth", "b": "nope"}, set())
        self.assertFalse(ok)
        self.assertIn("not in matrix", why)

    def test_gate_pass(self):
        ok, why = gate_candidate(self.m, "REL-BOND", {"a": "moth", "b": "dawn"}, set())
        self.assertTrue(ok)

    def test_guard_gate_refuses_unprovened_write(self):
        """Wave-69 spec-gate, miniaturized: guarded node + no question_id →
        refused AND scarred (never silently dropped)."""
        row = {"qid": "", "family": "REL-BOND", "slots": {"a": "moth", "b": "dawn"}}
        aux = {"sound": ([], None), "guards": ([{"node": "moth"}], None),
               "games": ([], None)}
        answers = {"resonates": {"noul": 0.9}, "contradicts": {"noul": 0.1},
                   "strength": {"score": 3}}
        out = apply_family("REL-BOND", row, answers, self.m, 1, self.scars, aux)
        self.assertEqual(out.get("refused"), "spec-missing")
        self.assertEqual(self.scars.reasons().get("spec-missing"), 1)
        self.assertEqual(len(self.m.edges), 0)  # nothing written

    def test_rel_bond_bind_writes_weighted_edge(self):
        row = {"qid": "REL-BOND:1", "slots": {"a": "moth", "b": "dawn"}}
        answers = {"resonates": {"noul": 0.82}, "contradicts": {"noul": 0.11},
                   "strength": {"score": 3}}
        out = apply_family("REL-BOND", row, answers, self.m, 4, self.scars, self.aux)
        self.assertEqual(out["rel"], "resonates")
        self.assertAlmostEqual(out["joy"], 0.82)
        self.assertIn("moth->dawn:resonates", self.m.edges)
        self.assertAlmostEqual(self.m.edges["moth->dawn:resonates"]["value"], 0.75)

    def test_tmseq_bind_mints_stage_nodes(self):
        row = {"qid": "TMSEQ:1", "slots": {"a": "quilt", "b": "stage-x", "c": "stage-y"}}
        answers = {"before": {"noul": 0.9}}
        out = apply_family("TMSEQ", row, answers, self.m, 5, self.scars, self.aux)
        self.assertIn("stage-x", self.m.nodes)
        self.assertIn("stage-y", self.m.nodes)
        self.assertIn("stage-x->stage-y:tminus", self.m.edges)

    def test_echo_bind_scars_on_instability(self):
        self.m.add_node("song")
        row = {"qid": "ECHO:1", "slots": {"a": "moth", "b": "song"}}
        answers = {"p1": {"noul": 0.9}, "p2": {"noul": 0.2}}
        out = apply_family("ECHO", row, answers, self.m, 6, self.scars, self.aux)
        self.assertTrue(out.get("scarred"))
        self.assertEqual(self.scars.reasons().get("oracle-instability"), 1)

    def test_tension_bind_confirm_and_scar_paths(self):
        self.m.upsert_edge("moth", "dawn", "resonates", 0.5, 0.5, 0.5)
        eid = "moth->dawn:resonates"
        # low suspicion → confirm bump
        row = {"qid": "TENSION:1", "slots": {"a": "moth", "b": "dawn", "edge_id": eid,
                                             "rel": "resonates", "joy": 0.5,
                                             "entropy": 0.5, "value": 0.5}}
        apply_family("TENSION", row, {"suspicious": {"noul": 0.2},
                                      "repairable": {"score": 2}},
                     self.m, 7, self.scars, self.aux)
        self.assertAlmostEqual(self.m.edges[eid]["value"], 0.52)
        # high suspicion → scar + entropy bump
        row2 = {**row, "qid": "TENSION:2"}
        out = apply_family("TENSION", row2, {"suspicious": {"noul": 0.9},
                                             "repairable": {"score": 3}},
                           self.m, 8, self.scars, self.aux)
        self.assertTrue(out.get("scarred"))
        self.assertAlmostEqual(self.m.edges[eid]["entropy"], 0.6)
        self.assertEqual(self.scars.reasons().get("tension-audit"), 1)


if __name__ == "__main__":
    unittest.main()
