"""engine/guards.py — the cross-run guard registry.

The per-run guards.csv is muscle memory: it guards nodes within one night.
The registry is the spine: a guard minted in ANY run protects that node in
EVERY run, because a node earned its guard as a node of the web, not as a
row of one night's CSV. Synced in at bootstrap, appended to at mint time,
consulted by every gate.

Sticky law (Wave-69): append-only and hash-chained, never truncated, never
rewound. Rewinds restore matrices; guards survive them — they are the
gatekeepers of the scar tissue. (Scars remember the failures; guards refuse
the next one.)
"""

from __future__ import annotations
import csv
import hashlib
import json
import os
import time

GENESIS = "0" * 64


def _entry_hash(prev_hash: str, entry: dict) -> str:
    body = json.dumps({k: entry[k] for k in sorted(entry)},
                      sort_keys=True, separators=(",", ":"))
    return hashlib.sha256((prev_hash + body).encode()).hexdigest()


class GuardRegistry:
    """Append-only, hash-chained ledger of guarded nodes across runs."""

    def __init__(self, path: str):
        self.path = path
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        self.lines: list[dict] = []
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                self.lines = [json.loads(x) for x in f if x.strip()]

    def _prev(self) -> str:
        return self.lines[-1]["hash"] if self.lines else GENESIS

    def mint(self, node: str, strength: float, round_no: int, run: str,
             reason: str = "guard-question") -> dict:
        e = {"node": node, "strength": strength, "round": round_no, "run": run,
             "reason": reason, "prev_hash": self._prev(),
             "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        e["hash"] = _entry_hash(self._prev(), e)
        self.lines.append(e)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(e, sort_keys=True, separators=(",", ":")) + "\n")
        return e

    def sync_from_run(self, run_dir: str, run_name: str) -> int:
        """Import per-run guards.csv rows not yet in the registry (dedup by
        node: first mint wins, later re-mints are the run's own business).
        Returns count imported."""
        p = os.path.join(run_dir, "guards.csv")
        if not os.path.exists(p):
            return 0
        known = self.nodes()
        imported = 0
        with open(p, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                node = (row.get("node") or "").strip()
                if not node or node in known:
                    continue
                try:
                    strength = float(row.get("strength") or 0.5)
                    rnd = int(row.get("round") or 0)
                except ValueError:
                    continue
                self.mint(node, strength, rnd, run_name, reason="sync-from-run")
                known.add(node)
                imported += 1
        return imported

    def nodes(self) -> set[str]:
        return {e["node"] for e in self.lines}

    def count(self) -> int:
        return len(self.lines)

    def chain_ok(self) -> bool:
        prev = GENESIS
        for e in self.lines:
            if e.get("prev_hash") != prev:
                return False
            body = {k: v for k, v in e.items() if k != "hash"}
            if _entry_hash(prev, body) != e.get("hash"):
                return False
            prev = e["hash"]
        return True
