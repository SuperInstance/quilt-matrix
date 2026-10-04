"""tests/test_moth_contract.py — the moth pipeline's request shaping, offline.

The deep probe (docs/MOTH-PROBE.md) bought the contract with 97 receipted
requests; these tests freeze it so a future refactor cannot silently
regress the exact bodies/routes that make the moth sing. NO network in CI:
transports are stubbed, only the shapes are proven.
"""

import json
import os
import sys
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

from engine import moth  # noqa: E402


class TestMothContractShapes(unittest.TestCase):
    def test_asset_upload_body_and_flow(self):
        """POST /assets body carries filename+content_type+size_bytes (the
        422s named all three), PUT is raw with exact content type, complete
        is posted."""
        calls = []

        def fake_call(method, path, body=None, timeout_s=20.0):
            calls.append((method, path, body))
            if path == "/assets":
                return {"asset_id": "aid-123",
                        "upload": {"url": "https://s3/presigned-put"}}
            return {}  # complete

        def fake_raw(method, url, data=None, headers=None, timeout_s=60.0):
            calls.append((method, url, headers))
            return b""

        with mock.patch.object(moth, "_call", side_effect=fake_call), \
             mock.patch.object(moth, "_raw", side_effect=fake_raw):
            aid = moth.asset_upload(b"MThdxxx", "in.mid", "audio/midi")
        self.assertEqual(aid, "aid-123")
        self.assertEqual(calls[0], ("POST", "/assets",
                                    {"filename": "in.mid", "content_type": "audio/midi",
                                     "size_bytes": 7}))
        method, url, headers = calls[1]
        self.assertEqual((method, url), ("PUT", "https://s3/presigned-put"))
        self.assertEqual(headers["Content-Type"], "audio/midi")
        self.assertNotIn("Authorization", headers)  # presigned law: no auth headers
        self.assertEqual(calls[2][1], "/assets/aid-123/complete")

    def test_qrc_midi_submit_shape(self):
        """THE contract: {"input_files": {"midi": <aid>}, "params": {"bpm"}} —
        anything else was 415/422."""
        captured = {}

        def fake_call(method, path, body=None, timeout_s=20.0):
            captured[(method, path)] = body
            if path == "/assets":
                return {"asset_id": "A", "upload": {"url": "https://s3/u"}}
            if path == "/engines/qrc-midi-v1/process":
                return {"job_id": "J"}
            if path == "/jobs/J/status":
                return {"status": "completed"}
            if path == "/jobs/J":
                return {"outputs": [
                    {"slot": "result", "output_asset_id": "R"},
                    {"slot": "model", "output_asset_id": "M"}]}
            if path == "/assets/R/download":
                return {"download_url": "https://s3/r"}
            if path == "/assets/M/download":
                return {"download_url": "https://s3/m"}
            return {}

        fake_mid = b"MThd\x00\x01" + b"x" * 20
        with mock.patch.object(moth, "_call", side_effect=fake_call), \
             mock.patch.object(moth, "_raw",
                               side_effect=lambda m, u, d=None, h=None, t=60.0:
                               fake_mid if u.endswith("/r") else
                               json.dumps({"v": 1}).encode()):
            data, model, info = moth.qrc_midi(fake_mid, bpm=112)
        self.assertTrue(info.get("ok"), info)
        self.assertEqual(data[:4], b"MThd")
        self.assertEqual(model, {"v": 1})
        body = captured[("POST", "/engines/qrc-midi-v1/process")]
        self.assertEqual(body, {"input_files": {"midi": "A"},
                                "params": {"bpm": 112}})

    def test_job_wait_fails_on_failed(self):
        with mock.patch.object(moth, "_call",
                               side_effect=lambda m, p, b=None, **kw:
                               {"status": "failed",
                                "error": {"message": "need at least 2 distinct notes"}}):
            with self.assertRaisesRegex(RuntimeError, "distinct notes"):
                moth.job_wait("J", timeout_s=2, poll_s=0.01)

    def test_legacy_shim_requires_bytes(self):
        self.assertIsNone(moth.midi_via_moth({"mode": "emu"}))


if __name__ == "__main__":
    unittest.main(verbosity=2)
