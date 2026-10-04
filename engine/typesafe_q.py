"""engine/typesafe_q.py — the typesafe.ai System One question oracle.

Wire format verified 2026-09-21 (si-fleet/jev-quilt lineage) and re-verified
live 2026-10-04 (recon/key-receipts-2026-10-04/, noul heartbeat 0.87):

  POST {base}/v1/systemone
  {model, state, questions: {name: {type: noul|choice|score,
                                    instructions, criteria}}}
  → {model, answers: {name: {type, value|noul|score, confidence,
                             probabilities}}, usage}

This is the engine of the whole sprint: the vast question index (questions/)
is a catalog of typed System One questions, and each answer set IS the
relational weight payload the mechanical bot writes into the spreadsheet.
The oracle never writes rows itself — it answers; the bot transcribes.
"""

from __future__ import annotations
import json
import os
import time
import urllib.error
import urllib.request

DEFAULT_BASE = "https://api.typesafe.ai"
DEFAULT_MODEL = "jev-latest"


def _key() -> str:
    k = os.environ.get("TYPESAFE_API_KEY") or os.environ.get("JEV_API_KEY") or ""
    if not k:
        # last resort: read the fleet vault directly (chmod 600, gitignored)
        p = "/home/z/my-project/.env.keys"
        if os.path.exists(p):
            for line in open(p, encoding="utf-8"):
                if line.startswith("TYPESAFE_API_KEY="):
                    k = line.split("=", 1)[1].strip()
                    break
    if not k:
        raise RuntimeError("no typesafe key (TYPESAFE_API_KEY)")
    return k


def ask(state: str, questions: dict, model: str = DEFAULT_MODEL,
        timeout_s: float = 30.0, base: str | None = None) -> dict:
    """One batched System One pass: N typed questions, one call.

    questions: {name: {"type": "noul"|"choice"|"score", "instructions": str,
                       "criteria": dict|list (choice/score only)}}
    Returns {answers, usage, latency_ms, model}.
    """
    body = json.dumps({"model": model, "state": state, "questions": questions}).encode()
    req = urllib.request.Request(
        (base or DEFAULT_BASE).rstrip("/") + "/v1/systemone", data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {_key()}"})
    t0 = time.monotonic()
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        payload = json.loads(resp.read().decode())
    return {"answers": payload.get("answers", {}),
            "usage": payload.get("usage", {}),
            "model": payload.get("model", model),
            "latency_ms": round((time.monotonic() - t0) * 1000, 1)}


def noul(state: str, question: str, **kw) -> float:
    """Convenience: single yes/no question → probability in [0,1]."""
    r = ask(state, {"q": {"type": "noul", "instructions": question}}, **kw)
    return float(r["answers"]["q"]["noul"])


def score(state: str, question: str, rubric: list[str], **kw) -> float:
    """Convenience: rubric question → normalized [0,1] (index / (len-1))."""
    r = ask(state, {"q": {"type": "score", "instructions": question, "criteria": rubric}}, **kw)
    v = r["answers"]["q"]["score"]
    try:
        v = float(v)
    except (TypeError, ValueError):
        v = float(rubric.index(v)) if v in rubric else 0.0
    return v / max(1, len(rubric) - 1)


def choice(state: str, question: str, criteria: dict, **kw) -> str:
    """Convenience: choice question → chosen option name."""
    r = ask(state, {"q": {"type": "choice", "instructions": question, "criteria": criteria}}, **kw)
    return r["answers"]["q"].get("value") or r["answers"]["q"].get("choice")
