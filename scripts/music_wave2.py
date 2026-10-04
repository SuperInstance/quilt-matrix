"""scripts/music_wave2.py — second wave: the ledger itself is the score.

Four new forms, every note a deterministic function of receipted run data
(no hand-picked pitches anywhere).  Reuses engine/music.py's zero-dep
MidiWriter and its pitch math (MODES / _deg_to_pitch / round_chord):

  1. scar_counterpoint.mid  — night1's 65 sticky scars as a cantus firmus
                              (phrygian), night2's 19 scars as a first-
                              species counterpoint in contrary motion,
                              verticals constrained to 3rds/5ths/6ths/8ves.
  2. ledger_canon.mid       — strict canon at the fifth: leader = first
                              32 receipt hashes of night1 (first hex byte →
                              degree), follower a fifth higher, delayed 8
                              sixteenths; night2's first 32 as a free bass.
  3. jev_tension_fugue.mid  — three-voice fugue over the 106 JEV walker
                              receipts: subject = joy trajectory, answer =
                              inverted value at the fifth, countersubject =
                              entropy; episodes at degree-zero nodes/motion.
  4. rewind_palinode.mid    — night1 rounds 8→40 as round-chords, then the
                              literal retrograde (hinge = the round-40
                              rewind receipt); the scar-hit percussion is
                              NOT retrograded — scars persist.

Run:  python3 scripts/music_wave2.py   (from the repo root)
Out:  music/scar_counterpoint.mid, music/ledger_canon.mid,
      music/jev_tension_fugue.mid, music/rewind_palinode.mid
Every file is re-parsed by a tiny SMF validator below and must pass.
"""

from __future__ import annotations
import csv
import json
import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine.music import (  # noqa: E402
    MidiWriter, TPQ, MODES, REL_TO_MODE, _deg_to_pitch, round_chord,
)

RUNS = os.path.join(ROOT, "runs")
OUT = os.path.join(ROOT, "music")
N1, N2 = os.path.join(RUNS, "night1"), os.path.join(RUNS, "night2")

MODE_TO_REL = {}
for _rel, _mode in REL_TO_MODE.items():
    MODE_TO_REL.setdefault(_mode, _rel)  # first rel wins; deterministic


# ────────────────────────────── data loaders ─────────────────────────────────
def load_jsonl(path):
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def load_csv(path):
    with open(path) as f:
        return list(csv.DictReader(f))


def floats_of(payload):
    return [v for v in payload.values() if isinstance(v, (int, float))
            and not isinstance(v, bool)]


def balance_map(night_dir):
    return {int(r["round"]): float(r["balance"])
            for r in load_csv(os.path.join(night_dir, "leaderboard.csv"))}


def scar_entropy(scar, bal):
    """Per-scar receipted entropy: mean of the scar's own payload floats
    (distinct/essential/bridges/repairable/suspicious/fits); scars with no
    numeric payload (cell-indeterminate) take the web's disorder 1-balance
    at their round."""
    fl = floats_of(scar["payload"])
    if fl:
        return sum(fl) / len(fl)
    return 1.0 - bal.get(scar["round"], 0.96)


# ═══════════════════════ 1. scar_counterpoint.mid ═══════════════════════════
def compose_scar_counterpoint(path):
    """Cantus firmus: night1's 65 scars, one whole note each, entropy →
    phrygian degree (2 octaves).  Counterpoint: night2's 19 scars cycled
    against them (index i mod 19 — matching scar round numbers modulo the
    other voice's count), first species, contrary motion, verticals forced
    to 3rd/5th/6th/8ve by (round_n1 + round_n2) mod 4; parallel perfects
    avoided by advancing the consonance slot."""
    w = MidiWriter(tempo_bpm=100)
    bal1, bal2 = balance_map(N1), balance_map(N2)
    scars1 = load_jsonl(os.path.join(N1, "scars.jsonl"))     # 65, round-sorted
    scars2 = load_jsonl(os.path.join(N2, "scars.jsonl"))     # 19, round-sorted

    ent1 = [scar_entropy(s, bal1) for s in scars1]
    ent2 = [scar_entropy(s, bal2) for s in scars2]
    cf_deg = [min(13, round(e * 13.99)) for e in ent1]       # 2 octaves max

    tonic = 52                                               # E3, phrygian
    steps_for = [2, 4, 5, 7]                                 # 3rd,5th,6th,8ve
    dur = 4 * TPQ * 95 // 100
    prev_steps = None
    prev_dir = 1
    for i, s1 in enumerate(scars1):
        s2 = scars2[i % len(scars2)]
        slot = (s1["round"] + s2["round"]) % 4
        steps = steps_for[slot]
        if prev_steps == steps and steps in (4, 7):          # parallel-perfect guard
            slot = (slot + 1) % 4
            steps = steps_for[slot]
        motion = (cf_deg[i] - cf_deg[i - 1]) if i else 0
        direction = (-1 if motion > 0 else 1) if motion else prev_dir  # contrary
        cp_deg = cf_deg[i] + direction * steps
        if not 0 <= cp_deg <= 20:                            # range clamp → flip
            direction = -direction
            cp_deg = cf_deg[i] + direction * steps
        prev_steps, prev_dir = steps, direction

        tick = i * 4 * TPQ
        # cantus firmus (channel 0), soft and low
        w.note(tick, 0, _deg_to_pitch(tonic, "phrygian", cf_deg[i]),
               58 + int(ent1[i] * 30), dur)
        # counterpoint (channel 1), a shade louder
        w.note(tick, 1, _deg_to_pitch(tonic, "phrygian", cp_deg),
               40 + int(ent2[i % len(scars2)] * 80), dur)
    w.write(path)
    return len(scars1), len(scars2)


