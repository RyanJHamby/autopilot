"""Pin a repo's required status checks to the apx GitHub App (backlog S3). An ADMIN action: the owner runs it.

Today the rulesets require `guard / guard` and `test`/`build` from ANY app (`integration_id` unset), so another app, or anything holding a
`checks:write` token, could post a passing check. Pinning sets `integration_id` to the apx App so only its results count.

Safety:
  * it refuses to pin a check name unless apx has actually been posting that name on this repo's recent PRs. Pinning a repo whose checks
    still come from Actions would stop every merge until the pin is undone;
  * dry run by default; `--apply` is required to write;
  * it changes nothing but `integration_id` on the named required checks: other rules, bypass actors and conditions are sent back as-is;
  * `--undo` removes the pin again.
"""

from __future__ import annotations

import argparse
import copy
import json
import subprocess
import sys

from .daemon import REQUIRED_CONTEXTS

APX_APP_ID = 5512558  # the autopilot-apx GitHub App
APX_SLUG = "autopilot-apx"
ALLOWED_REPOS = {"RyanJHamby/autopilot", "RyanJHamby/drillpad-workspace", "RyanJHamby/stencil"}
PUT_FIELDS = ("name", "target", "enforcement", "bypass_actors", "conditions", "rules")


def pin_rules(ruleset: dict, app_id: int, contexts: set[str], undo: bool = False) -> tuple[dict, list[str]]:
    """Returns (body to PUT, human-readable changes). Only `integration_id` of the named required checks is touched."""
    body = {k: copy.deepcopy(ruleset[k]) for k in PUT_FIELDS if k in ruleset}
    changes = []
    for rule in body.get("rules", []):
        if rule.get("type") != "required_status_checks":
            continue
        for chk in rule["parameters"]["required_status_checks"]:
            if chk["context"] not in contexts:
                continue
            before = chk.get("integration_id")
            if undo:
                chk.pop("integration_id", None)
            else:
                chk["integration_id"] = app_id
            if chk.get("integration_id") != before:
                changes.append(f"{chk['context']}: integration_id {before or 'any'} -> {chk.get('integration_id') or 'any'}")
    return body, changes


def required_contexts(ruleset: dict) -> list[str]:
    return [
        c["context"]
        for r in ruleset.get("rules", [])
        if r.get("type") == "required_status_checks"
        for c in r["parameters"]["required_status_checks"]
    ]


def missing_evidence(gh, repo: str, contexts: set[str], recent: int = 5) -> list[str]:
    """Contexts that apx has NOT posted on any of the repo's most recent PR heads. Empty list = safe to pin."""
    prs = gh(f"repos/{repo}/pulls?state=all&per_page={recent}&sort=updated&direction=desc")
    seen: set[str] = set()
    for pr in prs:
        runs = gh(f"repos/{repo}/commits/{pr['head']['sha']}/check-runs?per_page=100")["check_runs"]
        seen |= {r["name"] for r in runs if (r.get("app") or {}).get("slug") == APX_SLUG and r.get("conclusion") == "success"}
    return sorted(contexts - seen)


def _gh(path: str, method: str = "GET", body: dict | None = None):
    argv = ["gh", "api", "-X", method, path]
    if body is not None:
        argv += ["--input", "-"]
    p = subprocess.run(argv, input=json.dumps(body) if body is not None else None, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"gh api {method} {path} failed: {p.stderr.strip()[:200]}")
    return json.loads(p.stdout) if p.stdout.strip() else {}


def run(repo: str, *, apply: bool, undo: bool, force: bool, gh=_gh) -> int:
    if repo not in ALLOWED_REPOS:
        print(f"{repo} is outside apx scope", file=sys.stderr)
        return 2
    rulesets = [r for r in gh(f"repos/{repo}/rulesets") if r["name"] == "autopilot-main"]
    if len(rulesets) != 1:
        print("expected exactly one ruleset named autopilot-main", file=sys.stderr)
        return 2
    rs = gh(f"repos/{repo}/rulesets/{rulesets[0]['id']}")
    # only the names apx itself posts for this repo; any other required check keeps whatever app posts it today
    contexts = set(REQUIRED_CONTEXTS[repo]) & set(required_contexts(rs))
    body, changes = pin_rules(rs, APX_APP_ID, contexts, undo=undo)
    if not changes:
        print("nothing to change (already in that state)")
        return 0
    if not undo and not force:
        missing = missing_evidence(gh, repo, contexts)
        if missing:
            print(f"REFUSING: apx has not posted {missing} successfully on recent PRs of {repo}.", file=sys.stderr)
            print(
                "Pinning now would stop merges. Make apx authoritative for this repo first (APX_AUTHORITATIVE).", file=sys.stderr
            )
            return 3
    for c in changes:
        print(("WOULD " if not apply else "") + "change " + c)
    if not apply:
        print("dry run: nothing written (add --apply)")
        return 0
    gh(f"repos/{repo}/rulesets/{rulesets[0]['id']}", method="PUT", body=body)
    print(f"{'undone' if undo else 'pinned'} on {repo}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo", required=True)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--undo", action="store_true")
    ap.add_argument("--force", action="store_true", help="skip the evidence check (not recommended)")
    ns = ap.parse_args(argv)
    return run(ns.repo, apply=ns.apply, undo=ns.undo, force=ns.force)


if __name__ == "__main__":
    sys.exit(main())
