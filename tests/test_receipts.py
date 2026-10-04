"""tests/test_receipts.py — sticky receipts: hash chain + scars survive rewind."""

import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from engine.matrix import Matrix           # noqa: E402
from engine.receipts import (Ledger, ScarLog,  # noqa: E402
                             rewind, snapshot)


class TestLedger(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "receipts.jsonl")

    def test_chain_verifies(self):
        led = Ledger(self.path)
        for i in range(10):
            led.append("mutation", i, {"i": i}, f"hash{i}")
        ok, n = led.verify()
        self.assertTrue(ok)
        self.assertEqual(n, 10)

    def test_chain_links(self):
        led = Ledger(self.path)
        led.append("a", 1, {}, "h1")
        led.append("b", 2, {}, "h2")
        self.assertEqual(led.lines[1]["prev_hash"], led.lines[0]["hash"])

    def test_tamper_detected(self):
        led = Ledger(self.path)
        for i in range(5):
            led.append("mutation", i, {"i": i}, "h")
        # tamper with a payload on disk
        lines = [json.loads(x) for x in open(self.path)]
        lines[2]["payload"]["i"] = 999
        with open(self.path, "w") as f:
            f.write("\n".join(json.dumps(x) for x in lines) + "\n")
        ok, at = Ledger(self.path).verify()
        self.assertFalse(ok)
        self.assertEqual(at, 2)

    def test_reload_continues_chain(self):
        Ledger(self.path).append("a", 1, {}, "h1")
        led2 = Ledger(self.path)
        led2.append("b", 2, {}, "h2")
        ok, n = led2.verify()
        self.assertTrue(ok)
        self.assertEqual(n, 2)


class TestStickyScars(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.run = os.path.join(self.dir, "run")
        self.mroot = os.path.join(self.run, "matrix")
        self.snaps = os.path.join(self.run, "snapshots")
        os.makedirs(self.mroot)
        os.makedirs(self.snaps)

    def test_scars_survive_rewind(self):
        """THE invariant. Mutate → snapshot → more mutations + scars →
        rewind → matrix is old, scars are ALL still there."""
        m = Matrix(self.mroot)
        m.add_node("moth")
        m.save()
        snapshot(self.mroot, self.snaps, 1)

        m2 = Matrix(self.mroot).load()
        m2.add_node("scar-tissue")
        m2.save()
        scars = ScarLog(os.path.join(self.run, "scars.jsonl"))
        scars.scar(2, "test-failure", {"detail": "x"})
        scars.scar(3, "oracle-instability", {"delta": 0.4})

        rewind(self.mroot, self.snaps, 1)
        m3 = Matrix(self.mroot).load()
        self.assertNotIn("scar-tissue", m3.nodes)     # matrix went back
        self.assertEqual(ScarLog(  # ...but the scars STAYED (sticky law)
            os.path.join(self.run, "scars.jsonl")).count(), 2)

    def test_scar_log_append_only_on_disk(self):
        p = os.path.join(self.dir, "scars.jsonl")
        s1 = ScarLog(p)
        s1.scar(1, "a", {})
        raw1 = open(p).read()
        s2 = ScarLog(p)
        s2.scar(2, "b", {})
        raw2 = open(p).read()
        self.assertTrue(raw2.startswith(raw1))  # append-only, byte-prefix law

    def test_scar_reasons_aggregate(self):
        p = os.path.join(self.dir, "scars.jsonl")
        s = ScarLog(p)
        s.scar(1, "x", {})
        s.scar(2, "x", {})
        s.scar(3, "y", {})
        self.assertEqual(s.reasons(), {"x": 2, "y": 1})


if __name__ == "__main__":
    unittest.main()