# ═══════════════════════════ 2. ledger_canon.mid ════════════════════════════
def compose_ledger_canon(path):
    """Leader: night1 receipts idx 0..31 — first hex byte of each line's
    hash → dorian degree (byte mod 7), one quarter-note each.  Follower:
    the same bytes a diatonic fifth higher, entering 8 sixteenths late.
    Free bass: night2 receipts idx 0..31, same hash treatment, running
    eighths two octaves down."""
    w = MidiWriter(tempo_bpm=88)
    recs1 = load_jsonl(os.path.join(N1, "receipts.jsonl"))[:32]
    recs2 = load_jsonl(os.path.join(N2, "receipts.jsonl"))[:32]

    lead = [(int(r["hash"][:2], 16)) for r in recs1]
    bass = [(int(r["hash"][:2], 16)) for r in recs2]
    leader_root, sixteenth = 62, TPQ // 4
    delay = 8 * sixteenth                                    # 8 sixteenths
    q_dur = TPQ * 9 // 10
    follower_root = leader_root + 7                          # the dominant

    for i, byte in enumerate(lead):
        d = byte % len(MODES["dorian"])
        lp = _deg_to_pitch(leader_root, "dorian", d)
        # strict real canon: follower = leader transposed a perfect fifth up
        # (D dorian → A dorian, the dominant); dorian's diatonic 5th is
        # diminished on degree 5, so we transpose pitches, not degrees.
        fp = _deg_to_pitch(follower_root, "dorian", d)
        assert fp - lp == 7, "canon at the fifth must be +7 semitones"
        vel = 56 + byte % 40
        w.note(i * TPQ, 0, lp, vel, q_dur)                   # leader
        w.note(i * TPQ + delay, 1, fp, vel, q_dur)           # follower
    for i, byte in enumerate(bass):                          # free bass
        d = byte % len(MODES["dorian"])
        w.note(i * (TPQ // 2), 2, _deg_to_pitch(38, "dorian", d),
               44 + byte % 36, TPQ // 2 * 9 // 10)
    w.write(path)
    return len(lead), len(bass)


# ═══════════════════════ 3. jev_tension_fugue.mid ═══════════════════════════
def compose_jev_tension_fugue(path):
    """Three voices over night1's 106 jev receipts (leaderboard.csv carries
    no JEV columns, so the walker ledger is the score).  Position p = the
    walker's node at receipt p; weights read from matrix/nodes.csv.
    Subject (ch0) = joy, from position 0; answer (ch1) = inverted value
    (1-value) at the dominant, from position 16; countersubject (ch2) =
    entropy, from position 32.  Episode triggers (receipted): the walker
    standing on a graph-degree-zero node of edges.csv, or a walk that never
    leaves its start node (path length 1) — at those steps the subject
    plays its melodic inversion about the modal fifth (deg → 16-deg)."""
    nodes = {r["id"]: r for r in load_csv(os.path.join(N1, "matrix", "nodes.csv"))}
    deg = {}
    for e in load_csv(os.path.join(N1, "matrix", "edges.csv")):
        deg[e["src"]] = deg.get(e["src"], 0) + 1
        deg[e["dst"]] = deg.get(e["dst"], 0) + 1
    walks = [d for d in load_jsonl(os.path.join(N1, "receipts.jsonl"))
             if d["kind"] == "jev"]

    w = MidiWriter(tempo_bpm=104)
    step = TPQ // 2                                          # eighth-note grid
    dur = step * 9 // 10
    episodes = 0
    for p, rec in enumerate(walks):
        walked = rec["payload"]["path"]
        cur = walked[-1] if walked else rec["payload"]["start"]
        row = nodes[cur]
        joy, value, entropy = (float(row["joy"]), float(row["value"]),
                               float(row["entropy"]))
        is_episode = deg.get(cur, 0) == 0 or len(walked) == 1
        episodes += is_episode
        tick = p * step

        d_joy = round(joy * 13.99)
        if is_episode:                                       # episode: inversion
            d_joy = max(0, 16 - d_joy)
        w.note(tick, 0, _deg_to_pitch(62, "dorian", d_joy),
               64 + int(joy * 40), dur)                      # subject: joy
        if p >= 16:                                          # answer: 1-value @5th
            w.note(tick, 1, _deg_to_pitch(69, "dorian", round((1 - value) * 13.99)),
                   56 + int(value * 40), dur)
        if p >= 32:                                          # countersubject: entropy
            w.note(tick, 2, _deg_to_pitch(50, "dorian", round(entropy * 13.99)),
                   48 + int(entropy * 40), dur)
    w.write(path)
    return len(walks), episodes


# ═══════════════════════ 4. rewind_palinode.mid ═════════════════════════════
def compose_rewind_palinode(path):
    """Night1 rounds 8..40 as engine round_chords (forward), then the same
    progression retrograded with its voicing reversed — the music un-composes
    itself.  Hinge = the round-40 rewind receipt (idx 265, scars_preserved
    22): its matrix_hash picks the root, scars_preserved/to_round voices it,
    and a raw percussion accent marks the fold.  Scar hits (night1 scars,
    rounds 8..40) sound at both passes' bar positions in FORWARD order —
    the percussion never un-plays; scars persist."""
    recs = load_jsonl(os.path.join(N1, "receipts.jsonl"))
    bal = balance_map(N1)
    sound_mode = {int(r["round"]): r["mode"]
                  for r in load_csv(os.path.join(N1, "sound.csv"))}
    scars1 = [s for s in load_jsonl(os.path.join(N1, "scars.jsonl"))
              if 8 <= s["round"] <= 40]
    rewind = next(d for d in recs if d["kind"] == "rewind")

    VERB_MODE = {"delta": "dorian", "confirmed": "major", "fun": "lydian",
                 "brightness": "mixolydian", "bridges": "pentatonic",
                 "fits": "phrygian", "before": "minor"}
    PRIORITY = ["value", "entropy", "joy", "bridges", "fits", "brightness",
                "fun", "delta", "weight", "before", "distinct", "essential"]

    rounds = list(range(8, 41))
    chords = {}
    for r in rounds:
        muts = [d["payload"] for d in recs
                if d["kind"] == "mutation" and d["round"] == r]
        rel = next((m["rel"] for m in muts if "rel" in m), None)
        if rel:
            mode = REL_TO_MODE.get(rel, "minor")
        elif r in sound_mode:                                # receipted sound telemetry
            mode = sound_mode[r]
        else:
            verb = next((k for m in muts for k in PRIORITY if k in m), None)
            mode = VERB_MODE.get(verb, "minor")
        vals = []
        for m in muts:
            ordered = sorted((k for k in m if isinstance(m[k], (int, float))
                              and not isinstance(m[k], bool)),
                             key=lambda k: PRIORITY.index(k) if k in PRIORITY else 99)
            vals += [m[k] for k in ordered]
        vals = vals[:4] or [bal[r]]
        ent = next((m["entropy"] for m in muts if "entropy" in m),
                   1.0 - bal[r])
        matrix_hash = [d for d in recs if d["round"] == r][-1]["matrix_hash"]
        chords[r] = (matrix_hash, MODE_TO_REL[mode], vals, ent)

    w = MidiWriter(tempo_bpm=112)
    for i, r in enumerate(rounds):                           # forward 8→40
        mh, rel, vals, ent = chords[r]
        round_chord(w, i, mh, rel, vals, ent)
    # hinge: the rewind receipt itself
    hinge_vals = [rewind["payload"]["scars_preserved"] /
                  rewind["payload"]["to_round"]]            # 22/40
    round_chord(w, len(rounds), rewind["matrix_hash"],
                MODE_TO_REL["minor"], hinge_vals, 1.0 - bal[40])
    w.note(len(rounds) * 4 * TPQ, 9, 38, 110, TPQ // 4)     # sticky accent
    for k, r in enumerate(reversed(rounds)):                 # retrograde 40→8
        mh, rel, vals, ent = chords[r]
        round_chord(w, len(rounds) + 1 + k, mh, rel, vals[::-1], ent)

    def scar_hit(bar, j):                                    # un-retrograded
        tick = bar * 4 * TPQ + TPQ // 2 + (j % 4) * (TPQ // 16)
        w.note(tick, 9, 38 if j % 2 == 0 else 42, 90, TPQ // 8)

    for j, s in enumerate(scars1):
        scar_hit(s["round"] - 8, j)                          # forward pass
    for j, s in enumerate(scars1):                           # same order, second pass
        scar_hit(len(rounds) + 1 + (40 - s["round"]), j)
    w.write(path)
    return len(rounds) * 2 + 1, len(scars1) * 2


# ─────────────────────────── tiny SMF validator ──────────────────────────────
def _vlq(data, i):
    n = 0
    for _ in range(4):
        b = data[i]; i += 1
        n = (n << 7) | (b & 0x7F)
        if not b & 0x80:
            return n, i
    raise ValueError("bad VLQ")


def validate_smf(path):
    """Assert header chunk MThd (fmt/ntrks/division), MTrk chunk(s) with
    well-formed event stream (running status supported) and End-of-Track;
    return stats: format, tracks, note-ons, last tick, ticks-per-quarter."""
    with open(path, "rb") as f:
        data = f.read()
    assert data[:4] == b"MThd", f"{path}: missing MThd"
    (hlen,) = struct.unpack(">I", data[4:8])
    assert hlen == 6, f"{path}: bad header length {hlen}"
    fmt, ntrks, division = struct.unpack(">HHH", data[8:14])
    assert division == TPQ, f"{path}: division {division}"
    pos = 8 + hlen
    tracks = note_ons = 0
    last_tick = 0
    while pos < len(data):
        tag, length = data[pos:pos + 4], struct.unpack(">I", data[pos + 4:pos + 8])[0]
        chunk = data[pos + 8:pos + 8 + length]
        pos += 8 + length
        if tag != b"MTrk":
            continue
        tracks += 1
        i, tick, running, eot = 0, 0, None, False
        while i < len(chunk):
            delta, i = _vlq(chunk, i)
            tick += delta
            status = chunk[i]
            if status & 0x80:
                i += 1
                running = status if status < 0xF0 else None
            else:
                assert running is not None, f"{path}: running status without anchor"
                status = running
            if status == 0xFF:
                mtype = chunk[i]; i += 1
                mlen, i = _vlq(chunk, i)
                if mtype == 0x2F:
                    eot = True
                i += mlen
            elif status in (0xF0, 0xF7):
                slen, i = _vlq(chunk, i)
                i += slen
            else:
                high = status & 0xF0
                nbytes = 1 if high in (0xC0, 0xD0) else 2
                b1 = chunk[i] if nbytes >= 1 else 0
                b2 = chunk[i + 1] if nbytes == 2 else 0
                i += nbytes
                if high == 0x90 and b2 > 0:
                    note_ons += 1
                last_tick = max(last_tick, tick)
        assert eot, f"{path}: track {tracks} missing End-of-Track"
    assert pos == len(data), f"{path}: trailing garbage"
    assert tracks == ntrks, f"{path}: header says {ntrks} tracks, found {tracks}"
    return {"format": fmt, "tracks": tracks, "notes": note_ons,
            "last_tick": last_tick, "tpq": division}


# ─────────────────────────────────── main ────────────────────────────────────
def main():
    os.makedirs(OUT, exist_ok=True)
    jobs = [
        ("scar_counterpoint.mid", compose_scar_counterpoint,
         "night1 65 scars ↔ night2 19 scars, contrary-motion species CP"),
        ("ledger_canon.mid", compose_ledger_canon,
         "canon at the fifth over the first 32+32 receipt hashes"),
        ("jev_tension_fugue.mid", compose_jev_tension_fugue,
         "3-voice fugue: joy / inverted value / entropy over 106 walker receipts"),
        ("rewind_palinode.mid", compose_rewind_palinode,
         "rounds 8→40 forward + retrograde, rewind receipt as hinge"),
    ]
    print("wave 2 — receipt-traced compositions\n" + "=" * 62)
    ok = 0
    for name, fn, desc in jobs:
        info = fn(os.path.join(OUT, name))
        st = validate_smf(os.path.join(OUT, name))           # must parse as SMF
        bpm = {"scar_counterpoint.mid": 100, "ledger_canon.mid": 88,
               "jev_tension_fugue.mid": 104, "rewind_palinode.mid": 112}[name]
        secs = st["last_tick"] / st["tpq"] * 60.0 / bpm
        print(f"{name}\n  {desc}")
        print(f"  data: {info}")
        print(f"  SMF:  format {st['format']}, {st['tracks']} track(s), "
              f"{st['notes']} notes, {st['last_tick']} ticks "
              f"({secs:.1f}s @ {bpm}bpm) — VALID\n")
        ok += 1
    assert ok == 4, "not all forms validated"
    print("all four forms parse as valid Standard MIDI Files")


if __name__ == "__main__":
    main()
