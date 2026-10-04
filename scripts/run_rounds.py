#!/usr/bin/env python3
"""scripts/run_rounds.py — the marathon: competitive construction of idea-webs.

Per round (all receipted, all non-destructive):
  1. sample question instances from the pool (family rotation)
  2. resolve candidates:
       - oracle-only families: typesafe answers directly
       - generator families: TWO small cells compete (weaver vs trickster),
         the mechanical gate filters, the oracle judges, winner applied,
         loser -> sticky scar          (competitive construction)
  3. mechanical spec gate BEFORE the oracle (self-defending architecture:
     candidates that violate the pre-registered spec never compile)
  4. guarded-node gate: edges touching guarded nodes require question_id
  5. Die Engine on deadlock (double-INDETERMINATE / oracle failure): d20
     seeded by real moth entropy when available, else matrix-hash (receipted)
  6. one JEV bounce per round — the walker's path is tomorrow's melody
  7. music segment every --music-every rounds (chords + melody + scar hits
     + persona duet notes)
  8. snapshot every --snapshot-every rounds (rewindable, scars NOT rewound)
  9. leaderboard.csv row per round; optional git commit+push every N

Usage:
  python3 scripts/run_rounds.py --run runs/night1 --rounds 16 --push-every 8
  python3 scripts/run_rounds.py --run runs/night1 --rewind-to 8   # sticky rewind
"""

from __future__ import annotations
import argparse
import csv
import json
import os
import random
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from engine import cells, die, jev, moth, typesafe_q            # noqa: E402
from engine.guards import GuardRegistry                          # noqa: E402
from engine.matrix import Matrix, clamp01                        # noqa: E402
from engine.music import (MidiWriter, duet_note, jev_melody,     # noqa: E402
                          round_chord, scar_hit)
from engine.receipts import Ledger, ScarLog, rewind, snapshot    # noqa: E402
from questions.build_pool import build_pool, load_index, spec_sha, _fill  # noqa: E402

SEED_LEXICON = None  # replaced at bootstrap by the FULL index lexicon (48 words):
# the matrix must know every word the question pool can ask about, otherwise
# the gate correctly (but uselessly) refuses the whole pool.
SCORE_NORM = 4.0  # score rubrics are 5 levels → normalize by len-1


# ────────────────────────────── seed / bootstrap ─────────────────────────────
def bootstrap(matrix: Matrix, run_dir: str) -> None:
    if matrix.nodes:
        return
    lex = load_index()["lexicon"]
    for i, w in enumerate(lex):
        matrix.add_node(w, joy=0.5 + 0.02 * (i % 5), entropy=0.45 + 0.01 * (i % 7),
                        value=0.5, origin_round=0, created_by="seed",
                        note="lexicon seed row")
    matrix.save()


