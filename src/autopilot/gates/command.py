"""`ap gate show BET GATE`: where a bet stands against a gate. Read-only."""

from __future__ import annotations

import argparse
import json
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
    print(f"unknown gate command {ns.gate_cmd!r}")
    return 2


def cmd_show(ns: argparse.Namespace, *, repo_name, load_portfolio, policy_root: Path) -> int:
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
    text, _ = waivers.read_base(policy_root)
    wvs, _ = waivers.parse(text)
    check = _repo_check(ns, load_portfolio(), repo_name, wvs)
    items = core.evaluate(ns.gate, gates[ns.gate], ns.bet, control, check)
    if getattr(ns, "json", False):
        print(json.dumps({"bet": ns.bet, "gate": ns.gate, "title": gates[ns.gate]["title"], "ready": core.ready(items),
                          "items": [asdict(i) for i in items]}, indent=2))
    else:
        print(core.render(ns.bet, ns.gate, gates[ns.gate], items))
    return 0 if core.ready(items) else 1
