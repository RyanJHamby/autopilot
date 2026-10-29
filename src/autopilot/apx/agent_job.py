"""The agent job: runs the MODEL, as the dedicated agent account (backlog S1b). That account holds the Claude token and nothing that
can write to GitHub: it gets a short-lived, read-only, single-repository token for the checkout, and it never sees the App key.

It checks out the repo at the exact base commit, lets the model edit the worktree, applies the trusted patch checks, and returns the
resulting files as DATA. The orchestrator (which holds the write key) makes the commit and opens the PR.

    python -m autopilot.apx.agent_job < request.json > result.json

request: {repo, base_sha, base_branch, issue, prompt, model, effort, max_turns, commands, work_root, [binary, url, oauth_file, timeout]}
result:  {ok, summary, violations, turns, user, changes: [{path, mode, b64|null}]}     or {error}
"""

from __future__ import annotations

import base64
import getpass
import json
import os
import sys
import tempfile
from pathlib import Path

from . import claude_runner, committer, gitops

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "kit" / "runtime"))
import runner as kit_runner  # noqa: E402

MAX_RESULT_BYTES = 8 * 1024 * 1024  # a result bigger than this is refused rather than streamed through the orchestrator


def run_agent(req: dict, git_token: str | None) -> dict:
    root = Path(req["work_root"])
    root.mkdir(parents=True, exist_ok=True)
    gitops.prune_work(root)
    dest = root / f"agent-{req['repo'].replace('/', '_')}-{req['base_sha'][:12]}"
    co = gitops.checkout_pr(req["repo"], req["base_sha"], req["base_branch"], dest, git_token, url=req.get("url"), root=root)
    token = Path(req.get("oauth_file") or Path.home() / ".apx" / "claude-oauth").read_text().strip()
    home = Path(tempfile.mkdtemp(dir=root))
    runner = claude_runner.ClaudeRunner(
        token,
        home=home,
        commands=list(req["commands"]),
        prompt=req["prompt"],
        effort=req["effort"],
        binary=req.get("binary", "claude"),
        timeout=int(req.get("timeout", 1800)),
    )
    out = kit_runner.process(
        runner, kit_runner.Task(issue=req["issue"], prompt="", model=req["model"], max_turns=req["max_turns"]), co
    )
    who = getpass.getuser()
    base = {"summary": out.summary[-4000:], "violations": out.violations, "turns": out.usage.turns, "user": who}
    if not out.ok:
        return {"ok": False, **base, "changes": []}
    changes = []
    total = 0
    for c in committer.changes_from_worktree(co, req["base_sha"]):
        b64 = None if c.content is None else base64.b64encode(c.content).decode()
        total += len(b64 or "")
        changes.append({"path": c.path, "mode": c.mode, "b64": b64})
    if total > MAX_RESULT_BYTES:
        return {"ok": False, **base, "violations": ["result too large to hand back"], "changes": []}
    return {"ok": True, **base, "changes": changes}


def main() -> int:
    token = os.environ.get("APX_GIT_TOKEN") or None
    try:
        out = run_agent(json.load(sys.stdin), token)
    except Exception as e:  # noqa: BLE001 - one JSON line the orchestrator can post; never a traceback that could echo env
        out = {"error": f"{type(e).__name__}: {str(e)[:200]}"}
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
