#!/usr/bin/env python3
"""scripts/make_music.py — standalone pieces from a run's decomposed state.

Pieces (all deterministic replays of receipted state — rewind the run and
you get the same music):
  full_suite.mid  — the whole run: one bar per round; chord from the round's
                    mutation, melody from the round's JEV walk, one percussion
                    hit per sticky scar, duet notes from the winning cells.
  jev_drone.mid   — the balance of the web as a sustained drone whose tremolo
                    follows round-by-round joy/entropy spread.
  die_etudes.mid  — 20 bars, one per die face; bucket changes the interval
                    texture (the Die Engine as composer).
  moth_qrc.mid    — REAL quantum-generated MIDI via mothquantum qrc-midi-v1
                    (the moth as a musician). Receipted either way; falls
                    back to a moth-bit-seeded local etude if the engine
                    refuses — never silent.

Usage: python3 scripts/make_music.py --run runs/night1
"""

from __future__ import annotations
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from engine import die, moth  # noqa: E402
from engine.music import (MidiWriter, duet_note, die_etude, jev_melody,  # noqa: E402
                          round_chord, scar_hit)
from engine.receipts import Ledger, ScarLog  # noqa: E402


def full_suite(run_dir: str) -> str:
    led = Ledger(os.path.join(run_dir, "receipts.jsonl"))
    scars = ScarLog(os.path.join(run_dir, "scars.jsonl"))
    w = MidiWriter(tempo_bpm=104)
    w.program(0, 73)  # melody: flute
    w.program(1, 89)  # chords: warm pad
    w.program(2, 32)  # weaver voice
    w.program(3, 33)  # trickster voice
    walks = {x["round"]: x for x in led.lines if x["kind"] == "jev"}
    muts = {x["round"]: x for x in led.lines if x["kind"] == "mutation"}
    mhash = led.lines[-1]["matrix_hash"] if led.lines else "genesis"
    rounds = sorted(walks)
    for i, r in enumerate(rounds):
        mut = muts.get(r)
        rel, ent, top = "resonates", 0.5, [0.5, 0.4, 0.3]
        if mut:
            p = mut["payload"]
            rel = p.get("rel", p.get("mode", rel))
            v = p.get("value")
            if isinstance(v, (int, float)):
                top = [v, min(1.0, v + 0.1), max(0.0, v - 0.1)]
            e = p.get("entropy")
            if isinstance(e, (int, float)):
                ent = e
        round_chord(w, i, mhash + str(r), rel, top, ent)
        path = walks[r]["payload"].get("path")
        if isinstance(path, list):
            jev_melody(w, i, path, mhash + str(r), ent)
        for j, s in enumerate([x for x in scars.lines if x["round"] == r]):
            scar_hit(w, i, j)
        # duet: winner payloads this round (from mutation receipts w/ winner meta)
        # the runner stored duet data per process; reconstruct from ledger:
        if mut and isinstance(mut["payload"], dict):
            fam = mut["payload"].get("family", "")
            if fam in ("DECOMP", "BRIDGE", "TMSEQ"):
                v = mut["payload"].get("value", 0.5)
                v = v if isinstance(v, (int, float)) else 0.5
                e = mut["payload"].get("entropy", 0.4)
                e = e if isinstance(e, (int, float)) else 0.4
                duet_note(w, i, 2 if r % 2 else 3, float(v), float(e), f"{fam}:{r}")
    out = os.path.join(run_dir, "music", "full_suite.mid")
    w.write(out)
    return out


def jev_drone(run_dir: str) -> str:
    """The web's balance, sustained. One long note per 4 rounds; tremolo
    velocity follows the joy/entropy spread of the web at that round."""
    board = os.path.join(run_dir, "leaderboard.csv")
    import csv
    with open(board, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    w = MidiWriter(tempo_bpm=60)
    w.program(0, 52)  # choir-ish pad
    for i, row in enumerate(rows):
        bal = float(row["balance"])
        bars = 1
        tick = i * bars * 4 * 480
        # tremolo: 8 half-beat re-articulations of the same pitch
        for k in range(8):
            vel = int(30 + bal * 60 + (k % 2) * 12)
            w.note(tick + k * 240, 0, 36 + int(bal * 12), vel, 240)
    out = os.path.join(run_dir, "music", "jev_drone.mid")
    w.write(out)
    return out


def die_etudes(run_dir: str) -> str:
    w = MidiWriter(tempo_bpm=132)
    w.program(3, 30)  # overdriven guitar: the die is loud
    for face in range(1, 21):
        die_etude(w, face - 1, face)
    out = os.path.join(run_dir, "music", "die_etudes.mid")
    w.write(out)
    return out


def moth_qrc(run_dir: str) -> tuple[str, str]:
    """The moth as a musician: qrc-midi-v1 quantum MIDI. Receipted either way."""
    led = Ledger(os.path.join(run_dir, "receipts.jsonl"))
    raw = moth.midi_via_moth({"mode": "emu", "length": 64, "scale": "pentatonic"})
    out = os.path.join(run_dir, "music", "moth_qrc.mid")
    if raw and raw[:4] == b"MThd":
        with open(out, "wb") as f:
            f.write(raw)
        led.append("music", 0, {"piece": "moth_qrc.mid", "source": "qrc-midi-v1",
                                "bytes": len(raw), "mode": "live-quantum"},
                   os.path.join(run_dir, "matrix") and _mh(run_dir))
        return out, "live-quantum"
    # honest fallback: moth BITS seed a local pentatonic etude
    hx = moth.quantum_bytes(8) or ""
    seed = f"moth:{hx}" if hx else "sha:fallback-moth-unreachable"
    w = MidiWriter(tempo_bpm=96)
    w.program(0, 11)  # vibraphone
    from engine.music import _deg_to_pitch
    for i in range(32):
        face = die.d20(f"{seed}:{i}")
        step = die.d20(f"{seed}:{i}:b")
        w.note(i * 240, 0, _deg_to_pitch(57, "pentatonic", step), 60 + face * 3, 220)
    w.write(out)
    led.append("music", 0, {"piece": "moth_qrc.mid", "source": "local-etude",
              "reason": "qrc-midi-v1 unavailable", "moth_bits": bool(hx)},
              _mh(run_dir))
    return out, "local-etude (receipted)"


def _mh(run_dir: str) -> str:
    from engine.matrix import Matrix
    return Matrix(os.path.join(run_dir, "matrix")).load().matrix_hash()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--skip-moth", action="store_true")
    args = ap.parse_args()
    run_dir = os.path.join(HERE, args.run) if not os.path.isabs(args.run) else args.run
    print("full_suite:", full_suite(run_dir))
    print("jev_drone:", jev_drone(run_dir))
    print("die_etudes:", die_etudes(run_dir))
    if not args.skip_moth:
        p, how = moth_qrc(run_dir)
        print(f"moth_qrc: {p} [{how}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
