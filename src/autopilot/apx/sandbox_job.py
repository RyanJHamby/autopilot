"""One sandboxed job per PR: checkout, guard, CI. Runs as the unprivileged sandbox account (see runas.py), never as the account
that holds the App key or the Claude token.

Everything a PR's code can touch happens in here; the orchestrator only sends a small JSON request and reads a small JSON result.
The git token arrives through the environment (APX_GIT_TOKEN) and exists only for the fetch; it is never written to disk or argv.

    python -m autopilot.apx.sandbox_job < request.json > result.json

request:  {repo, sha, base_branch, head_ref, kit_dir, steps: [[cmd, dir], ...], toolchain_links: [...], work_root, [url]}
result:   {guard: [ok, text], ci: [ok, markdown] | null}      (ci is null when the guard rejected the PR: its code never ran)
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

from . import cilane, gitops, guardlane


def run_job(req: dict, token: str | None) -> dict:
    root = Path(req["work_root"])
    root.mkdir(parents=True, exist_ok=True)
    gitops.prune_work(root)
    dest = root / f"pr-{req['repo'].replace('/', '_')}-{req['sha'][:12]}"
    co = gitops.checkout_pr(req["repo"], req["sha"], req["base_branch"], dest, token, url=req.get("url"), root=root)
    tmp = Path(tempfile.mkdtemp(dir=root))
    g_ok, g_out = guardlane.run_guard(
        co, Path(req["kit_dir"]), base=f"origin/{req['base_branch']}", head="HEAD", head_ref=req["head_ref"], tmp=tmp
    )
    if not g_ok:
        return {"guard": [False, g_out], "ci": None}  # a rejected PR's code is never executed
    steps = [(c, d) for c, d in req["steps"]]
    home = Path(tempfile.mkdtemp(dir=root))
    res = cilane.run_commands(co, steps, home=home, toolchain_links=list(req.get("toolchain_links", [])), real_home=Path.home())
    ok, md = cilane.summarize(res, steps)
    return {"guard": [True, g_out], "ci": [ok, md]}


def main() -> int:
    token = os.environ.get("APX_GIT_TOKEN") or None
    try:
        out = run_job(json.load(sys.stdin), token)
    except Exception as e:  # noqa: BLE001 - report a failure the orchestrator can post, never a traceback that could echo env
        out = {"error": f"{type(e).__name__}: {str(e)[:200]}"}
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
