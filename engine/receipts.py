"""engine/receipts.py — sticky receipts: append-only, hash-chained, rewind-proof.

Wave-69 invariant "Scars Survive Rewind", carried into the quilt-growing
sprint: the ledger is a hash chain (tamper-evident), and the scar log is
append-only FOREVER — rewinding the matrix to an earlier snapshot never
deletes a scar. Failures are first-class citizens of the mind.
"""

from __future__ import annotations
import hashlib
import json
import os
import time

from .matrix import canon

GENESIS = "0" * 64


class Ledger:
    """Hash-chained receipt log (receipts.jsonl)."""

    def __init__(self, path: str):
        self.path = path
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.lines: list[dict] = []
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                self.lines = [json.loads(x) for x in f if x.strip()]

    def append(self, kind: str, round_no: int, payload: dict, matrix_hash: str) -> dict:
        prev = self.lines[-1]["hash"] if self.lines else GENESIS
        line = {"idx": len(self.lines), "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "kind": kind, "round": round_no, "payload": payload,
                "matrix_hash": matrix_hash, "prev_hash": prev}
        line["hash"] = hashlib.sha256((canon(line) + prev).encode()).hexdigest()
        self.lines.append(line)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(line, sort_keys=True, separators=(",", ":")) + "\n")
        return line

    def verify(self) -> tuple[bool, int]:
        prev = GENESIS
        for i, line in enumerate(self.lines):
            expect = {k: v for k, v in line.items() if k != "hash"}
            h = hashlib.sha256((canon(expect) + prev).encode()).hexdigest()
            if line.get("hash") != h or line.get("prev_hash") != prev or line.get("idx") != i:
                return False, i
            prev = h
        return True, len(self.lines)

    def count_kind(self, kind: str) -> int:
        return sum(1 for x in self.lines if x["kind"] == kind)


class ScarLog:
    """Sticky scars. Append-only, never truncated, never rewound.

    "Sticky" law: any procedure that restores earlier state (snapshot rewind,
    candidate rejection, drift rollback) MUST leave this file untouched. A
    scar is the memory of a failure; a mind that deletes its failures is
    doomed to re-fail them (and its cost accounting would lie).
    """

    def __init__(self, path: str):
        self.path = path
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.lines: list[dict] = []
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                self.lines = [json.loads(x) for x in f if x.strip()]

    def scar(self, round_no: int, reason: str, payload: dict) -> dict:
        s = {"idx": len(self.lines), "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
             "round": round_no, "reason": reason, "payload": payload}
        self.lines.append(s)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(s, sort_keys=True, separators=(",", ":")) + "\n")
        return s

    def count(self) -> int:
        return len(self.lines)

    def reasons(self) -> dict:
        acc: dict[str, int] = {}
        for s in self.lines:
            acc[s["reason"]] = acc.get(s["reason"], 0) + 1
        return acc


def snapshot(matrix_root: str, snaps_dir: str, round_no: int) -> str:
    """Copy the two-sheet matrix into runs/<run>/snapshots/round_XXXX/."""
    dst = os.path.join(snaps_dir, f"round_{round_no:04d}")
    os.makedirs(dst, exist_ok=True)
    for name in ("nodes.csv", "edges.csv"):
        src = os.path.join(matrix_root, name)
        if os.path.exists(src):
            with open(src, encoding="utf-8") as a, open(os.path.join(dst, name), "w", encoding="utf-8") as b:
                b.write(a.read())
    return dst


def rewind(matrix_root: str, snaps_dir: str, to_round: int) -> str:
    """Non-destructive restore: matrix CSVs go back; scars + receipts do NOT."""
    src = os.path.join(snaps_dir, f"round_{to_round:04d}")
    assert os.path.isdir(src), f"no snapshot for round {to_round}"
    for name in ("nodes.csv", "edges.csv"):
        p = os.path.join(src, name)
        if os.path.exists(p):
            with open(p, encoding="utf-8") as a, open(os.path.join(matrix_root, name), "w", encoding="utf-8") as b:
                b.write(a.read())
    return src
