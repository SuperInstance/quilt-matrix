"""engine/die.py — Deterministic Stochasticity: the Die Engine.

Wave-69 invariant, carried into the quilt matrix: when the system deadlocks
(cell INDETERMINATE twice, oracle unreachable twice, sensor failure), it does
NOT raise a standard exception — it rolls a pure-function d20 and applies a
STRUCTURAL drift move appropriate to the face. Determinism: same seed → same
face, forever, testable. Entropy: the seed is fed by real moth quantum bits
when the moth channel is alive, else by the matrix hash (receipted either
way — never silent).

The bias lesson from wave-69 is honored: faces come from a big-int modulo of
a sha256 stream, no float quantization anywhere.
"""

from __future__ import annotations
import hashlib

BUCKETS = {
    "scar_backoff":   range(1, 6),    # 1-5  candidate rejected harder + scar
    "entropy_jitter": range(6, 10),   # 6-9  sprinkle ±0.05 on random edge weights
    "node_fission":   range(10, 14),  # 10-13 split a node label into two
    "edge_rewire":    range(14, 18),  # 14-17 move one endpoint to a neighbor
    "moth_edge":      range(18, 20),  # 18-19 add a drift edge (moth-style)
    "double_or_bust": range(20, 21),  # 20   jitter AND rewire
}


def d20(seed: str) -> int:
    """Pure function: seed in, face out. 1..20. No state, no dice object."""
    h = hashlib.sha256(seed.encode()).digest()
    return int.from_bytes(h[:8], "big") % 20 + 1


def bucket(face: int) -> str:
    for name, rng in BUCKETS.items():
        if face in rng:
            return name
    raise ValueError(f"face {face} out of range")


def die_seed(moth_hex: str | None, matrix_hash: str, round_no: int, tag: str) -> str:
    """Entropy provenance is part of the seed string itself — receipted by
    construction. moth:… = quantum-sourced; sha:… = deterministic fallback."""
    if moth_hex:
        return f"moth:{moth_hex}:r{round_no}:{tag}:{matrix_hash[:16]}"
    return f"sha:r{round_no}:{tag}:{matrix_hash[:32]}"


def drift_plan(face: int, matrix, rng) -> list[dict]:
    """Translate a die face into mechanical mutations. The matrix passed in is
    read-only here; the runner applies the plan (and receipts it)."""
    import random
    b = bucket(face)
    plan: list[dict] = []
    edge_ids = sorted(matrix.edges)
    node_ids = sorted(matrix.nodes)

    def rand_edge():
        return rng.choice(edge_ids) if edge_ids else None

    if b in ("entropy_jitter", "double_or_bust"):
        e = rand_edge()
        if e:
            plan.append({"op": "jitter", "edge": e,
                         "d_joy": round(rng.uniform(-0.05, 0.05), 4),
                         "d_entropy": round(rng.uniform(-0.05, 0.05), 4)})
    if b in ("node_fission",):
        n = rng.choice(node_ids) if node_ids else None
        if n:
            plan.append({"op": "fission", "node": n,
                         "new_label": matrix.nodes[n]["label"] + "-bloom"})
    if b in ("edge_rewire", "double_or_bust"):
        e = rand_edge()
        if e and node_ids:
            new_dst = rng.choice(node_ids)
            if new_dst != matrix.edges[e]["src"]:
                plan.append({"op": "rewire", "edge": e, "new_dst": new_dst})
    if b == "moth_edge":
        a = rng.choice(node_ids) if node_ids else None
        c = rng.choice(node_ids) if node_ids else None
        if a and c and a != c:
            plan.append({"op": "add_edge", "src": a, "dst": c, "rel_type": "echoes",
                         "joy": 0.4, "entropy": 0.7, "value": 0.3,
                         "note": "die:moth_edge drift"})
    if b == "scar_backoff":
        plan.append({"op": "scar_backoff"})
    return plan
