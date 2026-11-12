"""Capability packs: what a repo must have once it can do something risky (take payments, call an LLM, run a deployment).

`packs.yaml` lists each pack's items and `capabilities.py` says which packs a repo needs, so the requirement appears the moment the
capability does, from the repo's own content, with nothing to remember. Three kinds of item:

  code        something visible in the repo's code, config or dependencies (a signature check, a health route, an error tracker)
  record      a written record that must really exist: no placeholder text, long enough to say something, and for an external fact
              (a spend cap set on a provider account, a restore that was tested) a `Verified: YYYY-MM-DD` line that goes stale
  codeowners  a human owner on the risky paths

A record is self-attested: the repo can hold a note that a cap exists, not prove it. It forces the question, dates the answer, and asks
again after 180 days. The rules that use packs say so, and `STANDARD.md` says it again.
"""

from __future__ import annotations

import datetime
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import yaml

from autopilot.standard import capabilities as cap

PACKS_FILE = Path(__file__).with_name("packs.yaml")
KINDS = ("code", "record", "codeowners")
WHEN = ("always", "hosted", "auth", "cron", "driver")
NEEDS = ("payments", "llm", "auth", "db", "deploy", "mail")
STALE_DAYS = 180
DEFAULT_MIN_LINES = 5
ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
PLACEHOLDER = re.compile(r"\b(?:TODO|TBD|FIXME)\b|<fill|<your\b|REPLACE-ME|lorem ipsum", re.I)
VERIFIED = re.compile(r"^[^\w\n]*verified[\s*_]*:[\s*_]*(\S.*?)\s*$", re.I | re.M)
CODEOWNERS_PATHS = ("CODEOWNERS", ".github/CODEOWNERS", "docs/CODEOWNERS")


@dataclass(frozen=True)
class ItemResult:
    id: str
    ok: bool
    finding: str


def load_packs(path: Path | None = None) -> dict:
    return yaml.safe_load((path or PACKS_FILE).read_text(encoding="utf-8")) or {}


def validate(data: dict) -> list[str]:
    """Every way the packs file is malformed. An item that could never pass or never fail is a mistake, not a configuration."""
    problems: list[str] = []
    packs = data.get("packs", {})
    if not isinstance(packs, dict):
        return ["packs must be a mapping of pack name to its definition"]
    for name, pack in packs.items():
        where = f"pack {name}"
        if not isinstance(pack, dict):
            problems.append(f"{where}: must be a mapping")
            continue
        if pack.get("needs") not in NEEDS:
            problems.append(f"{where}: needs must be one of {', '.join(NEEDS)}")
        items = pack.get("items")
        if not isinstance(items, list) or not items:
            problems.append(f"{where}: items must be a non-empty list")
            continue
        seen: set[str] = set()
        for i, item in enumerate(items):
            problems += _validate_item(f"{where} item {i}", item, seen)
    return problems


def _validate_item(where: str, item: object, seen: set[str]) -> list[str]:
    if not isinstance(item, dict):
        return [f"{where}: must be a mapping"]
    out: list[str] = []
    ident = item.get("id")
    if not isinstance(ident, str) or not ID.match(ident):
        out.append(f"{where}: id must be lowercase words joined by hyphens")
    elif ident in seen:
        out.append(f"{where}: duplicate id {ident}")
    else:
        seen.add(ident)
    for key in ("title", "fix"):
        if not item.get(key):
            out.append(f"{where}: needs `{key}`")
    kind = item.get("kind")
    if kind not in KINDS:
        out.append(f"{where}: kind must be one of {', '.join(KINDS)}")
    if item.get("when", "always") not in WHEN:
        out.append(f"{where}: when must be one of {', '.join(WHEN)}")
    patterns = list(item.get("match") or []) + ([item["cover"]] if kind == "codeowners" and item.get("cover") else [])
    for pat in patterns:
        try:
            re.compile(pat)
        except (re.error, TypeError):
            out.append(f"{where}: {pat!r} is not a valid regex")
    if kind == "code" and not (item.get("match") or item.get("paths") or item.get("deps")):
        out.append(f"{where}: a code item needs match, paths or deps, or it can never pass")
    if kind == "record" and not (isinstance(item.get("path"), list) and item["path"]):
        out.append(f"{where}: a record item needs a `path` list")
    if kind == "codeowners" and not item.get("cover"):
        out.append(f"{where}: a codeowners item needs `cover`")
    return out


# --- evaluation ---------------------------------------------------------------------------------------------------------


def _glob(pattern: str) -> re.Pattern:
    out, i = "", 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out, i = out + "(?:.*/)?", i + 3
        elif pattern.startswith("**", i):
            out, i = out + ".*", i + 2
        elif pattern[i] == "*":
            out, i = out + "[^/]*", i + 1
        elif pattern[i] == "?":
            out, i = out + "[^/]", i + 1
        else:
            out, i = out + re.escape(pattern[i]), i + 1
    return re.compile(out + r"\Z")


