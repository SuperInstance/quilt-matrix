"""engine/moth.py — mothquantum channel: certified entropy + quantum music.

Verified 2026-10-04 (night of the deep probe — docs/MOTH-PROBE.md, 97
receipted requests): the full qrc-midi-v1 contract is FOUND and the asset
flow is cracked. Truths this module now encodes:

  - Engines are async: POST /engines/{e}/process (JSON) → 202 {job_id} →
    poll GET /jobs/{id}/status until status == "completed" (NOT "succeeded"
    — we polled 40 rounds against the wrong word once) → GET /jobs/{id} for
    outputs[] ({slot, output_asset_id, content_type}).
  - Assets: POST /assets {filename, content_type, size_bytes} → 201 with a
    presigned S3 upload.url; PUT bytes there with NO auth headers (presigned
    signatures reject extra auth) and the EXACT registered content type;
    POST /assets/{id}/complete. Download is the mirror: GET
    /assets/{id}/download → {download_url} → raw GET.
  - qrc-midi-v1: {"input_files": {"midi": <asset_id>}, "params": {"bpm"}}.
    multipart is 415 (metadata lies); the error surface is cooperative —
    422s name the exact missing property. Engine needs ≥2 distinct notes.
  - comet-qrng-v1 {"mode":"emu"} → 32 certified bytes/call (SP 800-90B,
    Toeplitz, CHSH S≈2.8) — wired into quantum_bytes since the first night.
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


def _raw(method: str, url: str, data: bytes | None = None,
         headers: dict | None = None, timeout_s: float = 60.0) -> bytes:
    """Raw transport for presigned S3 URLs: NO Authorization/X-Api-Key (the
    signature IS the auth; extra headers corrupt it — observed 400), exact
    Content-Type, browser UA (S3 does not care, but consistency is free)."""
    h = {"User-Agent": "quilt-matrix/1.0"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, data=data, method=method, headers=h)
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        return resp.read()


def asset_upload(data: bytes, filename: str, content_type: str) -> str:
    """Three-step upload (MOTH-PROBE.md §2), all steps verified live.
    Returns asset_id. Raises on any step — callers receipt the outcome."""
    created = _call("POST", "/assets", {"filename": filename,
                                        "content_type": content_type,
                                        "size_bytes": len(data)})
    aid = created.get("asset_id") or (created.get("data") or {}).get("asset_id")
    up = created.get("upload") or {}
    url = up.get("url") if isinstance(up, dict) else None
    if not aid or not url:
        raise RuntimeError(f"asset create missing fields: {list(created)}")
    _raw("PUT", url, data, {"Content-Type": content_type})
    _call("POST", f"/assets/{aid}/complete", {})
    return aid


def asset_download(asset_id: str) -> bytes:
    """Mirror of upload: GET /assets/{id}/download → presigned GET → bytes."""
    d = _call("GET", f"/assets/{asset_id}/download")
    url = d.get("download_url") or d.get("url")
    if not url:
        raise RuntimeError(f"no download_url for {asset_id}")
    return _raw("GET", url)


def job_wait(job_id: str, timeout_s: float = 420.0, poll_s: float = 4.0) -> dict:
    """Poll /jobs/{id}/status to a TERMINAL state ('completed' — the moth's
    word, not 'succeeded'), then return the FULL /jobs/{id} record with
    outputs[]. Raises on failure/timeout."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        time.sleep(poll_s)
        st = _call("GET", f"/jobs/{job_id}/status", timeout_s=15.0)
        state = st.get("status") or (st.get("data") or {}).get("status")
        if state == "completed":
            return _call("GET", f"/jobs/{job_id}", timeout_s=30.0)
        if state in ("failed", "cancelled"):
            raise RuntimeError(f"job {job_id} {state}: {st.get('error')}")
    raise RuntimeError(f"job {job_id} timed out after {timeout_s}s")


def qrc_midi(midi_bytes: bytes, bpm: int = 120,
             timeout_s: float = 420.0) -> tuple[bytes | None, dict | None, dict]:
    """The full receipted round trip (MOTH-PROBE.md §4): upload the matrix's
    melody, let the quantum reservoir learn it, bring home the arrangement
    AND the learned model (the model is itself an artifact we keep).
    Returns (result_mid_bytes | None, model_dict | None, info)."""
    info: dict = {"pipeline": "qrc-midi-v1"}
    try:
        aid = asset_upload(midi_bytes, "jev-path.mid", "audio/midi")
        info["input_asset"] = aid
        sub = _call("POST", "/engines/qrc-midi-v1/process",
                    {"input_files": {"midi": aid}, "params": {"bpm": bpm}})
        jid = sub.get("job_id")
        if not jid:
            info["error"] = f"submit: {sub}"
            return None, None, info
        info["job"] = jid
        job = job_wait(jid, timeout_s=timeout_s)
        outs = job.get("outputs") or []
        res_aid = next((o["output_asset_id"] for o in outs
                        if o.get("slot") == "result"), None)
        mod_aid = next((o["output_asset_id"] for o in outs
                        if o.get("slot") == "model"), None)
        if res_aid:
            data = asset_download(res_aid)
            if data[:4] == b"MThd":
                info["result_bytes"] = len(data)
                info["ok"] = True
            else:
                info["error"] = "result is not SMF"
                data = None
        else:
            data, info["error"] = None, "no result slot"
        model = None
        if mod_aid:
            try:
                model = json.loads(asset_download(mod_aid).decode())
                info["model_keys"] = sorted(model)[:8]
            except Exception as e:  # model is a bonus, never fatal
                info["model_error"] = str(e)[:80]
        return data, model, info
    except Exception as e:
        info["error"] = str(e)[:160]
        return None, None, info


def midi_via_moth(params: dict) -> bytes | None:
    """Legacy shim (pre-contract). The probe-proven path is qrc_midi(); this
    shim now routes through it when given raw midi bytes under 'midi_bytes',
    else returns None (the old params-only submit shape was 415/422 — the
    route was never params-driven)."""
    raw = params.get("midi_bytes")
    if not raw:
        return None
    data, _model, _info = qrc_midi(raw, bpm=params.get("bpm", 120))
    return data
