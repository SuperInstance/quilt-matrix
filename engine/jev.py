"""engine/jev.py — the JEV bounce: a mechanical walker on the weight graph.

JEV = joy / entropy / value, the triad the whole fleet reads the world
through (si-fleet/jev-quilt lineage). Here the JEV is not a model, not a
prompt — it is a walker: it starts at a node, reads the relational weights
on its paper (edges), picks the next step by softmax attraction, and leaves
a light mechanical trace on every edge it traverses. The path it draws IS a
melody (see engine/music.py) and a chain-of-thought made of place-to-place
motion instead of internal narration.

No LLM anywhere in this file. This is the granular, externalized thinking:
the walker has to draw its links between visible rows because it has no
internal knowledge of the web at all.
"""

from __future__ import annotations
import math

from .matrix import Matrix, clamp01

ATTRACT_J, ATTRACT_V, ATTRACT_E = 0.5, 0.3, 0.2  # joy leads, value steers, entropy wanders
TRACE = 0.02          # how much a traversal nudges the weights
TEMPERATURE = 0.6     # softmax temperature


def _softmax_pick(options: list[tuple[str, float]], rng) -> str:
    if not options:
        raise ValueError("no options to pick from")
    m = max(w for _, w in options)
    exps = [(k, math.exp((w - m) / TEMPERATURE)) for k, w in options]
    z = sum(w for _, w in exps)
    r = rng.random() * z
    acc = 0.0
    for k, w in exps:
        acc += w
        if acc >= r:
            return k
    return exps[-1][0]


def bounce(matrix: Matrix, start_id: str, steps: int, rng) -> dict:
    """Walk the graph. Returns {path, edges_walked, deltas}. Mutates weights
    lightly (TRACE) — the walk is also an act of thinking on the web."""
    assert start_id in matrix.nodes, f"unknown start {start_id}"
    path = [start_id]
    edges_walked: list[str] = []
    cur = start_id
    for _ in range(steps):
        opts: list[tuple[str, float]] = []
        chosen_edge = {}
        for eid, e in matrix.edges.items():
            other = None
            if e["src"] == cur:
                other = e["dst"]
            elif e["dst"] == cur:
                other = e["src"]
            if other is None:
                continue
            attract = (ATTRACT_J * e["joy"] + ATTRACT_V * e["value"]
                       + ATTRACT_E * e["entropy"])
            opts.append((other, attract))
            chosen_edge[other] = eid
        if not opts:
            break  # walker reached a leaf: stops, honestly
        nxt = _softmax_pick(opts, rng)
        eid = chosen_edge[nxt]
        e = matrix.edges[eid]
        # light trace: walking a joyful edge makes it a touch more joyful,
        # walking an entropic edge raises its visibility for future walkers
        e["joy"] = clamp01(e["joy"] + TRACE * (1 - e["joy"]))
        e["value"] = clamp01(e["value"] + TRACE / 2)
        edges_walked.append(eid)
        path.append(nxt)
        cur = nxt
    return {"path": path, "edges_walked": edges_walked, "steps": len(edges_walked)}


def web_stats(matrix: Matrix) -> dict:
    """Mechanical read of the web's JEV state — the thing the leaderboard and
    the music mappings both consume."""
    n = len(matrix.nodes)
    e = len(matrix.edges)
    if n == 0:
        return {"nodes": 0, "edges": 0, "density": 0.0, "balance": 0.0}
    max_possible = n * (n - 1) / 2
    return {
        "nodes": n,
        "edges": e,
        "density": round(e / max_possible, 4) if max_possible else 0.0,
        "balance": round(matrix.jev_balance(), 4),
        "tensions": len(matrix.tension_pairs()),
    }
