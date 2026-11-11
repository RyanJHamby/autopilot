"""`ap gate show BET GATE`: where a bet stands against a gate. Read-only."""

from __future__ import annotations

import argparse
import json
import shlex
from dataclasses import asdict
from datetime import date
from pathlib import Path

from autopilot.gates import core, load_gates
from autopilot.standard import command as standard_command
from autopilot.standard import waivers


def _repo_check(ns: argparse.Namespace, portfolio: dict, repo_name, wvs: list[dict]) -> core.RepoCheck:
    """The real repo check: the bet's repo, held to the CURRENT standard as if it were new (the same check `ap enable` uses), offline."""

    def check(fields: dict):
        repo = (fields.get("repo") or "").strip()
        name = repo.split("/")[-1]
        if not name:
            return None, [], []
        explicit = Path(ns.path) if getattr(ns, "path", None) else None
        return standard_command.revive_check(
            name, portfolio, getattr(ns, "root", None), explicit, repo_name, standard_command.offline_gh, wvs, date.today()
        )

    return check


def cmd_gate(ns: argparse.Namespace, *, repo_name, load_portfolio, policy_root: Path) -> int:
    if ns.gate_cmd == "show":
        return cmd_show(ns, repo_name=repo_name, load_portfolio=load_portfolio, policy_root=policy_root)
    if ns.gate_cmd == "seed":
        return cmd_seed(ns)
    print(f"unknown gate command {ns.gate_cmd!r}")
    return 2


def _prepare(ns: argparse.Namespace) -> tuple[dict, Path] | int:
    """Validate the gate, the control repo and the bet before anything is read or written. Returns (gate, control) or an exit code."""
    gates = load_gates().get("gates", {})
    if ns.gate not in gates:
        print(f"unknown gate {ns.gate!r}; the gates are: {', '.join(sorted(gates))}")
        return 2
    control = core.resolve_control(getattr(ns, "control", None))
    if not (control / "pawl.toml").is_file():
        print(f"{control} is not a control repo (no pawl.toml); pass --control PATH or set PAWL_ROOT")
        return 2
    try:
        core.pawl_steps(control, ns.bet)  # the bet must exist before anything is said about it
    except core.PawlError as e:
        print(str(e))
        return 2
    return gates[ns.gate], control


def cmd_show(ns: argparse.Namespace, *, repo_name, load_portfolio, policy_root: Path) -> int:
    prepared = _prepare(ns)
    if isinstance(prepared, int):
        return prepared
    gate, control = prepared
    text, _ = waivers.read_base(policy_root)
    wvs, _ = waivers.parse(text)
    check = _repo_check(ns, load_portfolio(), repo_name, wvs)
    items = core.evaluate(ns.gate, gate, ns.bet, control, check)
    if getattr(ns, "json", False):
        print(json.dumps({"bet": ns.bet, "gate": ns.gate, "title": gate["title"], "ready": core.ready(items),
                          "items": [asdict(i) for i in items]}, indent=2))
    else:
        print(core.render(ns.bet, ns.gate, gate, items))
    return 0 if core.ready(items) else 1


def cmd_seed(ns: argparse.Namespace) -> int:
    """Add the gate's manual steps to the control repo as draft pawl steps. Dry run unless --apply; --no-push unless --push."""
    prepared = _prepare(ns)
    if isinstance(prepared, int):
        return prepared
    gate, control = prepared
    plan = core.seed_plan(ns.gate, gate, ns.bet, control)
    if not plan:
        print(f"the {ns.gate} gate has no manual steps to seed")
        return 0
    missing = [s for s in plan if not s.exists]
    if not missing:
        print(f"nothing to seed: all {len(plan)} step(s) of the {ns.gate} gate are already in pawl for {ns.bet}")
        return 0
    push = bool(getattr(ns, "push", False))
    if not getattr(ns, "apply", False):
        print(f"[dry run] would add {len(missing)} of {len(plan)} step(s) to {ns.bet} ({len(plan) - len(missing)} already there, left alone):")
        for s in missing:
            print("  " + shlex.join(core.seed_command(control, ns.bet, s, push)))
        print("Nothing was written. Re-run with --apply to write them" + ("" if push else " (committed locally, not pushed; add --push to push)") + ".")
        return 0
    written, err = core.apply_seed(plan, control, ns.bet, push)
    for sid in written:
        print(f"added {sid}")
    if err:
        print(f"STOPPED after {len(written)} of {len(missing)}: {err}")
        print("Nothing already written was undone; re-run the same command to resume.")
        return 1
    print(f"added {len(written)} draft step(s) to {ns.bet}.")
    print(
        "Pushed as each step was added (pawl's own sync)."
        if push
        else "They are committed locally and not pushed. `pawl sync` (or your scheduled tick) pushes them."
    )
    return 0
