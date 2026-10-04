"""engine/matrix.py — the external brain: a spreadsheet-viewable neural network.

Design law (Wave-69+ quilt-growing sprint, principal directive 2026-10-04):
  "the system self-decomposes into relational weights that the JEV can bounce
   around adding more to a mechanical bot's Neural network of parameters on
   their matrix of simulated ideas in pure external spreadsheet viewable
   weights and the logic between them."

Translation into this file:
  - nodes.csv  = ideas. Each row: id,label,joy,entropy,value,origin_round,created_by,note
  - edges.csv  = the logic between them. Each row:
                 edge_id,src,dst,rel_type,joy,entropy,value,origin_round,created_by,question_id,note
  - NO weights live inside any model. Models (typesafe oracle, small cells)
    are temporary visitors; the CSVs are the permanent mind. A mechanical bot
    (pure Python, zero deps) is the only thing allowed to write rows.

Everything is openable in Excel/LibreOffice — that is not a convenience, it is
the point: the parameters exist OUTSIDE the agent, in savable, rewindable,
human-inspectable form.
"""

from __future__ import annotations
import csv
import hashlib
import json
import math
import os
import re

NODE_COLS = ["id", "label", "joy", "entropy", "value", "origin_round", "created_by", "note"]
EDGE_COLS = ["edge_id", "src", "dst", "rel_type", "joy", "entropy", "value",
             "origin_round", "created_by", "question_id", "note"]
REL_TYPES = ["supports", "contradicts", "resonates", "transforms", "feeds",
             "guards", "tminus", "echoes", "plays", "sounds", "bridges"]
SCAR_RELS = {"contradicts"}  # rels that count toward tension checks


def clamp01(x: float) -> float:
    return max(0.0, min(1.0, float(x)))


