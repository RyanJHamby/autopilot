"""Orchestrator side of the sandbox: send one JSON job per PR to the unprivileged account and read back one JSON result.

`SandboxLanes` exposes the same checkout / guard / ci callables the executor already uses, so the executor does not change.
The PR's code (the guard run, the repo's CI commands) only ever executes inside the sandbox account, which cannot read the
App key or the Claude token. The git token is handed over through the environment only.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from .runas import Launcher


def run_in_sandbox(
    launcher: Launcher,
    req: dict,
    token: str | None,
    *,
    python: str,
    code_dir: str,
    home: str,
    timeout: int = 3600,
    module: str = "autopilot.apx.sandbox_job",
) -> dict:
    env = {
        "PYTHONPATH": f"{code_dir}/src",
        "HOME": home,
        "PATH": f"/opt/homebrew/bin:{home}/.local/bin:/usr/bin:/bin",
        "CI": "true",
        "LANG": "en_US.UTF-8",
        "GIT_TERMINAL_PROMPT": "0",
    }
    secret = {"APX_GIT_TOKEN": token} if token else {}
    try:
        p = launcher.run(
            [python, "-m", module],
            cwd=req["work_root"],
            env=env,
            secret_env=secret,
            input=json.dumps(req),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except Exception as e:  # noqa: BLE001 - includes a timeout; the PR's checks still complete as failures
        return {"error": f"sandbox did not finish ({type(e).__name__})"}
    for line in reversed(p.stdout.strip().splitlines()):
        try:
            return json.loads(line)
        except ValueError:
            continue
    if p.returncode == 97:
        return {
            "error": "sandbox work directory is missing or not accessible to the sandbox account (run deploy/apx-ci-account.sh)"
        }
    return {"error": f"sandbox produced no result (exit {p.returncode})"}


class SandboxLanes:
    """checkout() only records which PR to run; guard() runs the whole job once and caches it; ci() returns the cached result."""

    def __init__(
        self,
        launcher: Launcher,
        *,
        base_branch: str,
        kit_dir: str,
        work_root: str,
        python: str,
        code_dir: str,
        home: str,
        token_for: Callable[[str], str],
        steps_for: Callable[[str], list],
        toolchain_links: list[str],
        url_for: Callable[[str], str | None] = lambda repo: None,
        expected_user: str | None = None,
    ):
        self.__dict__.update(locals())
        del self.__dict__["self"]
        self.expected_user = expected_user or launcher.user
        self._handles: dict[str, tuple[str, str]] = {}
        self._results: dict[str, dict] = {}

    def checkout(self, repo: str, sha: str) -> Path:
        handle = Path("/sandbox") / repo / sha  # a label, not a real path: the real checkout lives where only the sandbox can see
        self._handles[str(handle)] = (repo, sha)
        return handle

    def guard(self, co: Path, head_ref: str) -> tuple[bool, str]:
        repo, sha = self._handles[str(co)]
        req = {
            "repo": repo,
            "sha": sha,
            "base_branch": self.base_branch,
            "head_ref": head_ref,
            "kit_dir": self.kit_dir,
            "steps": self.steps_for(repo),
            "toolchain_links": self.toolchain_links,
            "work_root": self.work_root,
        }
        url = self.url_for(repo)
        if url:
            req["url"] = url
        res = run_in_sandbox(self.launcher, req, self.token_for(repo), python=self.python, code_dir=self.code_dir, home=self.home)
        if "error" not in res and res.get("user") != self.expected_user:
            # the job ran, but not as the sandbox account (a misconfigured sudo, say). Its result cannot be trusted and its
            # PR code ran with the wrong privileges, so refuse it and say so.
            res = {"error": f"sandbox ran as {res.get('user')!r}, expected {self.expected_user!r}; result refused"}
        self._results[str(co)] = res
        if "error" in res:
            return False, f"sandbox job failed: {res['error']}"
        g_ok, g_out = res["guard"]
        return bool(g_ok), f"{g_out}\n\n_ran as {res['user']}_"

    def ci(self, co: Path) -> tuple[bool, str]:
        res = self._results.get(str(co)) or {}
        ci = res.get("ci")
        if not ci:
            return False, "not run: guard failed"
        return bool(ci[0]), f"{ci[1]}\n\n_ran as {res['user']}_"


def run_agent_in_sandbox(
    launcher: Launcher,
    req: dict,
    read_token: str | None,
    *,
    python: str,
    code_dir: str,
    home: str,
    expected_user: str | None = None,
    timeout: int = 3600,
) -> tuple[dict, list]:
    """Run the model as the agent account and return (result, changes as committer.FileChange). A result from the wrong account is
    refused: the model must only ever run with the agent account's privileges."""
    import base64

    from .committer import FileChange

    res = run_in_sandbox(
        launcher, req, read_token, python=python, code_dir=code_dir, home=home, timeout=timeout, module="autopilot.apx.agent_job"
    )
    want = expected_user or launcher.user
    if "error" not in res and res.get("user") != want:
        return {"ok": False, "error": f"agent ran as {res.get('user')!r}, expected {want!r}; result refused"}, []
    if "error" in res:
        return {"ok": False, **res}, []
    changes = [
        FileChange(c["path"], c["mode"], None if c["b64"] is None else base64.b64decode(c["b64"])) for c in res.get("changes", [])
    ]
    return res, changes
