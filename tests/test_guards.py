"""tests/test_guards.py — the cross-run guard registry.

A guard minted in one night must protect its node in every night. These
tests prove: hash-chain integrity, dedup-on-sync, cross-run visibility,
and tamper detection. The registry is the spine; the per-run guards.csv
is muscle memory.
"""

import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from engine.guards import GuardRegistry  # noqa: E402


class TestGuardRegistry(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="guards-test-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.reg_path = os.path.join(self.tmp, "guard_registry.jsonl")

    def test_mint_and_chain(self):
        reg = GuardRegistry(self.reg_path)
        e1 = reg.mint("node-a", 0.7, 3, "night1")
        e2 = reg.mint("node-b", 0.9, 5, "night1")
        e3 = reg.mint("node-a", 0.8, 9, "night2", reason="re-mint")
        self.assertEqual(reg.count(), 3)
        self.assertTrue(reg.chain_ok())
        self.assertEqual({"node-a", "node-b"}, reg.nodes())
        self.assertEqual(e1["prev_hash"], "0" * 64)
        self.assertEqual(e2["prev_hash"], e1["hash"])
        self.assertEqual(e3["prev_hash"], e2["hash"])

    def test_rejects_tamper(self):
        reg = GuardRegistry(self.reg_path)
        reg.mint("node-a", 0.7, 3, "night1")
        reg.mint("node-b", 0.9, 5, "night1")
        lines = open(self.reg_path).read().splitlines()
        bad = json.loads(lines[0])
        bad["strength"] = 0.11  # history rewrite attempt
        lines[0] = json.dumps(bad, sort_keys=True, separators=(",", ":"))
        with open(self.reg_path, "w") as f:
            f.write("\n".join(lines) + "\n")
        reg2 = GuardRegistry(self.reg_path)
        self.assertFalse(reg2.chain_ok())

    def test_sync_from_run_dedups(self):
        run_dir = os.path.join(self.tmp, "night1")
        os.makedirs(run_dir)
        with open(os.path.join(run_dir, "guards.csv"), "w") as f:
            f.write("node,strength,round\nnode-a,0.75,4\nnode-c,0.6,7\n")
        reg = GuardRegistry(self.reg_path)
        n1 = reg.sync_from_run(run_dir, "night1")
        n2 = reg.sync_from_run(run_dir, "night1")  # re-sync imports nothing new
        self.assertEqual(n1, 2)
        self.assertEqual(n2, 0)
        self.assertTrue(reg.chain_ok())
        self.assertEqual(reg.nodes(), {"node-a", "node-c"})

    def test_guards_cross_runs(self):
        """THE property: mint in run A, run B sees the node guarded."""
        runs_root = os.path.join(self.tmp, "runs")
        a_dir, b_dir = os.path.join(runs_root, "a"), os.path.join(runs_root, "b")
        os.makedirs(a_dir)
        os.makedirs(b_dir)
        with open(os.path.join(a_dir, "guards.csv"), "w") as f:
            f.write("node,strength,round\nshared-node,0.8,2\n")
        reg = GuardRegistry(os.path.join(runs_root, "guard_registry.jsonl"))
        reg.sync_from_run(a_dir, "a")
        reg.mint("fresh-node", 0.9, 10, "b")
        # run B's effective guard set: its own csv (empty) ∪ registry
        per_run_b = set()
        effective_b = per_run_b | reg.nodes()
        self.assertIn("shared-node", effective_b)
        self.assertIn("fresh-node", effective_b)

    def test_empty_dir_sync_is_noop(self):
        reg = GuardRegistry(self.reg_path)
        self.assertEqual(reg.sync_from_run(os.path.join(self.tmp, "nope"), "nope"), 0)
        self.assertTrue(reg.chain_ok())
        self.assertEqual(reg.count(), 0)

    def test_malformed_rows_skipped(self):
        run_dir = os.path.join(self.tmp, "nightX")
        os.makedirs(run_dir)
        with open(os.path.join(run_dir, "guards.csv"), "w") as f:
            f.write("node,strength,round\n,0.5,1\nnode-ok,not-a-float,2\nnode-fine,0.4,3\n")
        reg = GuardRegistry(self.reg_path)
        n = reg.sync_from_run(run_dir, "nightX")
        self.assertEqual(n, 1)
        self.assertEqual(reg.nodes(), {"node-fine"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
