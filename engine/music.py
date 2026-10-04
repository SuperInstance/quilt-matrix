"""engine/music.py — the web listens to itself: weights → standard MIDI files.

"play and even attempt to make music in all sorts of ways with these
decomposed systems" (principal directive). This file is a zero-dependency
Standard MIDI File (SMF) writer plus the mappings from spreadsheet weights
to sound. Every piece is a deterministic function of run state — replay the
run, get the same music. Scar hits are percussion: the system's failures are
literally audible in the mix, and they survive rewind the same way the scars
do (they are re-emitted from the sticky scar log).

Mappings (documented again in MUSIC.md):
  round chord   — per round: root from matrix hash, mode from the round's
                  dominant rel_type, voicing from top edge values, velocity
                  from value, duration from entropy.
  jev melody    — the walker's path → scale degrees; the chain-of-thought
                  made audible.
  scar hit      — one channel-10 hit per scar at the scar's round position.
  cell duet     — per persona channel: accepted proposals become notes
                  (pitch from weight, so voices that build high-value
                  structures sing higher).
  die etudes    — 20 bars, one per die face, pattern from face bucket.
"""

from __future__ import annotations
import hashlib
import struct

TPQ = 480
MODES = {
    "major":     [0, 2, 4, 5, 7, 9, 11],
    "minor":     [0, 2, 3, 5, 7, 8, 10],
    "dorian":    [0, 2, 3, 5, 7, 9, 10],
    "phrygian":  [0, 1, 3, 5, 7, 8, 10],
    "lydian":    [0, 2, 4, 6, 7, 9, 11],
    "mixolydian":[0, 2, 4, 5, 7, 9, 10],
    "pentatonic":[0, 2, 4, 7, 9],
}
REL_TO_MODE = {"supports": "major", "resonates": "lydian", "transforms": "dorian",
               "echoes": "pentatonic", "feeds": "mixolydian", "contradicts": "phrygian",
               "tminus": "minor", "guards": "minor", "plays": "major", "sounds": "dorian",
               "bridges": "pentatonic"}


# ─────────────────────────── minimal SMF writer ──────────────────────────────
def _vlq(n: int) -> bytes:
    """MIDI variable-length quantity."""
    out = [n & 0x7F]
    n >>= 7
    while n:
        out.append((n & 0x7F) | 0x80)
        n >>= 7
    return bytes(reversed(out))


def _chunk(tag: bytes, data: bytes) -> bytes:
    return tag + struct.pack(">I", len(data)) + data


class MidiWriter:
    """Format 0 SMF: one track, multiple channels. Deterministic bytes."""

    def __init__(self, tempo_bpm: int = 110):
        self.events: list[tuple[int, bytes]] = []  # (tick, raw bytes)
        self.tempo_bpm = tempo_bpm

    def note(self, tick: int, chan: int, pitch: int, vel: int, dur_ticks: int) -> None:
        self.events.append((tick, bytes([0x90 | chan, pitch & 0x7F, vel & 0x7F])))
        self.events.append((tick + dur_ticks, bytes([0x80 | chan, pitch & 0x7F, 0])))

    def program(self, chan: int, prog: int) -> None:
        self.events.append((0, bytes([0xC0 | chan, prog & 0x7F])))

    def bytes(self) -> bytes:
        tempo_us = int(60_000_000 / self.tempo_bpm)
        head = _chunk(b"MThd", struct.pack(">HHH", 0, 1, TPQ))
        evs = sorted(self.events, key=lambda x: (x[0], x[1]))
        track = bytearray(_vlq(0) + b"\xff\x51\x03" + tempo_us.to_bytes(3, "big"))
        last = 0
        for tick, raw in evs:
            track += _vlq(tick - last) + raw
            last = tick
        track += _vlq(0) + b"\xff\x2f\x00"
        return head + _chunk(b"MTrk", bytes(track))

    def write(self, path: str) -> str:
        with open(path, "wb") as f:
            f.write(self.bytes())
        return path


