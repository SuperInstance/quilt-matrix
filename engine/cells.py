"""engine/cells.py — the decomposed thinker's hands: small fast generator cells.

Doctrine (principal directive): "we don't want a giant model making up how
they did the answer after they just felt it internally. We want a model to
build its superstructure." So the generator cell is SMALL (8B-class), FAST,
and CONTEXT-STARVED ON PURPOSE: its only inputs are a role card, the question
of the round, and ≤6 rows of the spreadsheet (its "paper"). It cannot feel
the whole web internally — it must draw links between visible rows, which is
the granular chain-of-thought we actually want.

Channels, in order of preference:
  groq-relay — groq through the CF relay (smallest models, fastest) — DEAD
               for now: groq's edge rejects CF egress too (receipted 2026-10-04)
  cf-8b      — Cloudflare Workers AI @cf/meta/llama-3.1-8b-instruct — LIVE
               (same Meta 8B family as groq's llama-3.1-8b-instant; the
               documented stand-in during the groq block)

Output contract: strict JSON array. Anything else → mechanical gate rejects,
candidate becomes a scar. The cell never touches the matrix; it proposes.
"""

from __future__ import annotations
import json
import os
import time
import urllib.error
import urllib.request

PERSONAS = {
    "weaver":   ("Weaver", "propose the strongest MISSING connection between rows on your paper"),
    "trickster":("Trickster", "propose the strangest connection that could still be true between rows on your paper"),
    "surveyor": ("Surveyor", "propose a missing bridge concept that would connect distant clusters visible on your paper"),
}

REL_TYPES = ["supports", "contradicts", "resonates", "transforms", "feeds",
             "guards", "tminus", "echoes", "plays", "sounds", "bridges"]


def _cf_account() -> str:
    p = "/home/z/my-project/.env.keys"
    tok = os.environ.get("CLOUDFLARE_API_TOKEN", "")
    acct = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
    if not tok or not acct:
        # find the account id via the API (cached in scripts/.cf_account_id)
        if not tok:
            for line in open(p, encoding="utf-8"):
                if line.startswith("CLOUDFLARE_API_TOKEN="):
                    tok = line.split("=", 1)[1].strip()
                    break
        cache = "/home/z/my-project/scripts/.cf_account_id"
        if acct and os.path.exists(cache):
            pass
        elif os.path.exists(cache):
            acct = open(cache, encoding="utf-8").read().strip()
        else:
            req = urllib.request.Request("https://api.cloudflare.com/client/v4/accounts",
                                         headers={"Authorization": f"Bearer {tok}"})
            with urllib.request.urlopen(req, timeout=20) as r:
                acct = json.loads(r.read().decode())["result"][0]["id"]
            with open(cache, "w", encoding="utf-8") as f:
                f.write(acct)
    return acct


def _cf_run(model: str, messages: list[dict], max_tokens: int = 300,
            timeout_s: float = 45.0) -> str:
    tok = os.environ.get("CLOUDFLARE_API_TOKEN", "")
    if not tok:
        for line in open("/home/z/my-project/.env.keys", encoding="utf-8"):
            if line.startswith("CLOUDFLARE_API_TOKEN="):
                tok = line.split("=", 1)[1].strip()
                break
    url = (f"https://api.cloudflare.com/client/v4/accounts/{_cf_account()}"
           f"/ai/run/{model}")
    body = json.dumps({"messages": messages, "max_tokens": max_tokens}).encode()
    req = urllib.request.Request(url, data=body, headers={
        "Authorization": f"Bearer {tok}", "Content-Type": "application/json"})
    t0 = time.monotonic()
    with urllib.request.urlopen(req, timeout=timeout_s) as r:
        payload = json.loads(r.read().decode())
    ok = payload.get("success")
    if not ok:
        raise RuntimeError(f"cf run failed: {json.dumps(payload.get('errors'))[:200]}")
    res = payload["result"]
    # messages-mode returns OpenAI-style choices; raw-prompt mode returns .response
    if isinstance(res, dict) and res.get("choices"):
        text = res["choices"][0]["message"]["content"]
    elif isinstance(res, dict):
        text = res.get("response", "")
    elif isinstance(res, list):  # some models return message-object lists
        text = " ".join(str(m.get("content", "")) for m in res if isinstance(m, dict))
    else:
        text = str(res)
    routed = (res.get("model") if isinstance(res, dict) else None) or model
    return text, round((time.monotonic() - t0) * 1000), routed


def _groq_run(model: str, messages: list[dict], max_tokens: int = 300,
              timeout_s: float = 30.0) -> tuple[str, int]:
    """Groq via relay. The relay URL lives in scripts/.groq_relay_url.
    Currently RECEIPTED-DEAD at groq's edge (403 even via CF egress); kept so
    the lane flips on the moment groq relents — no code change needed."""
    url_file = "/home/z/my-project/scripts/.groq_relay_url"
    if not os.path.exists(url_file):
        raise RuntimeError("no relay url file")
    base = open(url_file, encoding="utf-8").read().strip()
    key = os.environ.get("GROQ_API_KEY", "")
    if not key:
        for line in open("/home/z/my-project/.env.keys", encoding="utf-8"):
            if line.startswith("GROQ_API_KEY="):
                key = line.split("=", 1)[1].strip()
                break
    body = json.dumps({"model": model, "messages": messages,
                       "max_tokens": max_tokens, "temperature": 1.0}).encode()
    req = urllib.request.Request(base + "/openai/v1/chat/completions", data=body,
                                 headers={"Authorization": f"Bearer {key}",
                                          "Content-Type": "application/json"})
    t0 = time.monotonic()
    with urllib.request.urlopen(req, timeout=timeout_s) as r:
        payload = json.loads(r.read().decode())
    return payload["choices"][0]["message"]["content"], round((time.monotonic() - t0) * 1000)


