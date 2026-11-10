"""Evaluate a gate for a bet. Read-only: it reads pawl through `pawl steps --json` and the bet's own bet.toml, and never writes anywhere.

Every item ends in one of four states, and the verdict is "ready" only when all are `done`:

  done        satisfied
  todo        not satisfied yet (the detail says what is missing)
  not-seeded  a step item that is not in pawl yet (`ap gate seed` adds it)
  unknown     could not be answered (no clone, no pawl, a bet that does not exist): never counted as done

Each item also says HOW it is known, because a tick is not proof: a repo check is made against the code, a bet field against bet.toml, a
cross-bet artifact is as good as the ref recorded in pawl, and a manual step is self-attested.
"""

from __future__ import annotations

import json
import os
import subprocess
import tomllib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from autopilot.gates import step_id

HOW = {
    "repo-standard": "checked against the code",
    "bet-artifact": "recorded in pawl (the delivery ref is self-attested)",
    "bet-field": "checked against bet.toml",
    "step": "self-attested",
}
LABEL = {"done": "done", "todo": "not done", "not-seeded": "not seeded", "unknown": "unknown"}
RepoCheck = Callable[[dict], "tuple[Path | None, list[str], list[str]]"]


class PawlError(Exception):
    """pawl could not answer: not installed, not a control repo, or a bet that does not exist."""


@dataclass
class Item:
    id: str
    kind: str
    title: str
    state: str
    detail: str
    how: str


def resolve_control(flag: str | None) -> Path:
    """The control repo: --control, else $PAWL_ROOT, else ~/dev/control."""
    return Path(flag or os.environ.get("PAWL_ROOT") or "~/dev/control").expanduser()


def pawl_steps(control: Path, bet: str, run=subprocess.run) -> dict:
    """`pawl steps BET --json`'s data. Raises PawlError with pawl's own message when it cannot answer."""
    try:
        r = run(["pawl", "--root", str(control), "steps", bet, "--json"], capture_output=True, text=True)
    except FileNotFoundError as e:
        raise PawlError("pawl is not installed or not on PATH (uv tool install --editable ~/dev/pawl)") from e
    try:
        doc = json.loads(r.stdout)
    except ValueError as e:
        raise PawlError(f"pawl gave no JSON: {(r.stderr or r.stdout).strip()[:160] or 'no output'}") from e
    if not doc.get("ok"):
        raise PawlError((doc.get("error") or {}).get("message") or "pawl failed")
    return doc["data"]


def thesis(control: Path, bet: str) -> dict:
    """The bet's own bet.toml fields ({} if the file is missing or unreadable)."""
    try:
        return tomllib.loads((control / "bets" / bet / "bet.toml").read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return {}


def _filled(value: object) -> bool:
    return bool(value) and not (isinstance(value, (int, float)) and not isinstance(value, bool) and value <= 0)


def evaluate(gate_name: str, gate: dict, bet: str, control: Path, repo_check: RepoCheck, run=subprocess.run) -> list[Item]:
    cache: dict[str, dict | PawlError] = {}

    def steps_of(slug: str) -> dict:
        if slug not in cache:
            try:
                cache[slug] = pawl_steps(control, slug, run)
            except PawlError as e:
                cache[slug] = e
        if isinstance(cache[slug], PawlError):
            raise cache[slug]  # type: ignore[misc]
        return cache[slug]  # type: ignore[return-value]

    fields = thesis(control, bet)
    out = []
    for item in gate["items"]:
        kind = item["kind"]
        try:
            state, detail = _one(gate_name, item, kind, bet, fields, steps_of, repo_check)
        except PawlError as e:
            state, detail = "unknown", str(e)
        out.append(Item(item["id"], kind, item["title"], state, detail, HOW[kind]))
    return out


def _one(gate_name: str, item: dict, kind: str, bet: str, fields: dict, steps_of, repo_check: RepoCheck) -> tuple[str, str]:
    if kind == "step":
        sid = step_id(gate_name, item["id"])
        found = next((s for s in steps_of(bet)["steps"] if s["id"] == sid), None)
        if found is None:
            return "not-seeded", f"not in pawl yet: `ap gate seed {bet} {gate_name} --apply` adds it"
        if found["state"] == "done":
            return "done", f"marked done{' on ' + found['done_on'] if found.get('done_on') else ''}"
        if found["state"] == "dropped":
            return "done", "dropped (not owed)"
        return "todo", f"step {sid} is still to do"
    if kind == "bet-field":
        value = fields.get(item["field"])
        return ("done", f"{item['field']} is set") if _filled(value) else ("todo", f"{item['field']} is empty in bets/{bet}/bet.toml")
    if kind == "bet-artifact":
        try:
            have = {a["id"]: a for a in steps_of(item["bet"])["artifacts"]}
        except PawlError as e:
            if "No bet named" in str(e):
                raise PawlError(f"bet {item['bet']!r} was not found in the control repo, so this cannot be checked") from e
            raise
        missing = [a for a in item["artifacts"] if a not in have]
        undelivered = [a for a in item["artifacts"] if a in have and have[a]["state"] != "delivered"]
        if missing or undelivered:
            parts = [f"no artifact {a!r} on {item['bet']}" for a in missing] + [f"{a} not delivered" for a in undelivered]
            return "todo", "; ".join(parts)
        return "done", f"{item['bet']}: {', '.join(item['artifacts'])} delivered"
    # repo-standard
    path, gaps, notes = repo_check(fields)
    if path is None:
        repo = (fields.get("repo") or "").strip()
        why = f"no clone of {repo} found (use --path or --root)" if repo else "the bet names no repo, so there is no clone to look at"
        return "unknown", why
    if gaps:
        shown = "; ".join(gaps[:6]) + (f"; and {len(gaps) - 6} more" if len(gaps) > 6 else "")
        return "todo", f"{len(gaps)} fail-level gap(s) held to the current standard: {shown}"
    return "done", f"no fail-level gaps in {path}"


def ready(items) -> bool:
    items = list(items)
    return bool(items) and all(i.state == "done" for i in items)


def render(bet: str, gate_name: str, gate: dict, items: list[Item]) -> str:
    width = max((len(i.id) for i in items), default=0)
    lines = [f"== {gate_name}: {gate['title']}  (bet {bet})"]
    for i in items:
        lines.append(f"  {LABEL[i.state]:10} {i.id:{width}}  {i.title}")
        lines.append(f"  {'':10} {'':{width}}  -> {i.detail}  [{i.how}]")
    done = sum(i.state == "done" for i in items)
    lines.append(f"{done} of {len(items)} done. " + ("Ready." if ready(items) else "Not ready."))
    if any(i.state == "not-seeded" for i in items):
        lines.append(f"Seed the missing steps with: ap gate seed {bet} {gate_name} --apply")
    return "\n".join(lines)