# ─────────────────────────────── mappings ────────────────────────────────────
def _deg_to_pitch(root: int, mode: str, degree: int) -> int:
    scale = MODES[mode]
    octs, idx = divmod(degree, len(scale))
    return max(24, min(102, root + scale[idx] + 12 * octs))


def round_chord(w: MidiWriter, bar: int, matrix_hash: str, rel_type: str,
                top_values: list[float], entropy: float) -> None:
    """One chord per round, at bar position `bar` (4 beats = 1 bar)."""
    h = int(hashlib.sha256(matrix_hash.encode()).hexdigest()[:8], 16)
    root = 48 + (h % 12)                       # C3..B3
    mode = REL_TO_MODE.get(rel_type, "minor")
    tick = bar * 4 * TPQ
    dur = max(1, int((1.0 - entropy) * 3 * TPQ) + TPQ // 4)
    for i, v in enumerate(top_values[:4]):
        pitch = _deg_to_pitch(root, mode, int(v * 9.99))
        vel = 40 + int(v * 80)
        w.note(tick, 1, pitch, vel, dur)


def jev_melody(w: MidiWriter, bar: int, path: list[str], matrix_hash: str,
               entropy: float) -> None:
    """Walker path → 8 eighth-notes of melody (or fewer if the walk died early)."""
    h = int(hashlib.sha256(("mel" + matrix_hash).encode()).hexdigest()[:8], 16)
    root = 60 + (h % 12)
    mode = MODES["pentatonic"]
    step = TPQ // 2
    for i, node in enumerate(path[:8]):
        d = int(hashlib.sha256(node.encode()).hexdigest()[:6], 16) % len(mode)
        pitch = _deg_to_pitch(root, "pentatonic", d) + (6 if i % 2 else 0)
        vel = 55 + (h >> i) % 30
        w.note(bar * 4 * TPQ + i * step, 0, pitch, vel, max(1, int(step * (1 - entropy))))


def scar_hit(w: MidiWriter, bar: int, i: int) -> None:
    """Percussion on channel 10 (0x09): the failure, audible."""
    pitch = 38 if i % 2 == 0 else 42  # snare / closed hat
    w.note(bar * 4 * TPQ + TPQ // 2, 9, pitch, 90, TPQ // 8)


def duet_note(w: MidiWriter, bar: int, chan: int, value: float, entropy: float,
              seed: str) -> None:
    """Cell duet: an accepted proposal becomes one note; higher value sings higher."""
    h = int(hashlib.sha256(seed.encode()).hexdigest()[:8], 16)
    root = 55 if chan == 2 else 50
    mode = "pentatonic"
    d = h % 10
    pitch = _deg_to_pitch(root, mode, d)
    vel = 45 + int(value * 70)
    dur = max(1, int(TPQ * (1.0 - entropy) * 1.5))
    w.note(bar * 4 * TPQ + (h % 8) * (TPQ // 2), chan - 2 + 0, pitch, vel, dur)


def die_etude(w: MidiWriter, bar: int, face: int) -> None:
    """One bar riff per die face; bucket changes the interval texture."""
    from .die import bucket
    b = bucket(face)
    root = 45 + (face % 7)
    pattern = {"scar_backoff": [0, 1, 0], "entropy_jitter": [0, 3, 1, 4],
               "node_fission": [0, 2, 4, 2], "edge_rewire": [0, 4, 2, 5],
               "moth_edge": [0, 6, 4], "double_or_bust": [0, 6, 1, 5, 3]}[b]
    mode = "phrygian" if b == "scar_backoff" else "pentatonic"
    for i, p in enumerate(pattern):
        w.note(bar * 4 * TPQ + i * TPQ, 3, _deg_to_pitch(root, mode, p),
               70 + face * 2, TPQ // 2)
