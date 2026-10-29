"""Run a command as a different, unprivileged OS account (the `apx-ci` sandbox user) through `sudo`.

Why: the account that holds the GitHub App key and the Claude token must never be the account that executes a PR's code. With a
`Launcher(user)` every untrusted step (git checkout of a PR, the guard, the repo's CI commands) runs as a user that cannot read
those files. With `Launcher(None)` it behaves exactly like a plain `subprocess.run`, so nothing changes until the owner opts in.

Two properties are enforced here and tested:
  * secrets never appear in a command line (anyone on the machine can read argv with `ps`). They travel only through the
    environment, via `sudo --preserve-env=NAME`, and are re-exported inside a tiny shell wrapper;
  * the child's environment is built from scratch (`env -i`), never inherited from the orchestrator.
Needs one sudoers line, documented in deploy/apx-ci-account.sh:  apx ALL=(apx-ci) NOPASSWD:SETENV: ALL
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass

_SECRET_NAME = re.compile(r"^[A-Z_][A-Z0-9_]*$")
_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_USER = re.compile(r"^[a-z_][a-z0-9_-]{0,31}$")

# cd into the work directory (exit 97 if impossible), then exec with a clean environment: explicit secrets first, then the
# public KEY=VALUE pairs, then the command. Secret values are expanded by the shell from the preserved environment.
_SCRIPT = 'cd "$1" || exit 97; shift; exec /usr/bin/env -i {secrets}"$@"'


@dataclass(frozen=True)
class Launcher:
    user: str | None = None
    sudo: str = "/usr/bin/sudo"  # absolute on purpose: never resolved through a PATH that someone could plant a copy in

    def wrap(self, argv: list[str], cwd: str | None, env: dict[str, str], secret_names: list[str]) -> list[str]:
        """argv to hand to subprocess.run. With no user this is just the original command."""
        if not argv or "=" in argv[0] or "\0" in "".join(argv):
            raise ValueError("refusing a malformed command")
        if self.user is None:
            return list(argv)
        if not _USER.match(self.user) or self.user in ("root", "apx"):
            raise ValueError(f"{self.user!r} is not an acceptable sandbox account")
        for n in secret_names:
            if not _SECRET_NAME.match(n):
                raise ValueError(f"bad secret variable name {n!r}")
        public = []
        for k, v in env.items():
            if not _ENV_NAME.match(k) or "\0" in v:
                raise ValueError(f"bad environment entry {k!r}")
            public.append(f"{k}={v}")
        script = _SCRIPT.format(secrets="".join(f'{n}="${n}" ' for n in secret_names))
        pre = [f"--preserve-env={','.join(secret_names)}"] if secret_names else []
        return [self.sudo, "-n", "-u", self.user, *pre, "--", "/bin/sh", "-c", script, "sh", cwd or "/", *public, *argv]

    def run(
        self,
        argv: list[str],
        *,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        secret_env: dict[str, str] | None = None,
        timeout: float | None = None,
        input: str | None = None,
        **kw,
    ) -> subprocess.CompletedProcess:
        secrets = secret_env or {}
        full = self.wrap(argv, cwd, env or {}, sorted(secrets))
        if self.user is None:
            return subprocess.run(full, cwd=cwd, env={**(env or {}), **secrets}, timeout=timeout, input=input, **kw)
        # the sudo process itself gets only a minimal PATH plus the preserved secrets; its cwd must be somewhere anyone can enter
        return subprocess.run(
            full, cwd="/", env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", **secrets}, timeout=timeout, input=input, **kw
        )
