"""tests/test_music.py — SMF writer correctness + deterministic sonification."""

import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from engine.music import (MidiWriter, TPQ, duet_note, jev_melody,  # noqa: E402
                          round_chord, scar_hit, die_etude, _vlq)
from engine.die import d20  # noqa: E402


class TestVlq(unittest.TestCase):
    def test_vlq(self):
        self.assertEqual(_vlq(0), b"\x00")
        self.assertEqual(_vlq(127), b"\x7f")
        self.assertEqual(_vlq(128), b"\x81\x00")
        self.assertEqual(_vlq(480), b"\x83\x60")


class TestSmf(unittest.TestCase):
    def test_header_bytes(self):
        w = MidiWriter()
        w.note(0, 0, 60, 90, 240)
        b = w.bytes()
        self.assertEqual(b[:4], b"MThd")
        self.assertEqual(b[4:8], b"\x00\x00\x00\x06")     # header length 6
        self.assertEqual(b[8:14], b"\x00\x00\x00\x01" + TPQ.to_bytes(2, "big"))
        self.assertEqual(b[14:18], b"MTrk")               # one track

    def test_end_of_track_present(self):
        w = MidiWriter()
        w.note(0, 0, 60, 90, 240)
        self.assertTrue(w.bytes().endswith(b"\x00\xff\x2f\x00"))

    def test_note_events_encoded(self):
        w = MidiWriter(tempo_bpm=110)
        w.note(0, 1, 64, 100, 120)
        b = w.bytes()
        track = b[22:]                                   # after MThd(14) + MTrk(8)
        self.assertEqual(track[:7],
                         b"\x00\xff\x51\x03" + (545454).to_bytes(3, "big"))  # tempo
        self.assertIn(b"\x91\x40\x64", track)            # note-on chan1 pitch64 vel100

    def test_deterministic_bytes(self):
        w1, w2 = MidiWriter(), MidiWriter()
        for w in (w1, w2):
            round_chord(w, 0, "hashx", "resonates", [0.7, 0.4, 0.2], 0.3)
            jev_melody(w, 1, ["a", "b", "c"], "hashx", 0.3)
            scar_hit(w, 1, 0)
            duet_note(w, 2, 2, 0.8, 0.2, "seed")
            die_etude(w, 3, d20("etude-seed"))
        self.assertEqual(w1.bytes(), w2.bytes())

    def test_roundtrip_writes_file(self):
        p = os.path.join(tempfile.mkdtemp(), "x.mid")
        w = MidiWriter()
        w.note(0, 9, 38, 90, 60)
        w.write(p)
        raw = open(p, "rb").read()
        self.assertEqual(raw[:4], b"MThd")
        self.assertGreater(len(raw), 30)

    def test_negative_guard(self):
        """Pitch/velocity clamps keep bytes in MIDI's 7-bit domain."""
        w = MidiWriter()
        round_chord(w, 0, "h", "contradicts", [1.0, 1.0, 1.0], 1.0)  # extremes
        for tick, raw in w.events:
            for byte in raw[1:]:
                self.assertLessEqual(byte, 0x7F)


if __name__ == "__main__":
    unittest.main()
