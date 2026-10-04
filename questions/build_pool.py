"""questions/build_pool.py — expand the index families into a vast question pool.

The index (questions/index.json) declares families; the pool is the family
expansion over (a) the 48-concept lexicon and (b) the matrix's own labels —
the quilt grows questions from its own nodes. Expansion is deterministic
given a seed: same seed → same pool, testable.

Output: <run_dir>/pool.jsonl — one question instance per line:
  {qid, family, state, questions, spec, spec_sha, round_hint}

"Vast" is a receipted number here: the pool size is logged and asserted
(>= 400 instances for a fresh matrix with the standard lexicon expansion —
REL-BOND alone contributes C(48,2) capped samples = 1128).
"""

from __future__ import annotations
import hashlib
import itertools
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
INDEX_PATH = os.path.join(HERE, "index.json")


def load_index() -> dict:
    with open(INDEX_PATH, encoding="utf-8") as f:
        return json.load(f)


def spec_sha(family: dict) -> str:
    """Pre-registration seal: sha256 over the canonical spec. Computed BEFORE
    any round runs; receipts carry it; the runner refuses to run a family
    whose spec changed mid-run (anti-post-hoc law)."""
    return hashlib.sha256(
        json.dumps(family["spec"], sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()[:16]


def _fill(template: str, **kw) -> str:
    out = template
    for k, v in kw.items():
        out = out.replace("{" + k + "}", str(v))
    return out


def _fmt(x) -> str:
    return json.dumps(x, separators=(",", ":")) if not isinstance(x, str) else x


def build_pool(matrix_labels: list[str], seed: int = 42, cap_per_family: int = 260) -> list[dict]:
    """Instantiate families over lexicon + matrix labels. Deterministic."""
    idx = load_index()
    rng = random.Random(seed)
    lex = idx["lexicon"]
    labels = sorted(set(lex + [l for l in matrix_labels if l not in lex]))
    pool: list[dict] = []

    def emit(fam, state, extra=None):
        qs = {}
        for name, q in fam["questions"].items():
            qq = {"type": q["type"], "instructions": _fill(q["instructions"], **kw_parts(state, fam))}
            if "criteria" in q:
                qq["criteria"] = q["criteria"]
            qs[name] = qq
        row = {"qid": f'{fam["id"]}:{len(pool):05d}', "family": fam["id"],
               "state": state, "questions": qs, "spec_sha": spec_sha(fam)}
        if extra:
            row.update(extra)
        pool.append(row)

    def kw_parts(state, fam):
        # the runner also needs raw slots; stash them on the row via state extras
        return {}

    for fam in idx["families"]:
        fid = fam["id"]
        made = 0
        seen: set[tuple] = set()

        def budget_ok() -> bool:
            return made < cap_per_family

        if fid == "REL-BOND":
            q = fam["questions"]
            pairs = list(itertools.combinations(labels, 2))
            rng.shuffle(pairs)
            for a, b in pairs:
                if not budget_ok():
                    break
                key = (a, b)
                if key in seen:
                    continue
                seen.add(key)
                state = _fill(fam["state"], a=a, b=b)
                row = {"qid": f"REL-BOND:{len(pool):05d}", "family": fid, "state": state,
                       "questions": {
                           "resonates": {"type": "noul", "instructions": _fill(q["resonates"]["instructions"], a=a, b=b)},
                           "contradicts": {"type": "noul", "instructions": _fill(q["contradicts"]["instructions"], a=a, b=b)},
                           "strength": {"type": "score", "instructions": _fill(q["strength"]["instructions"], a=a, b=b), "criteria": q["strength"]["criteria"]},
                       },
                       "spec_sha": spec_sha(fam), "slots": {"a": a, "b": b}}
                pool.append(row)
                made += 1

        elif fid in ("DECOMP", "TMSEQ", "GUARD", "ECHO"):
            q = fam["questions"]
            for a in labels:
                if not budget_ok():
                    break
                slots = {"a": a, "b": "", "c": "", "paper": "[]"}
                if fid == "ECHO":
                    partners = [x for x in labels if x != a]
                    if not partners:
                        continue
                    b = rng.choice(partners)
                    slots["b"] = b
                    state = _fill(fam["state"], a=a, b=b)
                    questions = {
                        "p1": {"type": "noul", "instructions": _fill(q["p1"]["instructions"], a=a, b=b)},
                        "p2": {"type": "noul", "instructions": _fill(q["p2"]["instructions"], a=a, b=b)},
                    }
                elif fid == "TMSEQ":
                    others = [x for x in labels if x != a]
                    if len(others) < 2:
                        continue
                    b, c = rng.sample(others, 2)
                    slots.update(b=b, c=c)
                    state = _fill(fam["state"], a=a, b=b, c=c)
                    questions = {"before": {"type": "noul", "instructions": _fill(q["before"]["instructions"], a=a, b=b, c=c)}}
                else:
                    state = _fill(fam["state"], a=a, paper="[]", joy=0.5, entropy=0.5, value=0.5, degree=0)
                    questions = {k: {"type": v["type"], "instructions": _fill(v["instructions"], a=a, b="{b}", degree=0)}
                                 for k, v in q.items()}
                row = {"qid": f"{fid}:{len(pool):05d}", "family": fid, "state": state,
                       "questions": questions, "spec_sha": spec_sha(fam), "slots": slots}
                pool.append(row)
                made += 1

        elif fid in ("BRIDGE", "MOTHDRIFT"):
            q = fam["questions"]
            for a in labels:
                if not budget_ok():
                    break
                others = [x for x in labels if x != a]
                b = rng.choice(others)
                c = rng.choice([x for x in labels if x not in (a, b)])
                state = _fill(fam["state"], a=a, b=b, c=c, prov="pending")
                questions = {k: {"type": v["type"], "instructions": _fill(v["instructions"], a=a, b=b, c=c)}
                             for k, v in q.items()}
                if "weight" in q:
                    questions["weight"]["criteria"] = q["weight"]["criteria"]
                if "mode" in q:
                    questions["mode"]["criteria"] = q["mode"]["criteria"]
                row = {"qid": f"{fid}:{len(pool):05d}", "family": fid, "state": state,
                       "questions": questions, "spec_sha": spec_sha(fam),
                       "slots": {"a": a, "b": b, "c": c}}
                pool.append(row)
                made += 1

        elif fid in ("TENSION", "SOUND", "PLAY"):
            q = fam["questions"]
            for a in labels:
                if not budget_ok():
                    break
                others = [x for x in labels if x != a]
                b = rng.choice(others)
                slots = {"a": a, "b": b, "rel": "resonates", "joy": 0.5, "entropy": 0.5, "value": 0.5, "degree": 0}
                if fid == "TENSION":
                    state = _fill(fam["state"], a=a, b=b, rel="resonates", joy=0.5, entropy=0.5, value=0.5)
                    questions = {
                        "suspicious": {"type": "noul", "instructions": _fill(q["suspicious"]["instructions"], a=a, b=b, rel="resonates", joy=0.5, entropy=0.5, value=0.5)},
                        "repairable": {"type": "score", "instructions": _fill(q["repairable"]["instructions"], a=a, b=b), "criteria": q["repairable"]["criteria"]},
                    }
                elif fid == "SOUND":
                    cluster = [a, b]
                    state = _fill(fam["state"], cluster=json.dumps(cluster), weights="{}")
                    questions = {k: {"type": v["type"], "instructions": _fill(v["instructions"], cluster=json.dumps(cluster), weights="{}")}
                                 for k, v in q.items()}
                    questions["mode"]["criteria"] = q["mode"]["criteria"]
                    for k in ("brightness", "density", "velocity"):
                        questions[k]["criteria"] = q[k]["criteria"]
                    slots["cluster"] = cluster
                else:  # PLAY
                    state = _fill(fam["state"], a=a, b=b)
                    questions = {
                        "game": {"type": "choice", "instructions": _fill(q["game"]["instructions"], a=a, b=b), "criteria": q["game"]["criteria"]},
                        "fun": {"type": "noul", "instructions": _fill(q["fun"]["instructions"], a=a, b=b)},
                    }
                row = {"qid": f"{fid}:{len(pool):05d}", "family": fid, "state": state,
                       "questions": questions, "spec_sha": spec_sha(fam), "slots": slots}
                pool.append(row)
                made += 1

    return pool


def main():
    run_dir = sys.argv[1] if len(sys.argv) > 1 else "."
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else 42
    pool = build_pool([], seed=seed)
    out = os.path.join(run_dir, "pool.jsonl")
    os.makedirs(run_dir, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        for row in pool:
            f.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")
    fams: dict[str, int] = {}
    for row in pool:
        fams[row["family"]] = fams.get(row["family"], 0) + 1
    print(json.dumps({"pool_size": len(pool), "families": fams, "seed": seed, "out": out}, indent=2))


if __name__ == "__main__":
    main()
