"""Host tools each enrolled repo's CI needs, checked by the doctor AS the sandbox account, on the PATH the sandbox job gets.

Where the declarations live (both are data merged by the owner, never read from a PR):
- repos in APX_PRIVATE_CI: the "tools" list of their entry in repo_ci.json (unchanged);
- the autopilot-managed repos (their CI is the repo's own .autopilot/repo.yaml `ci:` list, which names no host tools): "repos" here.

A bare presence check is not always enough (Ubuntu's apt gitleaks 8.18 exists but has no `gitleaks git`; a clang++ without the UBSan
runtime compiles but does not link with -fsanitize=undefined), so "probes" maps a TOOL to a command that must succeed, for every repo
that declares that tool; "repo_probes" maps OWNER/REPO -> TOOL -> a probe for that repo only (control's python3 must import yaml, pawl's
need not), with an optional `hint`, and replaces the unscoped probe for that repo and tool. A probe's argv starts with the tool itself (run as the binary found on the sandbox PATH) or with an absolute
path such as /bin/sh; `stdin` is fed to it, and `expect`, if set, is a regex its output must match. "hints" says how to install a tool.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .repo_ci import parse_tool

REPO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
DATA_FILE = Path(__file__).with_name("host_tools.json")
DEFAULT_HINT = "install it where the sandbox PATH finds it (docs/apx-linux-host.md, step 5)"


@dataclass(frozen=True)
class Probe:
    argv: tuple[str, ...]
    needs: str
    stdin: str | None = None
    expect: str | None = None
    hint: str | None = None


@dataclass(frozen=True)
class HostTools:
    repos: dict[str, tuple[str, ...]]
    probes: dict[str, Probe]
    hints: dict[str, str]
    repo_probes: dict[str, dict[str, Probe]] = field(default_factory=dict)

    def hint(self, tool: str) -> str:
        return self.hints.get(tool, DEFAULT_HINT)

    def probe_for(self, repo: str, tool: str) -> Probe | None:
        return self.repo_probes.get(repo, {}).get(tool) or self.probes.get(tool)

    def hint_for(self, repo: str, tool: str) -> str:
        scoped = self.repo_probes.get(repo, {}).get(tool)
        return scoped.hint if scoped and scoped.hint else self.hint(tool)


def _probe(tool: str, raw: dict) -> Probe:
    argv = raw.get("argv") if isinstance(raw, dict) else None
    if not isinstance(argv, list) or not argv or not all(isinstance(a, str) and a for a in argv):
        raise ValueError(f"probe for {tool}: argv must be a non-empty list of strings")
    if argv[0] != tool and not argv[0].startswith("/"):
        raise ValueError(f"probe for {tool}: argv must start with {tool!r} or an absolute path, not {argv[0]!r}")
    needs = raw.get("needs")
    if not isinstance(needs, str) or not needs.strip():
        raise ValueError(f"probe for {tool}: say what it proves in `needs`")
    stdin, expect, hint = raw.get("stdin"), raw.get("expect"), raw.get("hint")
    if stdin is not None and not isinstance(stdin, str):
        raise ValueError(f"probe for {tool}: stdin must be a string")
    if hint is not None and not isinstance(hint, str):
        raise ValueError(f"probe for {tool}: hint must be a string")
    if expect is not None:
        try:
            re.compile(expect)
        except (re.error, TypeError) as e:
            raise ValueError(f"probe for {tool}: bad expect regex ({e})") from None
    return Probe(tuple(argv), needs, stdin, expect, hint)


def load(path: Path | None = None) -> HostTools:
    raw = json.loads(Path(path or DATA_FILE).read_text())
    repos: dict[str, tuple[str, ...]] = {}
    for repo, entries in (raw.get("repos") or {}).items():
        if not isinstance(entries, list):
            raise ValueError(f"{repo}: host tools must be a list")
        for e in entries:
            parse_tool(e)  # raises ValueError; same syntax as repo_ci.json
        repos[repo] = tuple(entries)
    probes = {tool: _probe(tool, body) for tool, body in (raw.get("probes") or {}).items()}
    hints = raw.get("hints") or {}
    if not all(isinstance(v, str) for v in hints.values()):
        raise ValueError("hints must be strings")
    scoped: dict[str, dict[str, Probe]] = {}
    for repo, body in (raw.get("repo_probes") or {}).items():
        if not REPO.match(repo) or not isinstance(body, dict):
            raise ValueError(f"repo_probes: {repo!r} must be OWNER/REPO mapping tool -> probe")
        scoped[repo] = {tool: _probe(tool, b) for tool, b in body.items()}
    return HostTools(repos, probes, dict(hints), scoped)


def declared(repo: str, private_ci, data: HostTools, specs: dict) -> tuple[str, ...]:
    """The tool entries for one repo: from repo_ci.json for APX_PRIVATE_CI repos, from this file for every other repo."""
    if repo in private_ci:
        spec = specs.get(repo)
        return tuple(spec.tools) if spec else ()
    return data.repos.get(repo, ())