def slugify(label: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")
    return s or "node"


def canon(obj) -> str:
    """Canonical JSON for hashing — stable across runs and machines."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


class Matrix:
    """Load/modify/save the two-sheet external brain. Zero dependencies."""

    def __init__(self, root: str):
        self.root = root
        os.makedirs(root, exist_ok=True)
        self.nodes_path = os.path.join(root, "nodes.csv")
        self.edges_path = os.path.join(root, "edges.csv")
        self.nodes: dict[str, dict] = {}
        self.edges: dict[str, dict] = {}

    # ---------- persistence ----------
    def load(self) -> "Matrix":
        self.nodes, self.edges = {}, {}
        if os.path.exists(self.nodes_path):
            with open(self.nodes_path, newline="", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    row["origin_round"] = int(row["origin_round"])
                    for k in ("joy", "entropy", "value"):
                        row[k] = float(row[k])
                    self.nodes[row["id"]] = row
        if os.path.exists(self.edges_path):
            with open(self.edges_path, newline="", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    row["origin_round"] = int(row["origin_round"])
                    for k in ("joy", "entropy", "value"):
                        row[k] = float(row[k])
                    self.edges[row["edge_id"]] = row
        return self

    def save(self) -> None:
        # The spreadsheet IS the artifact: sorted for stable diffs.
        with open(self.nodes_path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=NODE_COLS)
            w.writeheader()
            for nid in sorted(self.nodes):
                w.writerow(self.nodes[nid])
        with open(self.edges_path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=EDGE_COLS)
            w.writeheader()
            for eid in sorted(self.edges):
                w.writerow(self.edges[eid])

    # ---------- identity ----------
    def matrix_hash(self) -> str:
        return hashlib.sha256(canon({"n": self.nodes, "e": self.edges}).encode()).hexdigest()

    # ---------- mutations (mechanical bot only) ----------
    def add_node(self, label: str, joy=0.5, entropy=0.5, value=0.5,
                 origin_round=0, created_by="seed", note="") -> str:
        base = slugify(label)
        nid, i = base, 2
        while nid in self.nodes:
            # same label reused → same node (idempotent); new label → suffix
            if self.nodes[nid]["label"] == label:
                return nid
            nid, i = f"{base}-{i}", i + 1
        self.nodes[nid] = {"id": nid, "label": label, "joy": clamp01(joy),
                           "entropy": clamp01(entropy), "value": clamp01(value),
                           "origin_round": int(origin_round), "created_by": created_by,
                           "note": note}
        return nid

    def has_edge(self, src: str, dst: str, rel_type: str) -> bool:
        return f"{src}->{dst}:{rel_type}" in self.edges

    def upsert_edge(self, src: str, dst: str, rel_type: str, joy, entropy, value,
                    origin_round=0, created_by="seed", question_id="", note="") -> str:
        assert rel_type in REL_TYPES, f"bad rel_type {rel_type}"
        assert src in self.nodes and dst in self.nodes, "edge endpoints must exist"
        eid = f"{src}->{dst}:{rel_type}"
        if eid in self.edges:
            row = self.edges[eid]
            row["joy"] = clamp01(0.5 * row["joy"] + 0.5 * float(joy))       # merge, not stomp
            row["entropy"] = clamp01(0.5 * row["entropy"] + 0.5 * float(entropy))
            row["value"] = clamp01(0.5 * row["value"] + 0.5 * float(value))
            row["question_id"] = question_id or row["question_id"]
            row["note"] = note or row["note"]
        else:
            self.edges[eid] = {"edge_id": eid, "src": src, "dst": dst, "rel_type": rel_type,
                               "joy": clamp01(joy), "entropy": clamp01(entropy),
                               "value": clamp01(value), "origin_round": int(origin_round),
                               "created_by": created_by, "question_id": question_id, "note": note}
        return eid

    def remove_edge(self, edge_id: str) -> None:
        self.edges.pop(edge_id, None)  # used only by drift; receipts remember

    # ---------- paper (the deliberately-limited view cells read) ----------
    def slice_for(self, node_id: str, k: int = 6) -> list[dict]:
        """The cell's 'paper': incident edges + neighbor labels. Context is
        limited ON PURPOSE — the thinker must draw links on paper, not feel
        them internally."""
        out = []
        for e in self.edges.values():
            if e["src"] == node_id or e["dst"] == node_id:
                other = e["dst"] if e["src"] == node_id else e["src"]
                out.append({"edge": f'{e["rel_type"]}({self.nodes[other]["label"]})',
                            "joy": round(e["joy"], 3), "entropy": round(e["entropy"], 3),
                            "value": round(e["value"], 3)})
            if len(out) >= k:
                break
        return out

    def neighbor_ids(self, node_id: str) -> list[str]:
        acc = []
        for e in self.edges.values():
            if e["src"] == node_id:
                acc.append(e["dst"])
            elif e["dst"] == node_id:
                acc.append(e["src"])
        return sorted(set(acc))

    def concepts(self, k: int, rng) -> list[str]:
        ids = sorted(self.nodes)
        rng.shuffle(ids)
        return [self.nodes[i]["label"] for i in ids[:k]]

    # ---------- mechanical analytics ----------
    def tension_pairs(self) -> list[str]:
        """Edges that both support and contradict the same pair with weight —
        the web's own contradictions, found mechanically."""
        bad = []
        for e in self.edges.values():
            if e["rel_type"] in SCAR_RELS and e["entropy"] > 0.6:
                rev = f'{e["dst"]}->{e["src"]}:{e["rel_type"]}'
                if rev in self.edges and self.edges[rev]["joy"] > 0.6:
                    bad.append(e["edge_id"])
        return bad

    def jev_balance(self) -> float:
        """1.0 = perfectly balanced web; penalize one-axis dominance."""
        if not self.nodes:
            return 0.0
        js = [n["joy"] for n in self.nodes.values()]
        es = [n["entropy"] for n in self.nodes.values()]
        m = lambda xs: sum(xs) / len(xs)
        var = lambda xs: sum((x - m(xs)) ** 2 for x in xs) / len(xs)
        return clamp01(1.0 - (math.sqrt(var(js)) + math.sqrt(var(es))) / 2.0)