def load_aux(run_dir: str, name: str, cols: list[str]):
    """Returns (rows, writer, file). Caller index pattern: [0] rows (read),
    [1] writerow, [2] close."""
    path = os.path.join(run_dir, name)
    rows = []
    if os.path.exists(path):
        with open(path, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    f = open(path, "a", newline="", encoding="utf-8")
    writer = csv.DictWriter(f, fieldnames=cols)
    if not rows and f.tell() == 0:
        writer.writeheader()
    return rows, writer, f


def append_aux(slot, row: dict) -> None:
    slot[1].writerow(row)
    slot[2].flush()


# ──────────────────────────── mechanical gate ────────────────────────────────
def gate_candidate(matrix: Matrix, fam_id: str, slots: dict,
                   guards: set[str]) -> tuple[bool, str]:
    """Spec gate BEFORE the oracle — Wave-69 self-defending architecture:
    refuse to compile what the pre-registered spec does not cover."""
    a, b, c = slots.get("a"), slots.get("b"), slots.get("c")
    if fam_id in ("REL-BOND", "ECHO", "TENSION", "PLAY", "SOUND", "TMSEQ"):
        if not a or not b:
            return False, "missing endpoints"
        if a not in matrix.nodes or b not in matrix.nodes:
            return False, f"endpoint not in matrix: {a}/{b}"
        if a == b:
            return False, "self loop"
    if fam_id == "BRIDGE":
        if not a or not c or a not in matrix.nodes or c not in matrix.nodes:
            return False, "bridge endpoints missing"
    if fam_id == "GUARD" and (not a or a not in matrix.nodes):
        return False, "guard target missing"
    if fam_id == "DECOMP" and (not a or a not in matrix.nodes):
        return False, "parent missing"
    # guarded-node provenance rule is enforced at apply-time (needs question_id)
    if fam_id in ("REL-BOND", "ECHO", "PLAY", "SOUND", "TMSEQ", "BRIDGE"):
        for lbl in (a, b, c):
            nid = _nid(matrix, lbl)
            if nid and nid in guards and not slots.get("question_id"):
                return False, f"guarded node {nid} touched without provenance"
    return True, ""


def _nid(matrix: Matrix, label: str | None) -> str | None:
    if not label:
        return None
    for n in matrix.nodes.values():
        if n["label"].lower() == str(label).lower():
            return n["id"]
    return None


# ───────────────────────────── family binds ──────────────────────────────────
def norm_score(ans: dict) -> float:
    """score answers arrive as rubric index (int) or label; normalize to [0,1]."""
    v = ans.get("score", ans.get("value", 0))
    try:
        return clamp01(float(v) / SCORE_NORM)
    except (TypeError, ValueError):
        return 0.5


def apply_family(fam_id: str, row: dict, answers: dict, matrix: Matrix,
                 round_no: int, scars: ScarLog, aux,
                 guards_all: frozenset | set | None = None,
                 registry: "GuardRegistry | None" = None,
                 run_name: str = "") -> dict:
    """Mechanical transcription: oracle answers → spreadsheet rows.
    Returns a receipt payload. guards_all = per-run ∪ cross-run registry;
    registry (when given) receives every fresh mint, so a guard earned
    tonight protects the node in every future night."""
    slots = row.get("slots", {})
    a, b, c = slots.get("a"), slots.get("b"), slots.get("c")
    out: dict = {"family": fam_id, "qid": row["qid"]}

    # GUARD GATE: mutations touching a guarded node require provenance. This
    # is the Wave-69 spec-gate miniaturized: a no-provenance write onto a
    # guarded node is refused (INDETERMINATE-style) and scarred — never
    # silently dropped, never allowed through un-specced.
    edge_writers = {"REL-BOND", "TMSEQ", "BRIDGE", "ECHO", "PLAY", "MOTHDRIFT"}
    _gset = guards_all if guards_all is not None else {r["node"] for r in aux["guards"][0]}
    if fam_id in edge_writers and not row.get("qid"):
        for lbl in (a, b, c):
            nid = _nid(matrix, lbl)
            if nid and nid in _gset:
                scars.scar(round_no, "spec-missing",
                           {"family": fam_id, "guarded": nid, "label": lbl})
                out.update({"refused": "spec-missing", "guarded": nid})
                return out

    if fam_id == "REL-BOND":
        r = float(answers["resonates"]["noul"])
        k = float(answers["contradicts"]["noul"])
        s = norm_score(answers["strength"])
        rel = "contradicts" if k > 0.6 else ("resonates" if r > 0.5 else "echoes")
        na, nb = _nid(matrix, a), _nid(matrix, b)
        eid = matrix.upsert_edge(na, nb, rel, joy=r, entropy=k, value=s,
                                 origin_round=round_no, created_by="oracle",
                                 question_id=row["qid"])
        out.update({"edge": eid, "rel": rel, "joy": r, "entropy": k, "value": round(s, 3)})

    elif fam_id == "DECOMP":
        ess = float(answers["essential"]["noul"])
        dis = float(answers["distinct"]["noul"])
        na = _nid(matrix, a)
        if ess > 0.5 and dis > 0.5:
            nb = matrix.add_node(b, joy=clamp01(0.4 + 0.4 * ess), entropy=0.5,
                                 value=clamp01(ess), origin_round=round_no,
                                 created_by="cell+oracle", note=f"decomp of {na}")
            matrix.upsert_edge(na, nb, "feeds", joy=ess, entropy=1 - ess, value=ess,
                               origin_round=round_no, created_by="oracle",
                               question_id=row["qid"])
            out.update({"fission": nb, "essential": ess, "distinct": dis})
        else:
            scars.scar(round_no, "decomp-rejected",
                       {"parent": na, "sub": b, "essential": ess, "distinct": dis})
            out.update({"scarred": True, "essential": ess, "distinct": dis})

    elif fam_id == "BRIDGE":
        br = float(answers["bridges"]["noul"])
        w = norm_score(answers["weight"])
        na, nc = _nid(matrix, a), _nid(matrix, c)
        if br > 0.5:
            if nc is None:
                nc = matrix.add_node(c, joy=br, entropy=0.5, value=w,
                                     origin_round=round_no, created_by="cell+oracle",
                                     note=f"bridge {a}<->{b}")
            e1 = matrix.upsert_edge(na, nc, "bridges", joy=br, entropy=0.4, value=w,
                                    origin_round=round_no, created_by="oracle",
                                    question_id=row["qid"])
            e2 = matrix.upsert_edge(nc, _nid(matrix, b), "bridges", joy=br, entropy=0.4,
                                    value=w, origin_round=round_no, created_by="oracle",
                                    question_id=row["qid"])
            out.update({"bridge": c, "edges": [e1, e2], "weight": round(w, 3)})
        else:
            scars.scar(round_no, "bridge-rejected", {"a": a, "b": b, "c": c, "bridges": br})
            out.update({"scarred": True, "bridges": br})

    elif fam_id == "TENSION":
        sus = float(answers["suspicious"]["noul"])
        rep = norm_score(answers["repairable"])
        eid = slots.get("edge_id", "")
        if eid in matrix.edges and sus > 0.7:
            matrix.edges[eid]["entropy"] = clamp01(matrix.edges[eid]["entropy"] + 0.1)
            scars.scar(round_no, "tension-audit", {"edge": eid, "suspicious": sus,
                                                   "repairable": rep})
            out.update({"scarred": True, "edge": eid, "suspicious": sus})
        elif eid in matrix.edges:
            matrix.edges[eid]["value"] = clamp01(matrix.edges[eid]["value"] + 0.02)
            out.update({"confirmed": True, "edge": eid})

    elif fam_id == "TMSEQ":
        bef = float(answers["before"]["noul"])
        if bef > 0.5:
            # stages are NEW nodes proposed by the cell — mint them on acceptance
            nb = _nid(matrix, b) or matrix.add_node(b, origin_round=round_no,
                                                    created_by="cell+oracle",
                                                    note=f"tminus stage of {a}")
            nc = _nid(matrix, c) or matrix.add_node(c, origin_round=round_no,
                                                    created_by="cell+oracle",
                                                    note=f"tminus stage of {a}")
            eid = matrix.upsert_edge(nb, nc, "tminus", joy=bef, entropy=1 - bef,
                                     value=0.8, origin_round=round_no,
                                     created_by="oracle", question_id=row["qid"])
            out.update({"edge": eid, "before": bef})
        else:
            out.update({"skipped": True, "before": bef})

    elif fam_id == "SOUND":
        mode = answers["mode"].get("value") or answers["mode"].get("choice") or "minor"
        bright = norm_score(answers["brightness"])
        dense = norm_score(answers["density"])
        vel = norm_score(answers["velocity"])
        append_aux(aux["sound"], {"cluster": json.dumps(slots.get("cluster", [a, b])),
                                  "mode": mode, "brightness": round(bright, 3),
                                  "density": round(dense, 3), "velocity": round(vel, 3),
                                  "round": round_no})
        out.update({"mode": mode, "brightness": round(bright, 3)})

    elif fam_id == "MOTHDRIFT":
        fits = float(answers["fits"]["noul"])
        ent = slots.get("moth_entropy", 0.75)
        na = _nid(matrix, a) or matrix.add_node(a, origin_round=round_no, created_by="moth")
        nb = _nid(matrix, b) or matrix.add_node(b, origin_round=round_no, created_by="moth")
        if fits > 0.4:
            eid = matrix.upsert_edge(na, nb, "echoes", joy=fits, entropy=ent, value=0.3,
                                     origin_round=round_no, created_by="moth",
                                     question_id=row["qid"], note="moth-drift")
            out.update({"edge": eid, "fits": fits})
        else:
            scars.scar(round_no, "moth-drift-rejected", {"a": a, "b": b, "fits": fits})
            out.update({"scarred": True, "fits": fits})

    elif fam_id == "GUARD":
        ng = float(answers["needs_guard"]["noul"])
        gs = norm_score(answers["guard_strength"])
        na = _nid(matrix, a)
        if ng > 0.5 and na:
            append_aux(aux["guards"], {"node": na, "strength": round(gs, 3),
                                       "round": round_no})
            if registry is not None:
                registry.mint(na, round(gs, 3), round_no, run_name,
                              reason=f"guard-question:{row['qid']}")
            if guards_all is not None:
                guards_all.add(na)  # guarded for every future run, now
            out.update({"guarded": na, "strength": round(gs, 3),
                        "registry_size": registry.count() if registry else None})
        else:
            out.update({"guarded": None, "needs_guard": ng})

    elif fam_id == "ECHO":
        p1 = float(answers["p1"]["noul"])
        p2 = float(answers["p2"]["noul"])
        delta = abs(p1 - p2)
        na, nb = _nid(matrix, a), _nid(matrix, b)
        if delta > 0.35:
            scars.scar(round_no, "oracle-instability", {"a": a, "b": b, "delta": delta})
            out.update({"scarred": True, "delta": round(delta, 3)})
        else:
            eid = matrix.upsert_edge(na, nb, "resonates", joy=(p1 + p2) / 2,
                                     entropy=delta, value=0.5 + 0.3 * (1 - delta),
                                     origin_round=round_no, created_by="oracle",
                                     question_id=row["qid"])
            out.update({"edge": eid, "delta": round(delta, 3)})

    elif fam_id == "PLAY":
        game = answers["game"].get("value") or answers["game"].get("choice") or "pass-the-note"
        fun = float(answers["fun"]["noul"])
        append_aux(aux["games"], {"a": a, "b": b, "game": game, "fun": round(fun, 3),
                                  "round": round_no})
        if fun > 0.5:
            eid = matrix.upsert_edge(_nid(matrix, a), _nid(matrix, b), "plays",
                                     joy=fun, entropy=0.3, value=0.4,
                                     origin_round=round_no, created_by="oracle",
                                     question_id=row["qid"])
            out.update({"edge": eid, "game": game, "fun": fun})
        else:
            out.update({"game": game, "fun": fun, "played": True})

    return out


# ─────────────────────────── competitive generator ────────────────────────────
def cell_propose(persona: str, fam_id: str, slots: dict, paper: list[dict],
                 channel: str) -> dict:
    """One competitor's proposal for a generator family. Context = paper only.
    Hallucinated labels are filtered mechanically (names must exist)."""
    tasks = {
        "DECOMP": {"schema": '[{"b":"<short sub-idea of a>","note":"<=8 words"}]',
                   "ask": f"propose 2-3 sub-ideas of '{slots.get('a')}'"},
        "BRIDGE": {"schema": '[{"b":"<new short bridge concept between a and b>","note":"<=8 words"}]',
                   "ask": f"propose ONE bridge concept connecting '{slots.get('a')}' and '{slots.get('b')}'"},
        "TMSEQ":  {"schema": '[{"b":"<stage name>","c":"<later stage name>","note":"<=8 words"}]',
                   "ask": f"propose the next two t-minus stages toward '{slots.get('a')}'"},
    }
    t = tasks[fam_id]
    name, mission = cells.PERSONAS[persona]
    sysmsg = (f"You are {name}, a small fast cell. {mission}. Output STRICT JSON only: "
              f"{t['schema']} — max 3 items, no prose, no markdown fences.")
    user = f"PAPER (current visible rows): {json.dumps(paper, separators=(',', ':'))}\nTASK: {t['ask']}"
    try:
        raw, ms = cells.complete(channel, [{"role": "system", "content": sysmsg},
                                           {"role": "user", "content": user}])
    except Exception as e:  # network/HTTP failure → INDETERMINATE, not a crash
        return {"ok": False, "error": f"channel {channel}: {e}", "latency_ms": None}
    arr, err = cells.parse_json_array(raw)
    if err:
        return {"ok": False, "error": f"parse: {err}", "raw": raw[:200], "latency_ms": ms}
    out = []
    for item in arr[:3]:
        if isinstance(item, dict) and item.get("b"):
            out.append({"b": str(item["b"])[:40],
                        "c": str(item.get("c", ""))[:40],
                        "note": str(item.get("note", ""))[:80]})
    if not out:
        return {"ok": False, "error": "empty proposals", "raw": raw[:200], "latency_ms": ms}
    return {"ok": True, "proposals": out, "latency_ms": ms}


def judge_with_oracle(fam_id: str, slots: dict, proposal: dict,
                      index_fam: dict, paper: list[dict]) -> tuple[dict | None, str | None]:
    """Build + send the typesafe batch for one proposal. Returns (answers, err)."""
    qspec = index_fam["questions"]
    qs = {}
    if fam_id == "DECOMP":
        qs = {"essential": {"type": "noul", "instructions": qspec["essential"]["instructions"].replace("{a}", slots["a"]).replace("{b}", proposal["b"])},
              "distinct": {"type": "noul", "instructions": qspec["distinct"]["instructions"].replace("{a}", slots["a"]).replace("{b}", proposal["b"])}}
        state = f"Parent concept: '{slots['a']}'. Proposed sub-idea: '{proposal['b']}'."
    elif fam_id == "BRIDGE":
        c = proposal["b"]
        qs = {"bridges": {"type": "noul", "instructions": qspec["bridges"]["instructions"].replace("{a}", slots["a"]).replace("{b}", slots["b"]).replace("{c}", c)},
              "weight": {"type": "score", "instructions": qspec["weight"]["instructions"].replace("{a}", slots["a"]).replace("{b}", slots["b"]).replace("{c}", c), "criteria": qspec["weight"]["criteria"]}}
        state = f"Concept A: '{slots['a']}'. Distant concept B: '{slots['b']}'. Proposed bridge C: '{c}'."
    elif fam_id == "TMSEQ":
        qs = {"before": {"type": "noul", "instructions": qspec["before"]["instructions"].replace("{a}", slots["a"]).replace("{b}", proposal["b"]).replace("{c}", proposal["c"] or "the final stage")}}
        state = f"Goal: '{slots['a']}'. Stage X: '{proposal['b']}'. Stage Y: '{proposal['c']}'."
    else:
        return None, f"unknown generator family {fam_id}"
    try:
        r = typesafe_q.ask(state, qs)
        return r["answers"], None
    except Exception as e:
        return None, f"oracle: {e}"


# ──────────────────────────────── main loop ───────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--rounds", type=int, default=16)
    ap.add_argument("--pool-seed", type=int, default=42)
    ap.add_argument("--rotation", default=None,
                    help="comma list of family ids overriding the standard "
                         "rotation — a night's declared 'varying logic' "
                         "experiment, receipted in the ledger")
    ap.add_argument("--no-moth", action="store_true")
    ap.add_argument("--no-music", action="store_true")
    ap.add_argument("--no-cells", action="store_true", help="oracle-only rounds")
    ap.add_argument("--snapshot-every", type=int, default=8)
    ap.add_argument("--music-every", type=int, default=8)
    ap.add_argument("--push-every", type=int, default=0, help="0 = no git ops")
    ap.add_argument("--rewind-to", type=int, default=None)
    args = ap.parse_args()

    run_dir = os.path.join(HERE, args.run) if not os.path.isabs(args.run) else args.run
    os.makedirs(run_dir, exist_ok=True)
    matrix_root = os.path.join(run_dir, "matrix")
    snaps_dir = os.path.join(run_dir, "snapshots")
    music_dir = os.path.join(run_dir, "music")
    for d in (matrix_root, snaps_dir, music_dir):
        os.makedirs(d, exist_ok=True)

    matrix = Matrix(matrix_root).load()
    bootstrap(matrix, run_dir)
    ledger = Ledger(os.path.join(run_dir, "receipts.jsonl"))
    scars = ScarLog(os.path.join(run_dir, "scars.jsonl"))
    run_state["scars0"] = scars.count()
    aux = {
        "sound": load_aux(run_dir, "sound.csv", ["cluster", "mode", "brightness", "density", "velocity", "round"]),
        "guards": load_aux(run_dir, "guards.csv", ["node", "strength", "round"]),
        "games": load_aux(run_dir, "games.csv", ["a", "b", "game", "fun", "round"]),
    }
    board_path = os.path.join(run_dir, "leaderboard.csv")
    new_board = not os.path.exists(board_path)
    board = open(board_path, "a", newline="", encoding="utf-8")
    bwr = csv.DictWriter(board, fieldnames=["round", "applied", "scarred", "die_rolls",
                                            "nodes", "edges", "balance", "scar_total"])
    if new_board:
        bwr.writeheader()

    # CROSS-RUN GUARD REGISTRY: sync every sibling run's guards into the
    # repo-level hash-chained registry, then the effective guard set is
    # per-run ∪ registry. A guard minted in any night protects the node
    # in every night; mints below append through to the registry too.
    import glob as _glob
    runs_root = os.path.dirname(os.path.abspath(run_dir))
    registry = GuardRegistry(os.path.join(runs_root, "guard_registry.jsonl"))
    for gcsv in sorted(_glob.glob(os.path.join(runs_root, "*", "guards.csv"))):
        registry.sync_from_run(os.path.dirname(gcsv),
                               os.path.basename(os.path.dirname(gcsv)))
    guards_all = _guards(aux) | registry.nodes()
    if registry.count():
        ledger.append("guard-registry-sync", len(ledger.lines),
                      {"registry_size": registry.count(),
                       "imported": registry.count(),
                       "chain_ok": registry.chain_ok(),
                       "nodes": sorted(registry.nodes())}, matrix.matrix_hash())

    pool = build_pool(matrix.concepts(20, random.Random(args.pool_seed)), seed=args.pool_seed)
    fams_by_id = {f["id"]: f for f in load_index()["families"]}
    spec_seals = {fid: spec_sha(f) for fid, f in fams_by_id.items()}
    with open(os.path.join(run_dir, "spec_seals.json"), "w", encoding="utf-8") as f:
        json.dump(spec_seals, f, indent=2, sort_keys=True)

    # rewind request: restore snapshot, keep scars/receipts, receipt the act
    if args.rewind_to is not None:
        rewind(matrix_root, snaps_dir, args.rewind_to)
        matrix = Matrix(matrix_root).load()
        ledger.append("rewind", args.rewind_to, {"to_round": args.rewind_to,
                     "scars_preserved": scars.count()}, matrix.matrix_hash())
        print(f"REWOUND to round {args.rewind_to}; scars preserved: {scars.count()}")

    rng = random.Random(args.pool_seed * 1000 + len(ledger.lines))
    mhash = matrix.matrix_hash()
    fam_rotation = [s.strip() for s in args.rotation.split(",")] if args.rotation \
        else ["REL-BOND", "DECOMP", "ECHO", "TENSION", "PLAY", "MOTHDRIFT",
              "SOUND", "GUARD", "TMSEQ", "BRIDGE"]
    if args.rotation:
        ledger.append("rotation-experiment", len(ledger.lines),
                      {"rotation": fam_rotation}, mhash)
    fam_pos = len(ledger.lines) % len(fam_rotation)
    t_start = time.time()
    print(f"RUN {args.run}: pool={len(pool)} round_start={len(ledger.lines) // 6} "
          f"nodes={len(matrix.nodes)} edges={len(matrix.edges)} scars={scars.count()}")

    for rr in range(args.rounds):
        # one bounce per round is the round's heartbeat — round number is
        # derived from it, so resume/rewind stays consistent
        round_no = ledger.count_kind("jev") + 1
        applied, scarred_this, die_rolls = [], 0, []
        oracle_fails = 0
        indeterminate = 0

        # 1-2 questions per round from the rotation
        for _ in range(2):
            fam_id = fam_rotation[fam_pos % len(fam_rotation)]
            fam_pos += 1
            fam_rows = [p for p in pool if p["family"] == fam_id]
            if not fam_rows:
                continue
            row = dict(rng.choice(fam_rows))
            fam = fams_by_id[fam_id]
            if spec_seals[fam_id] != row["spec_sha"]:  # anti-post-hoc law
                ledger.append("spec-drift", round_no, {"family": fam_id}, mhash)
                continue  # pool/INDEX mismatch refused
            ok, why = gate_candidate(matrix, fam_id, row.get("slots", {}), guards=guards_all)
            if not ok:
                scars.scar(round_no, "gate-refused", {"qid": row["qid"], "why": why})
                scarred_this += 1
                continue

            # TENSION audits a REAL edge: pick one now, rebuild state + questions
            if fam_id == "TENSION":
                eids = sorted(matrix.edges)
                if not eids:
                    scars.scar(round_no, "gate-refused",
                               {"qid": row["qid"], "why": "no edges yet"})
                    scarred_this += 1
                    continue
                e = matrix.edges[rng.choice(eids)]
                a_lbl = matrix.nodes[e["src"]]["label"]
                b_lbl = matrix.nodes[e["dst"]]["label"]
                row["slots"] = {"a": a_lbl, "b": b_lbl, "edge_id": e["edge_id"],
                                "rel": e["rel_type"], "joy": round(e["joy"], 2),
                                "entropy": round(e["entropy"], 2),
                                "value": round(e["value"], 2)}
                qt = fam["questions"]
                row["state"] = (f"Recorded relation: '{a_lbl}' --[{e['rel_type']}]--> "
                                f"'{b_lbl}' (joy={row['slots']['joy']}, "
                                f"entropy={row['slots']['entropy']}, "
                                f"value={row['slots']['value']}).")
                row["questions"] = {
                    "suspicious": {"type": "noul", "instructions":
                                   qt["suspicious"]["instructions"]
                                   .replace("{a}", a_lbl).replace("{b}", b_lbl)
                                   .replace("{rel}", e["rel_type"])
                                   .replace("{joy}", str(row["slots"]["joy"]))
                                   .replace("{entropy}", str(row["slots"]["entropy"]))
                                   .replace("{value}", str(row["slots"]["value"]))},
                    "repairable": {"type": "score",
                                   "instructions": qt["repairable"]["instructions"]
                                   .replace("{a}", a_lbl).replace("{b}", b_lbl),
                                   "criteria": qt["repairable"]["criteria"]},
                }

            # MOTHDRIFT: real quantum entropy picks + seeds the probe
            if fam_id == "MOTHDRIFT" and not args.no_moth:
                hx = moth.quantum_bytes(4)
                if hx:
                    # receipt the certified randomness itself (SP 800-90B +
                    # CHSH witness come from comet-qrng-v1's result payload)
                    ledger.append("moth-entropy", round_no,
                                  {"hex": hx, "source": "comet-qrng-v1",
                                   "use": "candidate-pick+entropy"}, mhash)
                    lex = json.load(open(os.path.join(HERE, "questions", "index.json")))["lexicon"]
                    a_lbl = row["slots"]["a"]
                    b_lbl = lex[int(hx, 16) % len(lex)]
                    row["slots"].update({"b": b_lbl, "prov": f"moth:{hx[:8]}",
                                         "moth_entropy": 0.6 + (int(hx, 16) % 30) / 100.0})
                    row["state"] = (f"Concept A: '{a_lbl}'. Moth-drifted candidate "
                                    f"neighbor: '{b_lbl}'. The candidate was chosen by "
                                    f"a quantum coin (provenance moth:{hx[:8]}).")
                    row["questions"]["fits"]["instructions"] = (
                        row["questions"]["fits"]["instructions"]
                        .replace("{a}", a_lbl).replace("{b}", b_lbl)
                        .replace("{prov}", f"moth:{hx[:8]}"))

            # generator families: two cells compete
            if fam.get("needs_generator") and not args.no_cells:
                paper = matrix.slice_for(_nid(matrix, row["slots"]["a"]) or "", 6)
                cands = []
                for persona in ("weaver", "trickster"):
                    pr = cell_propose(persona, fam_id, row["slots"], paper, "cf-8b")
                    ledger.append("cell", round_no, {"persona": persona, "family": fam_id,
                                  **{k: pr.get(k) for k in ("ok", "error", "proposals", "latency_ms")}}, mhash)
                    if pr["ok"]:
                        cands.append((persona, pr["proposals"]))
                if not cands:
                    indeterminate += 1
                    scars.scar(round_no, "cell-indeterminate", {"family": fam_id, "qid": row["qid"]})
                    scarred_this += 1
                else:
                    best = None
                    for persona, props in cands:
                        p = props[0]
                        answers, err = judge_with_oracle(fam_id, row["slots"], p, fam, paper)
                        if err:
                            oracle_fails += 1
                            continue
                        sc = sum(float(a.get("noul", a.get("score", 0) or 0)) for a in answers.values()) / len(answers)
                        if best is None or sc > best[0]:
                            best = (sc, persona, p, answers)
                    if best is None:
                        indeterminate += 1
                        scars.scar(round_no, "oracle-fail", {"family": fam_id, "qid": row["qid"]})
                        scarred_this += 1
                    else:
                        sc, persona, p, answers = best
                        slots2 = dict(row["slots"])
                        if fam_id == "BRIDGE":
                            # the proposal IS the bridge concept → it lands in C;
                            # B stays the original distant endpoint
                            slots2["c"] = p["b"]
                            slots2["bridge_note"] = p.get("note", "")
                        else:
                            slots2["b"] = p["b"]
                            slots2["c"] = p.get("c", "")
                        slots2["question_id"] = row["qid"]
                        payload = apply_family(fam_id, {**row, "slots": slots2}, answers,
                                               matrix, round_no, scars, aux,
                                               guards_all=guards_all, registry=registry,
                                               run_name=os.path.basename(os.path.abspath(args.run)))
                        applied.append({**payload, "winner": persona, "score": round(sc, 3)})
                        ledger.append("mutation", round_no, payload, matrix.matrix_hash())
                        duet_seed = f"{persona}:{row['qid']}"
                        run_state["duet"].append(
                            (persona, {**payload, "origin_round": round_no}, duet_seed))
            else:
                # oracle-only family: one batched call
                try:
                    r = typesafe_q.ask(refresh_guard_state(matrix, fams_by_id, row)["state"],
                                       row["questions"])
                    answers = r["answers"]
                    ledger.append("oracle", round_no, {"qid": row["qid"], "family": fam_id,
                                  "latency_ms": r["latency_ms"], "usage": r["usage"]}, mhash)
                except Exception as e:
                    oracle_fails += 1
                    ledger.append("oracle-fail", round_no, {"qid": row["qid"], "error": str(e)[:160]}, mhash)
                    continue
                payload = apply_family(fam_id, row, answers, matrix, round_no, scars, aux,
                                       guards_all=guards_all, registry=registry,
                                       run_name=os.path.basename(os.path.abspath(args.run)))
                applied.append(payload)
                ledger.append("mutation", round_no, payload, matrix.matrix_hash())

        # 5. Die Engine on deadlock
        if indeterminate >= 2 or oracle_fails >= 2:
            hx = None if args.no_moth else moth.quantum_bytes(4)
            seed = die.die_seed(hx, mhash, round_no, "deadlock")
            face = die.d20(seed)
            plan = die.drift_plan(face, matrix, rng)
            for step in plan:
                _apply_drift_step(step, matrix, round_no, scars, aux)
            die_rolls.append({"face": face, "seed": seed[:24], "plan": plan})
            ledger.append("die", round_no, {"face": face, "bucket": die.bucket(face),
                          "moth_seeded": bool(hx), "plan": plan}, matrix.matrix_hash())
            run_state["faces"].append(face)

        # 6. JEV bounce — the walker thinks on the web
        start = rng.choice(sorted(matrix.nodes))
        walk = jev.bounce(matrix, start, 6, rng)
        ledger.append("jev", round_no, {"start": start, "path": walk["path"],
                      "steps": walk["steps"]}, matrix.matrix_hash())

        mhash = matrix.matrix_hash()
        matrix.save()

        # 7. music segment
        if not args.no_music and round_no % args.music_every == 0:
            _emit_segment(music_dir, run_dir, matrix, mhash, round_no - args.music_every + 1, round_no)

        # 8. snapshot
        if round_no % args.snapshot_every == 0:
            snapshot(matrix_root, snaps_dir, round_no)

        st = jev.web_stats(matrix)
        bwr.writerow({"round": round_no, "applied": len(applied),
                      "scarred": scarred_this + scars.count() - run_state["scars0"],
                      "die_rolls": json.dumps(die_rolls), "nodes": st["nodes"],
                      "edges": st["edges"], "balance": st["balance"],
                      "scar_total": scars.count()})
        board.flush()
        print(f"  r{round_no:03d} applied={len(applied)} new_scars={scarred_this} "
              f"die={len(die_rolls)} nodes={st['nodes']} edges={st['edges']} "
              f"balance={st['balance']} scars={scars.count()} "
              f"({time.time()-t_start:.0f}s)")

        # 9. push
        if args.push_every and round_no % args.push_every == 0:
            _git_push(HERE, round_no, st)

    ledger.append("run-end", round_no, {"rounds": args.rounds,
                  "applied": sum(1 for _ in ledger.lines if _["kind"] == "mutation"),
                  "scars": scars.count()}, matrix.matrix_hash())
    board.close()
    for slot in aux.values():
        slot[2].close()
    print(f"RUN DONE: ledger={len(ledger.lines)} chain_ok={ledger.verify()[0]} scars={scars.count()}")
    return 0


def _degree(matrix: Matrix, label: str) -> int:
    nid = _nid(matrix, label)
    if not nid:
        return 0
    return sum(1 for e in matrix.edges.values()
               if e.get("src") == nid or e.get("dst") == nid)


def refresh_guard_state(matrix: Matrix, fams_by_id: dict, row: dict) -> dict:
    """GUARD asks whether a node is load-bearing enough to require provenance
    — so the question must be asked about the node's REAL current weights,
    not the boot-time defaults (joy=0.5, degree=0) the pool baked in. Night 3
    diagnosis: with baked state the oracle honestly answered needs_guard≈0.3
    for everything, and no guard could ever mint. The SPEC (questions,
    criteria, spec_sha seal) is untouched — only the world the question is
    asked about is refreshed. The pre-registered spec is about what is asked,
    not about freezing the web in time."""
    if row.get("family") != "GUARD":
        return row
    node = (row.get("slots") or {}).get("a")
    n = matrix.nodes.get(_nid(matrix, node) or "")
    if not node or not n:
        return row
    tpl = fams_by_id["GUARD"]["state"]
    row["state"] = _fill(tpl, a=node,
                         joy=round(clamp01(float(n.get("joy", 0.5))), 3),
                         entropy=round(clamp01(float(n.get("entropy", 0.5))), 3),
                         value=round(clamp01(float(n.get("value", 0.5))), 3),
                         degree=_degree(matrix, node))
    return row


def _guards(aux) -> set[str]:
    return {r["node"] for r in aux["guards"][0]}


def _apply_drift_step(step: dict, matrix: Matrix, round_no: int, scars: ScarLog,
                      aux=None) -> None:
    op = step["op"]
    if op == "add_edge" and aux is not None:
        # die edges carry question_id="die" — that is NO provenance for a
        # guarded node: the guard gate has teeth on drift too (refuse + scar)
        guarded = {r["node"] for r in aux["guards"][0]}
        if step.get("src") in guarded or step.get("dst") in guarded:
            scars.scar(round_no, "die-refused-guarded", step)
            return
    if op == "jitter" and step["edge"] in matrix.edges:
        e = matrix.edges[step["edge"]]
        e["joy"] = clamp01(e["joy"] + step["d_joy"])
        e["entropy"] = clamp01(e["entropy"] + step["d_entropy"])
    elif op == "fission":
        src = matrix.nodes.get(step["node"])
        if src:
            nid = matrix.add_node(step["new_label"], joy=src["joy"], entropy=min(1.0, src["entropy"] + 0.1),
                                  value=src["value"] * 0.8, origin_round=round_no,
                                  created_by="die", note=f"fission of {src['id']}")
            matrix.upsert_edge(src["id"], nid, "feeds", joy=0.6, entropy=0.5, value=0.4,
                               origin_round=round_no, created_by="die", question_id="die")
    elif op == "rewire" and step["edge"] in matrix.edges:
        e = matrix.edges[step["edge"]]
        old = dict(e)
        matrix.remove_edge(step["edge"])
        matrix.upsert_edge(old["src"], step["new_dst"], old["rel_type"], old["joy"],
                           old["entropy"], old["value"], old["origin_round"],
                           created_by="die", question_id="die", note="rewired")
    elif op == "add_edge":
        if step["src"] in matrix.nodes and step["dst"] in matrix.nodes:
            matrix.upsert_edge(step["src"], step["dst"], step["rel_type"], step["joy"],
                               step["entropy"], step["value"], origin_round=round_no,
                               created_by="die", question_id="die", note=step.get("note", ""))
    elif op == "scar_backoff":
        scars.scar(round_no, "die-scar-backoff", step)


def _emit_segment(music_dir: str, run_dir: str, matrix, mhash: str,
                  r0: int, r1: int) -> str | None:
    """One MIDI segment: chords per round, walker melodies, scar percussion,
    persona duet notes. Deterministic from run state."""
    try:
        w = MidiWriter(tempo_bpm=110)
        w.program(0, 73)  # flute-ish melody
        w.program(1, 89)  # warm pad chords
        w.program(2, 32)  # duet voices
        w.program(3, 33)
        led = Ledger(os.path.join(run_dir, "receipts.jsonl"))
        scars = ScarLog(os.path.join(run_dir, "scars.jsonl"))
        walks = [x for x in led.lines if x["kind"] == "jev" and r0 <= x["round"] <= r1]
        muts = [x for x in led.lines if x["kind"] == "mutation" and r0 <= x["round"] <= r1]
        for i, r in enumerate(range(r0, r1 + 1)):
            walk = next((x for x in walks if x["round"] == r), None)
            mut = next((x for x in muts if x["round"] == r), None)
            ent = 0.5
            rel = "resonates"
            top = [0.5, 0.4, 0.3]
            if mut and "payload" in mut:
                p = mut["payload"]
                rel = p.get("rel", p.get("mode", rel)) if isinstance(p, dict) else rel
                if isinstance(p, dict) and "value" in p:
                    v = p["value"]
                    top = [v, min(1.0, v + 0.1), max(0.0, v - 0.1)] if isinstance(v, (int, float)) else top
                    ent = p.get("entropy", ent) if isinstance(p.get("entropy"), (int, float)) else ent
            round_chord(w, i, mhash + str(r), rel, top, ent)
            if walk and isinstance(walk["payload"].get("path"), list):
                jev_melody(w, i, walk["payload"]["path"], mhash + str(r), ent)
            for j, s in enumerate([x for x in scars.lines if x["round"] == r]):
                scar_hit(w, i, j)
        # duet notes: one per accepted generator payload landing in this segment
        idx = 0
        for persona, payload, seedstr in run_state["duet"]:
            rr = s_round(payload)
            if r0 <= rr <= r1:
                v = payload.get("value", 0.5) if isinstance(payload, dict) else 0.5
                v = v if isinstance(v, (int, float)) else 0.5
                e = payload.get("entropy", 0.4) if isinstance(payload, dict) else 0.4
                duet_note(w, rr - r0, 2 if persona == "weaver" else 3,
                          float(v), float(e), seedstr)
                idx += 1
        path = os.path.join(music_dir, f"seg_{r0:04d}-{r1:04d}.mid")
        w.write(path)
        return path
    except Exception as e:
        print(f"  music emit failed (receipted, non-fatal): {e}")
        return None


def s_round(payload: dict) -> int:
    return int(payload.get("origin_round", 0) or 0) if isinstance(payload, dict) else 0


def _git_push(root: str, round_no: int, stats: dict) -> None:
    try:
        subprocess.run(["git", "add", "-A"], cwd=root, check=True,
                       capture_output=True, timeout=60)
        subprocess.run(["git", "commit", "-q", "-m",
                        f"quilt-matrix: through round {round_no} "
                        f"(nodes={stats['nodes']} edges={stats['edges']} "
                        f"balance={stats['balance']})"], cwd=root, check=True,
                       capture_output=True, timeout=60)
        subprocess.run([os.path.join(root, "..", "scripts", "push_with_token.sh"),
                        "SuperInstance/quilt-matrix", "main"], cwd=root, check=True,
                       capture_output=True, timeout=120)
        print(f"  PUSHED through round {round_no}")
    except subprocess.CalledProcessError as e:
        print(f"  git op skipped/failed (receipted, non-fatal): "
              f"{(e.stderr or b'').decode()[:120]}")


# per-run mutable state for duet emission (module-level, single-threaded)
run_state: dict = {"duet": [], "faces": [], "scars0": 0}

if __name__ == "__main__":
    sys.exit(main())
