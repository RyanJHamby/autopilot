"""The Claude Code version floor (autonomy hardening plan, work item W0-19): one policy value, one shared check.

`policy/claude.yaml` holds the lowest version any machine or runner may use. `ap doctor` (this machine), `apx doctor` (the
executor and its agent account) and `ap launch-repo` all call into this module, so they cannot disagree about the number.

Everything fails closed: a `claude` that is missing, times out or exits non-zero; output that is not exactly `N.N.N` (optionally
followed by ` (Claude Code)`), so a pre-release or an unfamiliar format refuses; a policy file that is missing, unreadable or
malformed; a floor that is not a plain version. Versions compare numerically part by part (2.1.1000 is above 2.1.302). No argument
or variable lowers the floor: the only way to change it is to edit the policy file.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
FLOOR_FILE = ROOT / "policy" / "claude.yaml"
_PLAIN = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+", re.ASCII)
_OUTPUT = re.compile(r"\s*([0-9]+)\.([0-9]+)\.([0-9]+)(?:\s+\(Claude Code\))?\s*", re.ASCII)


class FloorError(Exception):
    """Something stopped the check from giving a trustworthy answer; callers treat it as a failed check."""


def _fmt(v: tuple[int, ...]) -> str:
    return ".".join(str(x) for x in v)


def load_floor(path: Path | str | None = None) -> tuple[int, int, int]:
    p = Path(path) if path is not None else FLOOR_FILE
    try:
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as e:
        raise FloorError(f"cannot read the version floor from {p.name} ({type(e).__name__})") from None
    value = data.get("min_version") if isinstance(data, dict) else None
    if not isinstance(value, str) or not _PLAIN.fullmatch(value):
        raise FloorError(f"{p.name} must hold min_version as a plain N.N.N version string")
    a, b, c = (int(x) for x in value.split("."))
    return (a, b, c)


def parse_version(text: str) -> tuple[int, int, int] | None:
    m = _OUTPUT.fullmatch(text or "")
    return (int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None


def verdict(text: str, floor: tuple[int, ...]) -> tuple[bool, str]:
    v = parse_version(text)
    if v is None:
        return False, f"cannot read a version from claude's output (the floor is {_fmt(floor)})"
    ok = v >= tuple(floor)
    return ok, f"claude {_fmt(v)} {'meets' if ok else 'is below'} the floor {_fmt(floor)}"


def probe(binary: str = "claude", run=subprocess.run) -> str:
    try:
        r = run([binary, "--version"], capture_output=True, text=True, timeout=30)
    except FileNotFoundError:
        raise FloorError(f"{binary} is not installed or not on PATH") from None
    except (OSError, subprocess.SubprocessError) as e:
        raise FloorError(f"cannot run {binary} --version ({type(e).__name__})") from None
    if r.returncode != 0:
        raise FloorError(f"{binary} --version failed (exit {r.returncode})")
    return r.stdout


def _default_probe(binary: str) -> str:
    return probe(binary)  # looked up at call time, so tests can replace it


def machine_check(binary: str = "claude", probe=None, floor_path: Path | str | None = None) -> tuple[bool, str]:
    try:
        floor = load_floor(floor_path)
    except FloorError as e:
        return False, f"version floor unreadable: {e}"
    try:
        out = (probe or _default_probe)(binary)
    except FloorError as e:
        return False, str(e)
    except Exception as e:  # noqa: BLE001 - an unexpected failure must read as a failed check, never as a pass
        return False, f"the claude version check failed unexpectedly ({type(e).__name__})"
    return verdict(out, floor)


def check_result(rc: int, out: str, floor_path: Path | str | None = None) -> tuple[bool, str]:
    """For a caller that already ran `claude --version` itself (the launcher, the agent account)."""
    try:
        floor = load_floor(floor_path)
    except FloorError as e:
        return False, f"version floor unreadable: {e}"
    if rc != 0:
        return False, f"claude --version failed (exit {rc})"
    return verdict(out, floor)
