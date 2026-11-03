"""Batch manifests: order, dependencies and file-scope overlap for a queue of specs.

A manifest is `.autopilot/batches/<id>.yaml` on the DEFAULT branch, so the owner approves a batch by merging one PR:

    id: b1
    items:
      - issue: 101
        scope: ["src/a/**"]
      - issue: 102
        depends_on: [101]

It only ORDERS and HOLDS work the gate already allows. It never makes an issue eligible (that is still the owner's
`agent-ready` label), never raises a cap, and an unreadable or invalid manifest is ignored whole (fail closed: its issues
fall back to plain gate order, never to "run everything").
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import yaml

BATCH_DIR = ".autopilot/batches"
_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")


@dataclass(frozen=True)
class Item:
    issue: int
    depends_on: tuple[int, ...] = ()
    scope: tuple[str, ...] = ()


@dataclass(frozen=True)
class Batch:
    id: str
    items: tuple[Item, ...] = field(default_factory=tuple)


class BatchError(ValueError):
    pass


def _ints(v, what: str) -> tuple[int, ...]:
    if v is None:
        return ()
    if not isinstance(v, list) or not all(isinstance(x, int) and not isinstance(x, bool) and x > 0 for x in v):
        raise BatchError(f"{what} must be a list of issue numbers")
    return tuple(v)


def parse(text: str) -> Batch:
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as e:
        raise BatchError(f"not yaml: {e}") from e
    if not isinstance(raw, dict) or not _ID.match(str(raw.get("id", ""))):
        raise BatchError("batch needs an id like 'b1'")
    rows = raw.get("items")
    if not isinstance(rows, list) or not rows:
        raise BatchError("batch needs a non-empty items list")
    items, seen = [], set()
    for r in rows:
        if not isinstance(r, dict) or not isinstance(r.get("issue"), int) or isinstance(r.get("issue"), bool):
            raise BatchError("each item needs an integer issue")
        n = r["issue"]
        if n in seen:
            raise BatchError(f"issue {n} listed twice")
        seen.add(n)
        scope = r.get("scope") or []
        if not isinstance(scope, list) or not all(isinstance(s, str) and s for s in scope):
            raise BatchError(f"scope for {n} must be a list of globs")
        items.append(Item(n, _ints(r.get("depends_on"), f"depends_on for {n}"), tuple(scope)))
    for it in items:
        if it.issue in it.depends_on:
            raise BatchError(f"issue {it.issue} depends on itself")
    # cycle check over dependencies that point inside the batch
    deps = {it.issue: [d for d in it.depends_on if d in seen] for it in items}
    state: dict[int, int] = {}

    def visit(n: int) -> None:
        if state.get(n) == 1:
            raise BatchError("dependency cycle")
        if state.get(n) == 2:
            return
        state[n] = 1
        for d in deps[n]:
            visit(d)
        state[n] = 2

    for n in deps:
        visit(n)
    return Batch(str(raw["id"]), tuple(items))


def parse_all(texts: list[str]) -> list[Batch]:
    """Valid batches only. An issue listed in two batches goes to the first; the later batch is dropped whole."""
    out, claimed = [], set()
    for t in texts:
        try:
            b = parse(t)
        except BatchError:
            continue
        nums = {it.issue for it in b.items}
        if nums & claimed:
            continue
        claimed |= nums
        out.append(b)
    return out


def _prefix(glob: str) -> str:
    m = re.search(r"[*?\[]", glob)
    return glob if m is None else glob[: m.start()]


def overlaps(a: tuple[str, ...], b: tuple[str, ...]) -> bool:
    """Conservative: two scopes overlap when one glob's literal prefix is a prefix of the other's. No scope = unknown = no claim."""
    return any(_prefix(x).startswith(_prefix(y)) or _prefix(y).startswith(_prefix(x)) for x in a for y in b)


def order_and_hold(
    picked: list[int], batches: list[Batch], merged: set[int], in_flight: set[int], limit: int
) -> tuple[list[int], dict[int, str]]:
    """picked: gate-ordered issue numbers. merged: issues whose agent PR merged. in_flight: issues with an open agent PR or a
    running agent. Returns (to run now, {issue: why held}).

    Batch items keep the slots they had in gate order but are reordered among themselves by manifest position. An item is held
    while a dependency is not merged, or while its scope overlaps work in flight or already chosen this round."""
    where = {it.issue: (b, i, it) for b in batches for i, it in enumerate(b.items)}
    slots = [k for k, n in enumerate(picked) if n in where]
    ordered = list(picked)
    for k, n in zip(slots, sorted((picked[k] for k in slots), key=lambda n: (where[n][0].id, where[n][1]))):
        ordered[k] = n
    held: dict[int, str] = {}
    chosen: list[int] = []
    claimed = [where[n][2].scope for n in in_flight if n in where and where[n][2].scope]
    for n in ordered:
        if n not in where:
            if len(chosen) < limit:
                chosen.append(n)
            continue
        it = where[n][2]
        unmet = [d for d in it.depends_on if d not in merged]
        if unmet:
            held[n] = "waiting on " + ", ".join(f"#{d}" for d in unmet)
        elif it.scope and any(overlaps(it.scope, c) for c in claimed):
            held[n] = "scope overlaps work in flight"
        elif len(chosen) < limit:
            chosen.append(n)
            if it.scope:
                claimed.append(it.scope)
    return chosen, held
