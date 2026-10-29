"""Redact secrets from anything apx publishes (check-run summaries, and so public PR pages).

Two layers, because neither alone is enough:
  1. exact values: every secret apx holds in memory (installation tokens, the Claude token) is registered and replaced
     wherever it appears, in any form of surrounding text;
  2. shapes: common credential formats are replaced even if apx never held them (a PR's test could print a key it found).
It never raises and is idempotent. This is defence in depth for output; the real protection is that the CI account cannot
read the secrets at all (backlog S1).
"""

from __future__ import annotations

import re

MARK = "[REDACTED]"
MIN_SECRET_LEN = 8  # shorter "secrets" would shred ordinary text
_registered: set[str] = set()

_SHAPES = [
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?(?:-----END [A-Z ]*PRIVATE KEY-----|\Z)", re.S),
    re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"),
    re.compile(r"\bxox[abprs]-[A-Za-z0-9\-]{10,}"),
    re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}"),  # JWT
    re.compile(r"(?i)\b(authorization:\s*(?:basic|bearer)\s+)[A-Za-z0-9+/=._\-]{12,}"),
    re.compile(r"(?i)\b((?:api[_-]?key|secret|token|passwd|password)\b[\"']?\s*[:=]\s*[\"']?)[A-Za-z0-9/+_\-=.]{20,}"),
]
_FENCE = re.compile(r"```.*?```", re.S)


def register(value: str | None) -> None:
    """Remember an exact secret value so it is scrubbed everywhere it could appear."""
    if value and len(value) >= MIN_SECRET_LEN:
        _registered.add(value)


def forget_all() -> None:  # tests only
    _registered.clear()


def redact(text: str) -> str:
    try:
        out = text
        for v in sorted(_registered, key=len, reverse=True):  # longest first so overlapping values cannot leave a tail
            out = out.replace(v, MARK)
        for rx in _SHAPES:
            if rx.groups:
                out = rx.sub(lambda m: m.group(1) + MARK, out)  # keep the label ("token=") and drop only the value
            else:
                out = rx.sub(MARK, out)
        return out
    except Exception:  # noqa: BLE001 - never let redaction break a check; withhold instead of risking a leak
        return "(output withheld: redaction failed)"


def strip_output_blocks(markdown: str) -> str:
    """Public repos get step names and durations only: drop fenced raw output (the tail of a failing command)."""
    return _FENCE.sub("(raw output withheld on public repositories; see the apx log on the host)", markdown)
