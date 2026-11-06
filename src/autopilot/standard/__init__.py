"""The project standard: what every repo should have, and how each rule is backed.

`checks.yaml` is the single list. Every rule says how it is backed, so a judgment call is never passed off as a control:

  enforced  CI or a ruleset blocks it. Needs `enforced_by`, naming the mechanism.
  audited   `ap standard check` reports it when someone runs it. Nothing blocks a merge.
  advisory  Judgment, not enforced anywhere. Must say `evidence: judgment`, and can only warn.

A rule's `level` is what a failing result does to the run: `fail` exits non-zero, `warn` prints. New rules start at `warn`
until the portfolio is clean, so adding one never breaks a repo overnight.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

LEVELS = ("fail", "warn")
LABELS = ("enforced", "audited", "advisory")
APPLIES_TO = ("all", "public", "private")
REQUIRED = ("id", "title", "level", "label", "why", "fix")
ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
CHECKS_FILE = Path(__file__).with_name("checks.yaml")


def load_checks(path: Path | None = None) -> dict:
    return yaml.safe_load((path or CHECKS_FILE).read_text(encoding="utf-8"))


def validate(data: dict) -> list[str]:
    """Return every way the checks file is malformed. An empty list means it is usable."""
    problems: list[str] = []
    version = data.get("standard_version")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        problems.append("standard_version must be an integer, 1 or higher")
    checks = data.get("checks")
    if not isinstance(checks, list) or not checks:
        return problems + ["checks must be a non-empty list"]
    seen: set[str] = set()
    for index, check in enumerate(checks):
        name = check.get("id") if isinstance(check, dict) else None
        label = name or f"checks[{index}]"
        if not isinstance(check, dict):
            problems.append(f"{label}: must be a mapping")
            continue
        for key in REQUIRED:
            if not check.get(key):
                problems.append(f"{label}: needs `{key}`")
        if name:
            if not ID.match(str(name)):
                problems.append(f"{label}: id must be lowercase words joined by hyphens")
            if name in seen:
                problems.append(f"{label}: duplicate id")
            seen.add(name)
        if check.get("level") and check["level"] not in LEVELS:
            problems.append(f"{label}: level must be one of {', '.join(LEVELS)}")
        if check.get("label") and check["label"] not in LABELS:
            problems.append(f"{label}: label must be one of {', '.join(LABELS)}")
        if check.get("applies_to", "all") not in APPLIES_TO:
            problems.append(f"{label}: applies_to must be one of {', '.join(APPLIES_TO)}")
        if check.get("label") == "enforced" and not check.get("enforced_by"):
            problems.append(f"{label}: an enforced rule must say what enforces it (`enforced_by`)")
        if check.get("label") == "advisory":
            if check.get("level") == "fail":
                problems.append(f"{label}: an advisory rule is judgment, so it can only warn")
            if check.get("evidence") != "judgment":
                problems.append(f"{label}: an advisory rule must say `evidence: judgment`")
    return problems
