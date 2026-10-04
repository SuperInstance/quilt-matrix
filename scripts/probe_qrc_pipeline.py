#!/usr/bin/env python3
"""Task 71-a finale: qrc-midi-v1 with a REAL matrix melody.

Pipeline proven end-to-end except musical content: asset flow works, submit
works, engine errors are semantic ("need at least 2 distinct notes"). Now feed
it night1's JEV walker melody (receipt-traced data -> pitch), upload, submit,
poll, save. The quantum reservoir rearranges the external mind's own tune.
"""
import json, sys, time, urllib.request, urllib.error

HERE = "/home/z/my-project/quilt-matrix"
sys.path.insert(0, HERE)
from engine.music import MidiWriter, jev_melody          # noqa: E402

API = "https://api.mothquantum.com/api/v1"
HDRS = {"Accept": "application/json", "User-Agent": "Mozilla/5.0 quilt-matrix-probe"}
KEY = ""
for line in open("/home/z/my-project/.env.keys"):
    if line.startswith("MOTH_API_KEY="):
        KEY = line.strip().split("=", 1)[1]
AUTH = {"Authorization": f"Bearer {KEY}", "X-Api-Key": KEY}
RECEIPTS = f"{HERE}/docs/moth-probe-receipts.json"
receipts = json.load(open(RECEIPTS))

def call(method, url, body=None, headers=None, label="", auth=True):
    h = dict(HDRS)
    if auth:
        h.update(AUTH)
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, data=body, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            data = r.read()
            receipts.append({"route": url.replace("https://api.mothquantum.com", "")[:90],
                             "method": method, "status": r.status, "verdict": "ok",
                             "label": label, "bytes": len(data)})
            return r.status, data, r.headers
    except urllib.error.HTTPError as e:
        data = e.read()
        receipts.append({"route": url.replace("https://api.mothquantum.com", "")[:90],
                         "method": method, "status": e.code, "verdict": f"http_{e.code}",
                         "label": label, "body_head": data[:300].decode("utf-8", "replace")})
        return e.code, data, e.headers
    except Exception as e:
        receipts.append({"route": url.replace("https://api.mothquantum.com", "")[:90],
                         "method": method, "status": 0, "verdict": f"error:{e}", "label": label})
        return 0, b"", {}

# 1. Compose input from night1 JEV receipts (kind=jev, payload.path node names).
# Mapping mirrors engine.music jev_melody: pentatonic degrees over two octaves,
# pitch a deterministic function of the node name the walker actually stood on.
import hashlib
jev_rows = []
for line in open(f"{HERE}/runs/night1/receipts.jsonl"):
    r = json.loads(line)
    if r.get("kind") == "jev":
        jev_rows.append(r)
print("jev receipts:", len(jev_rows))
PENTA = [0, 2, 4, 7, 9]
path_nodes = []
for r in jev_rows:
    path_nodes.extend(r.get("payload", {}).get("path", []))
print("total path nodes:", len(path_nodes))

mw = MidiWriter(tempo_bpm=112)
tick = 0
for i, node in enumerate(path_nodes[:64]):   # 64 eighth-notes of the walker's path
    h = int(hashlib.sha256(("mel" + node).encode()).hexdigest()[:8], 16)
    degree = h % 10
    pitch = 60 + PENTA[degree % 5] + 12 * (degree // 5)
    vel = 70 + (h % 40)
    mw.note(tick, 0, pitch, vel, 480 // 2)
    tick += 480 // 2
midi_bytes = mw.bytes()
distinct = len({int(hashlib.sha256(("mel" + n).encode()).hexdigest()[:8], 16) % 10
                for n in path_nodes[:64]})
print(f"melody: {min(len(path_nodes),64)} notes, {distinct} distinct pitches, "
      f"{len(midi_bytes)} bytes")
open("/tmp/jev-input.mid", "wb").write(midi_bytes)

# 2. Upload asset (proven flow: create -> PUT no-auth -> complete)
b = json.dumps({"filename": "jev-path.mid", "content_type": "audio/midi",
                "size_bytes": len(midi_bytes)}).encode()
st, data, _ = call("POST", f"{API}/assets", b, {"Content-Type": "application/json"},
                   label="asset create")
if st != 201:
    print("asset create failed:", st, data[:200]); sys.exit(1)
a = json.loads(data)
aid, up = a["asset_id"], a["upload"]["url"]
st, _, _ = call("PUT", up, midi_bytes, {"Content-Type": "audio/midi"},
                label="presigned PUT", auth=False)
print("PUT:", st)
st, data, _ = call("POST", f"{API}/assets/{aid}/complete", b"",
                   {"Content-Type": "application/json"}, label="asset complete")
print("complete:", st, json.loads(data).get("status") if st == 200 else data[:150])

# 3. Submit with THE contract
b = json.dumps({"input_files": {"midi": aid}, "params": {"bpm": 112}}).encode()
st, data, _ = call("POST", f"{API}/engines/qrc-midi-v1/process", b,
                   {"Content-Type": "application/json"}, label="qrc real melody")
print("submit:", st, data[:200])
if st not in (200, 202):
    sys.exit(1)
jid = json.loads(data)["job_id"]

# 4. Poll + fetch
out = f"{HERE}/runs/moth-qrc-jev-rearranged.mid"
for i in range(40):
    time.sleep(4)
    st3, d3, _ = call("GET", f"{API}/jobs/{jid}/status", label="poll")
    jj = json.loads(d3) if d3[:1] == b"{" else {}
    state = jj.get("status")
    print(f"poll {i}: {state}", str(jj.get("progress"))[:100])
    if state == "succeeded":
        print("JOB DONE:", json.dumps(jj)[:600])
        got = False
        for k in ("result_url", "output_url", "url", "download_url"):
            v = jj.get(k)
            if not v:
                continue
            for u in (v if isinstance(v, list) else [v]):
                u2 = u if isinstance(u, str) else (u.get("url") or "")
                if u2:
                    st4, d4, _ = call("GET", u2, label="result fetch", auth=False)
                    if st4 == 200 and d4[:4] == b"MThd":
                        open(out, "wb").write(d4)
                        print("QRC REARRANGEMENT SAVED:", len(d4), "bytes ->", out)
                        got = True
                        break
            if got:
                break
        if not got:
            # maybe result is itself an asset: GET /assets/{result_asset_id}
            ra = jj.get("result_asset_id") or jj.get("output_asset_id")
            print("no url keys; result asset:", ra, "| full keys:", list(jj.keys()))
        break
    if state == "failed":
        print("FAILED:", json.dumps(jj.get("error"))[:300]); break

json.dump(receipts, open(RECEIPTS, "w"), indent=1)
print("receipts:", len(receipts))
