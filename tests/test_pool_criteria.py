"""tests/test_pool_criteria.py — regression for the silent-422 bug.

Night 3's oracle-fail receipts led to the diagnosis: the generic pool branch
copied type+instructions but dropped criteria, so every GUARD score question
was rejected by the oracle (422) in EVERY night since the pool existed — and
no guard was ever minted. Law now frozen: every score/choice question in
every pool row must carry criteria, and the pool must validate as a whole.
"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from questions.build_pool import build_pool, load_index, spec_sha  # noqa: E402

NEEDS_CRITERIA = ("score", "choice")


class TestPoolCriteria(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pool = build_pool([f"word{i:02d}" for i in range(16)], seed=1234)

    def test_every_score_or_choice_has_criteria(self):
        bad = []
        for row in self.pool:
            for name, q in row["questions"].items():
                if q["type"] in NEEDS_CRITERIA and "criteria" not in q:
                    bad.append(f'{row["qid"]}.{name}')
        self.assertEqual(bad, [], f"questions missing criteria: {bad[:8]}")

    def test_guard_rows_specifically_carry_criteria(self):
        guard = [r for r in self.pool if r["family"] == "GUARD"]
        self.assertTrue(guard, "pool has no GUARD rows")
        for row in guard:
            self.assertIn("criteria", row["questions"]["guard_strength"])

    def test_decomp_rows_carry_criteria_when_index_declares_it(self):
        idx = load_index()
        dec = next(f for f in idx["families"] if f["id"] == "DECOMP")
        declared = {k for k, v in dec["questions"].items() if "criteria" in v}
        rows = [r for r in self.pool if r["family"] == "DECOMP"]
        self.assertTrue(rows)
        for row in rows:
            for k in declared:
                self.assertIn("criteria", row["questions"][k])

    def test_spec_sha_untouched_by_criteria_fix(self):
        """Anti-post-hoc law: the fix must not have moved any spec seal."""
        idx = load_index()
        for fam in idx["families"]:
            self.assertTrue(spec_sha(fam))

    def test_noul_questions_need_no_criteria(self):
        """The rule is asymmetric: noul stays criteria-free (proven by the
        families that always worked — ECHO, TENSION, SOUND, REL-BOND)."""
        seen = 0
        for row in self.pool:
            for q in row["questions"].values():
                if q["type"] == "noul":
                    seen += 1
        self.assertGreater(seen, 100)


if __name__ == "__main__":
    unittest.main(verbosity=2)