def _check_code(scan: cap.Scan, item: dict, today: datetime.date) -> tuple[bool, str]:
    regexes = [re.compile(p) for p in item.get("match") or []]
    if regexes:
        texts = (scan.code(p) for p in scan.code_paths if p.endswith(tuple(cap.CODE_EXT)))
        if any(rx.search(t) for t in texts if t for rx in regexes):
            return True, ""
        if item.get("include_sql"):
            for rel in scan.page_paths:
                raw = scan.raw(rel) if rel.endswith(".sql") else None
                if raw and any(rx.search(re.sub(r"--[^\n]*", "", raw)) for rx in regexes):
                    return True, ""
    globs = [_glob(g) for g in item.get("paths") or []]
    if globs and any(g.match(p) for p in scan.page_paths for g in globs):
        return True, ""
    deps = item.get("deps") or []
    if deps and any(cap.matches_any(name, deps) for name, _ in scan.deps):
        return True, ""
    return False, f"{item['title']}: not found in this repo"


def _check_record(scan: cap.Scan, item: dict, today: datetime.date) -> tuple[bool, str]:
    candidates = item["path"]
    found = next((p for p in candidates if (scan.root / p).is_file()), None)
    if found is None:
        return False, f"no {candidates[0]}"
    text = scan.raw(found) or ""
    if PLACEHOLDER.search(text):
        return False, f"{found} still has placeholder text (TODO, TBD, FIXME or a <fill> marker)"
    need = int(item.get("min_lines", DEFAULT_MIN_LINES))
    content = [ln for ln in text.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
    if len(content) < need:
        return False, f"{found} is too short to be a record ({len(content)} lines of content, needs {need})"
    if item.get("verified"):
        return _check_verified(found, text, today)
    return True, ""


def _check_verified(found: str, text: str, today: datetime.date) -> tuple[bool, str]:
    m = VERIFIED.search(text)
    if not m:
        return False, f"{found} has no `Verified: YYYY-MM-DD` line saying when this was last checked"
    raw = m.group(1).strip("*_ ")
    try:
        day = datetime.date.fromisoformat(raw) if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw) else None
    except ValueError:
        day = None
    if day is None:
        return False, f"{found} has a Verified line that is not a date written YYYY-MM-DD ({raw!r})"
    if day > today:
        return False, f"{found} says it was verified in the future ({day})"
    age = (today - day).days
    if age > STALE_DAYS:
        return False, f"{found} is stale: last verified {day}, {age} days ago (the limit is {STALE_DAYS})"
    return True, ""


def _check_codeowners(scan: cap.Scan, item: dict, today: datetime.date) -> tuple[bool, str]:
    rx = re.compile(item["cover"], re.I)
    for rel in CODEOWNERS_PATHS:
        text = scan.raw(rel)
        if text is None:
            continue
        for line in text.splitlines():
            entry = line.strip()
            if entry and not entry.startswith("#") and rx.search(entry.split()[0]):
                return True, ""
    return False, f"CODEOWNERS has no entry for paths matching /{item['cover']}/"


_CHECKS: dict[str, Callable[[cap.Scan, dict, datetime.date], tuple[bool, str]]] = {
    "code": _check_code,
    "record": _check_record,
    "codeowners": _check_codeowners,
}


def evaluate(scan: cap.Scan, pack: dict, today: datetime.date | None = None) -> list[ItemResult]:
    """One result per item that applies to this repo. An item whose `when` is not met (hosted, auth, cron, driver) is left out, not passed."""
    today = today or datetime.date.today()
    caps = scan.caps
    out = []
    for item in pack["items"]:
        when = item.get("when", "always")
        skip = (
            (when == "hosted" and not cap.hosted(caps))
            or (when == "auth" and "auth" not in caps)
            or (when == "cron" and not cap.has_cron(scan))
            or (when == "driver" and not cap.has_db_driver(scan))
        )
        if skip:
            continue
        ok, why = _CHECKS[item["kind"]](scan, item, today)
        out.append(ItemResult(item["id"], ok, "" if ok else f"{why}. Fix: {item['fix']}"))
    return out


def check_pack(scan: cap.Scan, name: str, cfg: dict | None = None, today: datetime.date | None = None) -> tuple[str, list[str]]:
    """(pass | fail | skip, findings) for one pack against one repo. Used by the standard's pack rules."""
    pack = (cfg or load_packs())["packs"][name]
    need = pack["needs"]
    caps = scan.caps
    if need not in caps:
        return "skip", [f"no {need} capability detected"]
    missing = [r for r in evaluate(scan, pack, today) if not r.ok]
    if not missing:
        return "pass", []
    ev = caps[need][0]
    where = ev.detail if ev.path in ev.detail else f"{ev.path}: {ev.detail}"
    return "fail", [f"{need} detected: {where}"] + [f"{r.id}: {r.finding}" for r in missing]
