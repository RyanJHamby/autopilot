"""Waivers: a repo that can't meet a rule yet says so, with an owner and an expiry.

They live in one central file, `policy/waivers.yaml` in the autopilot checkout, and are read from the base ref
(`origin/main`), not the working tree. A pull request therefore can't waive its own failure: the file it edits isn't the
one that is read. A waiver is valid for at most 30 days, and once it expires the rule fails again.

    waivers:
      - {repo: stencil, rule: license-present, owner: RyanJHamby, reason: why, granted: 2026-11-03, expires: 2026-11-20}
"""

from __future__ import annotations

import subprocess
from datetime import date
from pathlib import Path

import yaml

from autopilot.standard import load_checks

FILE = "policy/waivers.yaml"
BASE = "origin/main"
MAX_DAYS = 30
FIELDS = ("repo", "rule", "owner", "reason", "granted", "expires")


def read_base(root: Path, base: str = BASE) -> tuple[str | None, str]:
    """The waivers file as it is on the base ref, plus a note when that isn't possible. No text means no waivers.

    When the checkout has no `origin` remote at all (a bare local repo) the working-tree file is used, and the note
    says so. When there is a remote but the base ref isn't there, no waiver is applied: the safe direction is to fail."""

    def git(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)

    if "origin" not in git("remote").stdout.split():
        p = Path(root) / FILE
        return (
            (p.read_text(), f"no origin remote: waivers read from the working tree, not from {base}")
            if p.is_file()
            else (None, "")
        )
    shown = git("show", f"{base}:{FILE}")
    if shown.returncode == 0:
        return shown.stdout, ""
    if git("rev-parse", "--verify", "-q", base).returncode == 0:
        return None, ""  # the base ref exists and has no waivers file: there are none
    return None, f"{base} not found, so no waivers are applied (run `git fetch`)"


def parse(text: str | None) -> tuple[list[dict], list[str]]:
    """Valid waivers, and a note for every entry that was ignored and why."""
    if not text:
        return [], []
    try:
        data = yaml.safe_load(text) or {}
    except yaml.YAMLError as e:
        return [], [f"{FILE} does not parse, so no waivers are applied: {e}"]
    entries = data.get("waivers") if isinstance(data, dict) else None
    if not isinstance(entries, list):
        return [], [f"{FILE} has no `waivers:` list, so no waivers are applied"]
    rules = {c["id"] for c in load_checks()["checks"]}
    valid, notes = [], []
    for i, w in enumerate(entries):
        why = None
        if not isinstance(w, dict):
            why = "not a mapping"
        else:
            missing = [f for f in FIELDS if not w.get(f)]
            if missing:
                why = f"missing {', '.join(missing)}"
            elif w["rule"] not in rules:
                why = f"unknown rule {w['rule']!r}"
            elif not (isinstance(w["granted"], date) and isinstance(w["expires"], date)):
                why = "granted and expires must be dates like 2026-11-20"
            elif w["expires"] <= w["granted"]:
                why = "expires is not after granted"
            elif (w["expires"] - w["granted"]).days > MAX_DAYS:
                why = f"lasts {(w['expires'] - w['granted']).days} days; the maximum is {MAX_DAYS}"
        if why:
            notes.append(f"waiver #{i + 1} ignored: {why}")
        else:
            valid.append(w)
    return valid, notes


def apply(results: list, repo: str, waivers: list[dict], today: date) -> None:
    """Turn a failing result into `waived` when a live waiver covers it. An expired waiver leaves it failing, and says so.
    Only `fail` can be waived: an `unknown` has nothing to waive, and a `pass` needs none."""
    for r in results:
        if r.result != "fail":
            continue
        for w in waivers:
            if w["repo"] == repo and w["rule"] == r.id:
                if w["expires"] >= today:
                    r.findings = [f"waived by {w['owner']} until {w['expires']}: {w['reason']}", *r.findings]
                    r.result = "waived"
                else:
                    r.findings = [*r.findings, f"waiver expired {w['expires']} (owner {w['owner']})"]
                break
