# MOTH-PROBE.md — the moth's real contract, learned by probing (Task 71-a)

Every claim below cites an HTTP status actually observed and recorded in
`moth-probe-receipts.json` (97 receipted requests across probe rounds). The
moth API publishes `openapi.json` (GET, 200, 387 KB) — the definitive source
we consulted AFTER behavior-probing; both agree.

## 1. The async job pattern (the big discovery)

All heavy engines are async. The earlier 415s at `/process` were us knocking
on a door that moved.

```
POST /api/v1/engines/{engine}/process     JSON body → 202 {job_id, status:"queued"}
GET  /api/v1/jobs/{job_id}/status         → 200 {status: "queued"|"running"|"completed"|"failed", progress:{step,detail}}
GET  /api/v1/jobs/{job_id}                → 200 full record incl. outputs[]
```

⚠️ Terminal state is **`"completed"`**, not `"succeeded"`. We polled 40× against
the wrong word before noticing the engine had finished saying `Writing N
generated notes to MIDI` the whole time.

Outputs live on the full job record, not the status endpoint:

```json
"outputs": [
  {"slot": "model",  "output_asset_id": "<uuid>", "content_type": "application/json"},
  {"slot": "result", "output_asset_id": "<uuid>", "content_type": "audio/midi"}
]
```

## 2. The assets flow (upload AND download are presigned)

Upload (all three steps required):

```
POST /api/v1/assets    {"filename","content_type","size_bytes"} → 201
                       body has asset_id + upload.url (S3 presigned PUT)
PUT  <upload.url>      raw bytes, Content-Type EXACTLY as registered,
                       and NO Authorization/X-Api-Key headers (presigned
                       signatures reject extra auth) → 200
POST /api/v1/assets/{id}/complete → 200, asset status "uploaded"
```

The API's 422 errors are cooperative: they name the exact missing property
(`expected required property size_bytes to be present`). We bootstrapped the
whole request schema from the error messages alone before consulting the spec.

Download:

```
GET /api/v1/assets/{id}/download → 200 {"download_url": <presigned GET>}
GET <download_url>               → raw bytes (no auth headers)
```

## 3. qrc-midi-v1 — contract FOUND (bone closed)

"Sequence MIDI with a quantum reservoir — learn the notes of a file and
generate a new arrangement as a fresh .mid." (engine metadata, 200)

```
POST /api/v1/engines/qrc-midi-v1/process
Content-Type: application/json
{"input_files": {"midi": "<asset_id>",            # audio/midi (audio/x-midi ok)
                 "model": "<asset_id>"},          # optional, application/json
 "params": {"bpm": 120}}                          # tempo of output; durations preserved
→ 202 → poll → outputs: model (the learned reservoir, 18 KB JSON with
vocabulary/readout_weights/internal_state/training_loss) + result (.mid)
```

Engine-level constraints observed: `need at least 2 distinct notes to work
with (got 1)` (our first upload was a single-pitch test tone — failed with a
*musical* complaint, proving the pipeline itself was already correct).
Metadata's `input_type: multipart/form-data` is WRONG — multipart gets 415
`unknown content type`; the route is JSON-only (spec agrees).

## 4. The closed loop we actually ran (all receipted)

1. night1's 106 JEV receipts → walker path node names → pentatonic melody
   (same hash→degree mapping family as `engine/music.py`), 64 eighth-notes
2. asset `jev-path.mid` uploaded (201 → 200 PUT → 200 complete)
3. job submitted with `input_files.midi` → 202
4. quantum reservoir trained (`training_loss` in returned model)
5. `runs/moth-qrc-jev-rearranged.mid` downloaded (valid SMF) +
   `runs/moth-qrc-model.json` (the learned reservoir, reusable as future input)

The external mind's own chain-of-thought, rearranged by a quantum reservoir.
The model it learned is itself an artifact we keep — receipted round-trip.

## 5. Entropy modes

`comet-qrng-v1` `{"mode":"emu"}` → 32 certified bytes/call (SP 800-90B
min-entropy + Toeplitz extraction + CHSH witness S≈2.8) — this was already
wired into `engine/moth.py` (`quantum_bytes`). Job-based too (202 → poll).
Non-emu modes: not found in the spec's params for this engine; we call the
emulated channel "certifiedentropy, receipted provenance" and say nothing
stronger than the certificate does.

## 6. Engine inventory

32 engines listed (GET /engines). Music/entropy-relevant subset, all probed:

| engine | purpose (per metadata) | status |
|---|---|---|
| qrc-midi-v1 | quantum-reservoir MIDI arrangement | **WORKING** (contract above) |
| qrc-audio-v1 | audio rendering | probed, same job pattern |
| qrc-train-v2 | reservoir training | probed, same job pattern |
| qrc-gen-v2 | reservoir generation | probed, same job pattern |
| blur-midi-v1 | MIDI blur | probed, same job pattern |
| comet-qrng-v1 | certified entropy | **WORKING** (wired into engine) |

Full metadata for all 32: `moth-engines.json`.

## 7. Probing etiquette

~110 requests total across the night (38 + 12 + 1 + 5 + the successful
pipeline), all GETs idempotent or explicitly intended mutations (assets,
jobs), all receipted. The moth's cooperative 422s made this a conversation,
not a brute force: the gate that names what it refuses.
