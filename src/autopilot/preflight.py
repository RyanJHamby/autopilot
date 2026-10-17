"""Readiness check for letting agents run unattended on a repo. `evaluate` is pure over gathered facts; the CLI gathers them."""

from __future__ import annotations

import re

PASS, WARN, FAIL = "PASS", "WARN", "FAIL"
SHA = re.compile(r"@([0-9a-f]{40})")


def evaluate(f: dict) -> list[tuple[str, str]]:
    """f: facts about one repo. Returns [(level, message)]; FAIL = do not leave unattended."""
    out: list[tuple[str, str]] = []

    def add(level: str, msg: str) -> None:
        out.append((level, msg))

    add(
        PASS if "CLAUDE_CODE_OAUTH_TOKEN" in f["secrets"] else FAIL,
        "Claude secret CLAUDE_CODE_OAUTH_TOKEN is set"
        if "CLAUDE_CODE_OAUTH_TOKEN" in f["secrets"]
        else "no CLAUDE_CODE_OAUTH_TOKEN secret (run `claude setup-token` in Terminal.app, then gh secret set)",
    )
    v = f["variables"]
    add(
        PASS if v.get("AUTOPILOT_ENABLED") == "true" else FAIL,
        "AUTOPILOT_ENABLED=true" if v.get("AUTOPILOT_ENABLED") == "true" else "AUTOPILOT_ENABLED is not true (ap enable)",
    )
    if v.get("AUTOPILOT_PAUSED") == "true":
        add(FAIL, "AUTOPILOT_PAUSED=true (ap resume)")
    if v.get("AUTOPILOT_DEBUG") == "true":
        add(
            WARN if not f.get("public") else FAIL,
            "AUTOPILOT_DEBUG=true prints full agent output in logs"
            + (" (PUBLIC repo: leaks transcripts)" if f.get("public") else "; fine privately, turn off when stable"),
        )

    rs = f.get("ruleset")
    if not rs:
        add(FAIL, "no autopilot-main ruleset (ap ruleset --central --check <ci> --apply)")
    else:
        checks = set(rs.get("checks", []))
        add(
            PASS if "guard / guard" in checks else FAIL,
            "ruleset requires guard / guard" if "guard / guard" in checks else "ruleset does not require guard / guard",
        )
        add(
            PASS if len(checks) >= 2 else WARN,
            f"ruleset required checks: {sorted(checks)}"
            if len(checks) >= 2
            else "ruleset requires only the guard check; add the repo's CI check so agent PRs cannot merge on red",
        )
        add(
            PASS if rs.get("signatures") else FAIL,
            "signed commits required" if rs.get("signatures") else "ruleset does not require signed commits",
        )
        add(
            PASS if rs.get("codeowner") else FAIL,
            "code-owner review required" if rs.get("codeowner") else "ruleset does not require code-owner review",
        )

    if f.get("codeowners_catchall"):
        add(WARN, "CODEOWNERS has a catch-all `*`: every PR needs you and no auto-merge class can ever apply")
    if not f.get("codeowners_has_block"):
        add(FAIL, "CODEOWNERS lacks the autopilot protected-paths block")

    shas = set(f.get("caller_shas", []))
    approved = set(f.get("approved", []))
    if not shas:
        add(FAIL, "repo is not on the shared kit (no pinned callers)")
    elif len(shas) > 1:
        add(FAIL, f"callers disagree on the kit sha: {sorted(s[:7] for s in shas)}")
    else:
        s = next(iter(shas))
        add(
            PASS if s in approved else FAIL,
            f"kit {s[:7]} is owner-approved" if s in approved else f"kit {s[:7]} is NOT on the approved list",
        )
        latest = f.get("latest_approved")
        if latest and s != latest:
            add(WARN, f"a newer approved kit exists ({latest[:7]}); `ap rollout` bumps it")

    exec_run = f.get("last_exec")
    if exec_run is None:
        add(WARN, "no agent run yet: run one cheap smoke issue to prove the app install, signing and PR creation")
    elif exec_run == "success":
        add(PASS, "last agent run succeeded (app installed, signing and PR creation work)")
    else:
        add(
            FAIL,
            f"last agent run ended `{exec_run}` (read its log; `Claude Code is not installed` means install https://github.com/apps/claude)",
        )
    if f.get("billing_suspect"):
        add(
            FAIL,
            "recent Actions jobs failed within seconds: likely a billing/spending-limit block (Settings > Billing > Spending limit)",
        )

    n, cap = f.get("open_agent_prs", 0), f.get("max_open_prs", 3)
    add(
        WARN if n >= cap else PASS,
        f"{n} open agent PRs (cap {cap})" + ("; agents stall at the cap until you review" if n >= cap else ""),
    )
    q = f.get("agent_ready", 0)
    add(PASS if q else WARN, f"{q} agent-ready issue(s) queued" if q else "no agent-ready issues: nothing to do overnight")
    if not f.get("merge_classes"):
        add(WARN, "no auto-merge classes: every agent PR waits for you (fine to start; see ap report for promotion hints)")
    else:
        add(PASS, f"auto-merge classes: {sorted(f['merge_classes'])}")
    if f.get("data_class") == "restricted":
        add(FAIL, "data_class is restricted: no cloud agents allowed")
    return out


def summarize(results: list[tuple[str, str]]) -> tuple[int, int, int]:
    return tuple(sum(1 for lv, _ in results if lv == k) for k in (PASS, WARN, FAIL))  # type: ignore[return-value]