def complete(channel: str, messages: list[dict], max_tokens: int = 300,
             timeout_s: float = 45.0, model: str | None = None) -> tuple[str, int]:
    """Generic cell completion (runner composes family-specific prompts).
    Returns (text, latency_ms)."""
    if channel == "groq-relay":
        return _groq_run(model or "llama-3.1-8b-instant", messages, max_tokens, timeout_s)[:2]
    if channel == "cf-8b":
        return _cf_run(model or "@cf/meta/llama-3.1-8b-instruct",
                       messages, max_tokens, timeout_s)[:2]
    raise ValueError(f"unknown channel {channel}")


def parse_json_array(raw: str) -> tuple[list, str | None]:
    """Mechanical gate part 1: extract a JSON array from cell output.
    Tolerates a fenced block; refuses anything that isn't a JSON list."""
    txt = raw.strip()
    if txt.startswith("```"):
        txt = txt.strip("`")
        txt = txt.split("\n", 1)[-1] if "\n" in txt else txt
        txt = txt.rsplit("```", 1)[0]
    start, end = txt.find("["), txt.rfind("]")
    if start == -1 or end == -1 or end <= start:
        return [], "no JSON array found"
    try:
        arr = json.loads(txt[start:end + 1])
    except json.JSONDecodeError as e:
        return [], f"json decode: {e}"
    if not isinstance(arr, list):
        return [], "not a list"
    return arr, None


def generate(persona: str, question: str, paper_rows: list[dict],
             channel: str = "cf-8b", model: str | None = None) -> dict:
    """One cell pass. Returns {ok, proposals, channel, model, latency_ms, raw}.

    proposals: [{a, b, rel_type, note}] — candidate edges ONLY (names must
    come from the paper; the mechanical gate enforces existence).
    """
    name, mission = PERSONAS[persona]
    paper = json.dumps(paper_rows, separators=(",", ":"))
    sysmsg = (
        f"You are {name}, a small fast cell in a decomposed mind. Your mission: {mission}. "
        "Your ONLY knowledge is the paper (JSON rows of an idea-web: edge type and neighbor "
        "label with joy/entropy/value weights). Output STRICT JSON: "
        '[{"a":"<existing label>","b":"<existing label or new short concept>","rel_type":"<one of '
        + "|".join(REL_TYPES) + '>","note":"<=10 words"}] — 1 to 3 items, no prose, no markdown.'
    )
    user = f"PAPER: {paper}\n\nTASK: {question}"
    messages = [{"role": "system", "content": sysmsg}, {"role": "user", "content": user}]
    if channel == "groq-relay":
        raw, ms = _groq_run(model or "llama-3.1-8b-instant", messages)
    elif channel == "cf-8b":
        raw, ms = _cf_run(model or "@cf/meta/llama-3.1-8b-instruct", messages)
    else:
        raise ValueError(f"unknown channel {channel}")
    proposals, err = _parse_proposals(raw)
    return {"ok": err is None, "proposals": proposals, "parse_error": err,
            "channel": channel, "model": model or ("llama-3.1-8b-instant" if channel == "groq-relay"
                                                   else "@cf/meta/llama-3.1-8b-instruct"),
            "latency_ms": ms, "raw": raw[:400]}


def _parse_proposals(raw: str) -> tuple[list[dict], str | None]:
    """Mechanical gate part 1: extract JSON array from the cell's output.
    Tolerates a fenced block; refuses anything that isn't a JSON list."""
    txt = raw.strip()
    if txt.startswith("```"):
        txt = txt.strip("`")
        txt = txt.split("\n", 1)[-1] if "\n" in txt else txt
        txt = txt.rsplit("```", 1)[0]
    start, end = txt.find("["), txt.rfind("]")
    if start == -1 or end == -1 or end <= start:
        return [], "no JSON array found"
    try:
        arr = json.loads(txt[start:end + 1])
    except json.JSONDecodeError as e:
        return [], f"json decode: {e}"
    if not isinstance(arr, list):
        return [], "not a list"
    out = []
    for item in arr[:3]:
        if not isinstance(item, dict):
            continue
        a, b = item.get("a"), item.get("b")
        rel = item.get("rel_type", "resonates")
        if not a or not b or rel not in REL_TYPES:
            continue
        out.append({"a": str(a)[:40], "b": str(b)[:40], "rel_type": rel,
                    "note": str(item.get("note", ""))[:80]})
    if not out:
        return [], "no valid proposals after schema filter"
    return out, None
