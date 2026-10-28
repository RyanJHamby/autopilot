import hashlib
import hmac
import json

import pytest

from autopilot.apx import report as rp


class Resp:
    def __init__(self, status=200):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_body_normalises_unknown_model_and_outcome():
    b = json.loads(rp.build_body("o/r", 4, "claude-sonnet-5-5", 9, "weird", "2026-10-28T10:00:00Z"))
    assert b == {
        "repo": "o/r",
        "issue": 4,
        "model": "sonnet",
        "turns": 9,
        "outcome": "failure",
        "started_at": "2026-10-28T10:00:00Z",
    }


def test_signature_matches_github_style_hmac():
    body = b'{"a":1}'
    assert rp.sign("s3cret", body) == "sha256=" + hmac.new(b"s3cret", body, hashlib.sha256).hexdigest()


def test_reporter_sends_signed_apx_run_event_and_never_sends_the_secret():
    seen = {}

    def opener(req, timeout):
        seen["req"], seen["timeout"] = req, timeout
        return Resp(200)

    r = rp.make_reporter("https://cp.example/api/github/webhook", "s3cret", opener=opener)
    assert r("o/r", 4, "sonnet", 9, "success", "2026-10-28T10:00:00Z") is True
    req = seen["req"]
    h = {k.lower(): v for k, v in req.header_items()}
    assert h["x-github-event"] == "apx_run" and h["x-hub-signature-256"] == rp.sign("s3cret", req.data)
    assert "s3cret" not in req.data.decode() and "s3cret" not in " ".join(h.values())


def test_reporter_never_raises_and_requires_https():
    def boom(req, timeout):
        raise OSError("down")

    assert rp.make_reporter("https://x/y", "s", opener=boom)("o/r", 1, "sonnet", 1, "success", "t") is False
    assert (
        rp.make_reporter("https://x/y", "s", opener=lambda r, timeout: Resp(500))("o/r", 1, "sonnet", 1, "success", "t") is False
    )
    with pytest.raises(ValueError):
        rp.make_reporter("http://x/y", "s")
