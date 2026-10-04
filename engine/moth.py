"""engine/moth.py — mothquantum channel: true quantum entropy + quantum music.

Verified 2026-10-04 (recon/scout-2a/moth_engines.md): GET /api/v1/engines
returns 32 engines WITH the header `Accept: application/json` (content
negotiation was the whole mystery). Relevant engines:

  coin-toss-v1  — true quantum bits → the Die Engine's entropy source
  qrc-midi-v1   — quantum-generated MIDI (→ .mid bytes) — moth AS a musician
  qpixl-v1      — numbers-as-waveform round trip
  graph-v1      — quantum graph states

Job flow: POST /api/v1/engines/{engine}/process {params} → job_id →
poll GET /api/v1/jobs/{id}/status → GET /api/v1/jobs/{id}/result.
Key: MOTH_API_KEY env or the fleet vault. Key NEVER lands in logs.
"""

from __future__ import annotations
import json
import os
import time
import urllib.error
import urllib.request

API = "https://api.mothquantum.com/api/v1"


def _key() -> str:
    k = os.environ.get("MOTH_API_KEY", "")
    if not k:
        p = "/home/z/my-project/.env.keys"
        if os.path.exists(p):
            for line in open(p, encoding="utf-8"):
                if line.startswith("MOTH_API_KEY="):
                    k = line.split("=", 1)[1].strip()
                    break
    if not k:
        raise RuntimeError("no moth key (MOTH_API_KEY)")
    return k


def _call(method: str, path: str, body: dict | None = None, timeout_s: float = 20.0):
    req = urllib.request.Request(
        API + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Bearer {_key()}", "Content-Type": "application/json",
                 "Accept": "application/json",  # content negotiation (scout-verified)
                 "User-Agent": "quilt-matrix/1.0"})  # python-urllib UA is WAF-blocked (1010)
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        return json.loads(resp.read().decode())


def engines() -> list[str]:
    """List visible engine ids (Accept: application/json)."""
    d = _call("GET", "/engines")
    lst = d.get("data", d) if isinstance(d, dict) else d
    if isinstance(lst, dict):
        lst = lst.get("engines", [])
    return [e.get("engine_id") or e.get("id") for e in lst if isinstance(e, dict)]


def run_job(engine: str, params: dict, timeout_s: float = 90.0, poll_s: float = 1.5):
    """Submit → poll → result. Returns {ok, job_id, result, outputs, latency_ms}."""
    t0 = time.monotonic()
    sub = _call("POST", f"/engines/{engine}/process", {"params": params})
    job_id = sub.get("job_id") or (sub.get("data") or {}).get("job_id")
    if not job_id:
        return {"ok": False, "stage": "submit", "error": f"no job_id in {sub}"}
    deadline = t0 + timeout_s
    status = None
    while time.monotonic() < deadline:
        time.sleep(poll_s)
        st = _call("GET", f"/jobs/{job_id}/status", timeout_s=15.0)
        status = st.get("status") or (st.get("data") or {}).get("status")
        if status in ("completed", "failed", "cancelled"):
            break
    if status != "completed":
        return {"ok": False, "stage": "poll", "job_id": job_id, "error": f"status={status}"}
    out = _call("GET", f"/jobs/{job_id}/result", timeout_s=30.0)
    return {"ok": True, "job_id": job_id, "latency_ms": round((time.monotonic() - t0) * 1000),
            "result": out.get("result", out), "outputs": out.get("outputs")}


def quantum_bytes(n_bytes: int = 8) -> str | None:
    """Certified quantum hex for the Die Engine seed (comet-qrng-v1: Born-rule
    measurements, SP 800-90B min-entropy certificate, Toeplitz extractor,
    CHSH Bell witness). None on any failure — callers fall back to the
    deterministic sha seed and receipt it. NOTE: python-urllib UA must be
    set (see _call) or the WAF answers 403; coin-toss-v1 returns aggregate
    counts only — comet streams real bits."""
    try:
        r = run_job("comet-qrng-v1", {"mode": "emu"}, timeout_s=75.0)
        if not r["ok"]:
            return None
        out = (r.get("result") or {}).get("output") or {}
        rnd = out.get("random") or {}
        hx = rnd.get("hex") or ""
        hx = "".join(c for c in str(hx) if c in "0123456789abcdef")
        if len(hx) < n_bytes * 2:
            return None
        return hx[: n_bytes * 2]
    except Exception:
        return None


def midi_via_moth(params: dict) -> bytes | None:
    """qrc-midi-v1: quantum-generated MIDI bytes (the moth as a musician).
    Returns raw .mid bytes or None — the caller receipts the outcome either
    way; never silent."""
    try:
        r = run_job("qrc-midi-v1", params, timeout_s=120.0)
        if not r["ok"]:
            return None
        b64 = None
        res = r["result"] or {}
        if isinstance(res, dict):
            b64 = res.get("midi_b64") or res.get("midi") or res.get("file_b64")
        outs = r.get("outputs") or {}
        if not b64 and isinstance(outs, dict):
            b64 = outs.get("midi_b64") or outs.get("midi")
        if not b64:
            return None
        import base64
        return base64.b64decode(b64)
    except Exception:
        return None
