"""Gates: checklists a bet clears before real users arrive (`beta`) and before the first payment (`charge`).

A gate is data (`gates.yaml`). Each item is one of four kinds, and `ap gate show` says which are verified and which are not:

  repo-standard  the bet's repo has no fail-level gap when held to the current standard (checked against the code)
  bet-artifact   another bet has delivered the named artifacts, e.g. the llc bet's `ein` (as good as the ref recorded in pawl)
  bet-field      a field of the bet's own bet.toml is filled in (checked against the file)
  step           a manual task, seeded into pawl as a draft step; done when someone marks it done (self-attested)

`ap gate seed` writes the steps into the control repo through pawl's own CLI, with explicit ids so running it twice adds nothing. This is a
checklist, not legal or tax advice: the legal and tax steps say to confirm with a professional.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

GATES_FILE = Path(__file__).with_name("gates.yaml")
KINDS = ("repo-standard", "bet-artifact", "bet-field", "step")
# Fields a bet.toml can carry (from pawl's product template), so a typo in gates.yaml is caught here and not by an empty check later.
BET_FIELDS = (
    "problem", "buyer", "buying_path", "channel", "offer", "price_monthly", "churn_monthly", "channel_sales_per_month", "forecast",
    "premortem", "conflict_check", "moat", "appetite_units", "kill_state", "kill_date", "money_gate", "repo",
)
# pawl's own limits (steps.py): a step it would reject is only found out by `seed --apply` on the real ledger, so they are checked here.
PAWL_ID = re.compile(r"[a-z0-9][a-z0-9-]{0,39}")
MAX_TITLE, MAX_NOTE = 200, 300
SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
ITEM_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def load_gates(path: Path | None = None) -> dict:
    return yaml.safe_load((path or GATES_FILE).read_text(encoding="utf-8")) or {}


def step_id(gate: str, item_id: str) -> str:
    """The pawl step id for a gate item. Prefixed with the gate so two gates can never collide, and always passed explicitly,
    because ids derived from titles drift and are suffixed -2, -3 on a repeat."""
    return f"g-{gate}-{item_id}"


def validate(data: dict) -> list[str]:
    problems: list[str] = []
    gates = data.get("gates")
    if not isinstance(gates, dict) or not gates:
        return ["gates must be a non-empty mapping of gate name to its definition"]
    for name, gate in gates.items():
        where = f"gate {name}"
        if not SLUG.match(str(name)):
            problems.append(f"{where}: gate name must be lowercase words joined by hyphens")
        if not isinstance(gate, dict):
            problems.append(f"{where}: must be a mapping")
            continue
        if not gate.get("title"):
            problems.append(f"{where}: needs a title")
        items = gate.get("items")
        if not isinstance(items, list) or not items:
            problems.append(f"{where}: items must be a non-empty list")
            continue
        seen: set[str] = set()
        for i, item in enumerate(items):
            problems += _validate_item(f"{where} item {i}", name, item, seen)
    return problems


def _validate_item(where: str, gate: str, item: object, seen: set[str]) -> list[str]:
    if not isinstance(item, dict):
        return [f"{where}: must be a mapping"]
    out: list[str] = []
    ident = item.get("id")
    if not isinstance(ident, str) or not ITEM_ID.match(ident):
        out.append(f"{where}: id must be lowercase words joined by hyphens")
    elif ident in seen:
        out.append(f"{where}: duplicate id {ident}")
    else:
        seen.add(ident)
    kind = item.get("kind")
    if kind not in KINDS:
        out.append(f"{where}: kind must be one of {', '.join(KINDS)}")
    if not item.get("title"):
        out.append(f"{where}: needs a title")
    tips = item.get("tips")
    if tips is not None and not (isinstance(tips, list) and all(isinstance(t, int) and not isinstance(t, bool) for t in tips)):
        out.append(f"{where}: tips must be a list of integers")
    if kind == "step":
        out += _validate_step(where, gate, ident, item)
    elif kind == "bet-artifact":
        if not item.get("bet"):
            out.append(f"{where}: needs `bet`")
        elif not SLUG.match(str(item["bet"])):
            out.append(f"{where}: bet must be a lowercase slug")
        arts = item.get("artifacts")
        if not (isinstance(arts, list) and arts and all(isinstance(a, str) and a for a in arts)):
            out.append(f"{where}: needs `artifacts`, a non-empty list of artifact ids")
    elif kind == "bet-field":
        if not item.get("field"):
            out.append(f"{where}: needs `field`")
        elif item["field"] not in BET_FIELDS:
            out.append(f"{where}: unknown bet field {item['field']!r}; known: {', '.join(BET_FIELDS)}")
    return out


def _validate_step(where: str, gate: str, ident: object, item: dict) -> list[str]:
    out: list[str] = []
    title, note = item.get("title") or "", item.get("note")
    if len(" ".join(title.split())) > MAX_TITLE:
        out.append(f"{where}: title is at most {MAX_TITLE} characters (pawl's limit)")
    if not note:
        out.append(f"{where}: a step needs a note (cite the tip it comes from)")
    elif len(" ".join(str(note).split())) > MAX_NOTE:
        out.append(f"{where}: note is at most {MAX_NOTE} characters (pawl's limit)")
    if isinstance(ident, str) and not PAWL_ID.fullmatch(step_id(gate, ident)):
        out.append(f"{where}: step id {step_id(gate, ident)!r} is not a valid pawl id (lowercase, numbers, dashes, at most 40 characters)")
    return out
