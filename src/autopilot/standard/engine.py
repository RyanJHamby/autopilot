"""Runs the standard's rules (`checks.yaml`) against a repo checkout.

Every rule is a function `check(repo) -> (result, messages)` registered in CHECKS under the rule's id. A test requires
the registry and `checks.yaml` to list the same ids, so a rule can't exist on paper only, or in code only.

Results are `pass | fail | unknown | skip`. `unknown` means the check couldn't be answered (no `gh`, not a git repo, a
workflow that doesn't parse); it is never counted as a pass. A check that raises is `unknown`, never a crash and never
a pass. `skip` is only for a rule whose `applies_to` doesn't match the repo, and it is still printed.
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path

import yaml

from autopilot.standard import load_checks

# Mirrors kit/runtime/guard.py DEFAULT_PROTECTED. The kit isn't in the wheel, so it is copied, and a test fails if the
# two lists drift.
PROTECTED = [
    ".github/**",
    ".autopilot/**",
    ".claude/**",
    "AGENTS.md",
    "CLAUDE.md",
    ".mcp.json",
    "CODEOWNERS",
    ".github/CODEOWNERS",
]

# Workflows autopilot writes and owns. Doctor trusts these for the secret-exposure rule.
AUTOPILOT_WORKFLOWS = {
    "agent-dispatch.yml",
    "agent-exec.yml",
    "guard.yml",
    "handshake.yml",
    "automerge.yml",
    "improve.yml",
    "audit.yml",
    "rebase.yml",
}

SHA = re.compile(r"^[0-9a-f]{40}$")
USES = re.compile(r"^\s*-?\s*uses:\s*['\"]?([^'\"\s#]+)", re.M)
AGENTS_MD_BUDGET = 60  # a starting value, not a measured threshold


@dataclass
class Result:
    id: str
    label: str
    level: str
    result: str
    findings: list[str] = field(default_factory=list)


class Repo:
    """One checkout plus what the checks need to know about it. `gh` is injected so tests never touch the network."""

    def __init__(
        self,
        path: Path,
        entry: dict | None = None,
        slug: str | None = None,
        gh: Callable | None = None,
        github_public: bool | None = None,
    ):
        self.path = Path(path)
        self.entry = entry  # this repo's policy/portfolio.yaml entry, or None if it isn't in the portfolio
        self.slug = slug
        self.github_public = github_public  # what GitHub says, when it could be asked; it wins over the portfolio
        self.gh = gh or subprocess.run
        self._workflows: list[tuple[Path, str, object]] | None = None

    @property
    def public(self) -> bool | None:
        """What GitHub says if it was asked, else the portfolio's `public` flag. None when neither is known."""
        if self.github_public is not None:
            return self.github_public
        return None if self.entry is None else bool(self.entry.get("public", False))

    def read(self, rel: str) -> str | None:
        p = self.path / rel
        return p.read_text(encoding="utf-8", errors="replace") if p.is_file() else None

    def repo_cfg(self) -> dict:
        try:
            return yaml.safe_load(self.read(".autopilot/repo.yaml") or "") or {}
        except yaml.YAMLError:
            return {}

    def protected(self) -> list[str]:
        extra = (self.repo_cfg().get("guard") or {}).get("extra_protected") or []
        return PROTECTED + [str(p) for p in extra]

    def workflows(self) -> list[tuple[Path, str, object]]:
        """(path, raw text, parsed YAML or None if it doesn't parse) for every workflow file."""
        if self._workflows is None:
            out = []
            wf_dir = self.path / ".github/workflows"
            for p in sorted(wf_dir.glob("*.y*ml")) if wf_dir.is_dir() else []:
                text = p.read_text(encoding="utf-8", errors="replace")
                try:
                    doc = yaml.safe_load(text)
                except yaml.YAMLError:
                    doc = None
                out.append((p, text, doc))
            self._workflows = out
        return self._workflows


Outcome = tuple[str, list[str]]


def _ok() -> Outcome:
    return "pass", []


def _verdict(findings: list[str]) -> Outcome:
    return ("fail", findings) if findings else _ok()


def triggers(doc: object) -> set[str]:
    """Event names a workflow runs on. PyYAML reads the bare key `on` as the boolean True, so look for both."""
    if not isinstance(doc, dict):
        return set()
    on = doc.get("on", doc.get(True))
    if isinstance(on, str):
        return {on}
    if isinstance(on, list):
        return {str(x) for x in on}
    if isinstance(on, dict):
        return {str(k) for k in on}
    return set()


def pinned_actions(repo: Repo) -> Outcome:
    findings = []
    for path, text, _ in repo.workflows():
        for line in text.splitlines():
            m = USES.match(line)
            if not m:
                continue
            ref = m.group(1)
            if ref.startswith(("./", "docker://")):
                continue
            if "@" not in ref or not SHA.match(ref.rsplit("@", 1)[1]):
                findings.append(f"{path.name}: action not pinned to a SHA: {line.strip()}")
    return _verdict(findings)


def workflow_permissions(repo: Repo) -> Outcome:
    findings, unreadable = [], []
    for path, _, doc in repo.workflows():
        if not isinstance(doc, dict):
            unreadable.append(f"{path.name}: not a readable workflow")
        elif "permissions" not in doc:
            findings.append(f"{path.name}: no top-level `permissions`")
    if findings:
        return "fail", findings
    return ("unknown", unreadable) if unreadable else _ok()


def no_privileged_triggers(repo: Repo) -> Outcome:
    findings, unreadable = [], []
    for path, _, doc in repo.workflows():
        if not isinstance(doc, dict):
            unreadable.append(f"{path.name}: not a readable workflow")
        elif "pull_request_target" in triggers(doc):
            findings.append(f"{path.name}: runs on pull_request_target")
    if findings:
        return "fail", findings
    return ("unknown", unreadable) if unreadable else _ok()


def secret_exposed_workflows(repo: Path | Repo) -> list[str]:
    """Names of host workflows that hand repo secrets to code from a PR branch and don't exclude agent/* branches.
    GITHUB_TOKEN doesn't count."""
    root = repo.path if isinstance(repo, Repo) else Path(repo)
    out: list[str] = []
    for wf in sorted((root / ".github/workflows").glob("*.y*ml")):
        if wf.name in AUTOPILOT_WORKFLOWS:
            continue
        text = wf.read_text()
        uses_secret = any(s != "GITHUB_TOKEN" for s in re.findall(r"secrets\.([A-Za-z0-9_]+)", text))
        on_pr = re.search(r"^\s*pull_request(_target)?\s*:", text, re.M) is not None
        if uses_secret and on_pr and "agent/" not in text:
            out.append(wf.name)
    return out


def secret_exposed(repo: Repo) -> Outcome:
    return _verdict(
        [
            f"{name}: uses repo secrets on pull_request with no agent/* exclusion (an agent PR could read or spend them)"
            for name in secret_exposed_workflows(repo)
        ]
    )


def _norm(pattern: str) -> str:
    """A protected glob or CODEOWNERS pattern as a plain path: `/.github/` and `.github/**` both become `.github`."""
    p = pattern.strip().lstrip("/")
    for tail in ("/**", "/*", "/"):
        if p.endswith(tail):
            p = p[: -len(tail)]
    return p


def codeowners_entries(text: str) -> list[str]:
    """Normalized patterns of every CODEOWNERS line that names at least one owner."""
    out = []
    for line in text.splitlines():
        parts = line.split("#", 1)[0].split()
        if len(parts) >= 2:
            out.append(_norm(parts[0]))
    return out


def codeowners_cover(repo: Repo) -> Outcome:
    """Each protected path needs a CODEOWNERS entry that is that path or a directory above it (or `*`).

    This is a path-prefix test, not GitHub's matcher: it handles the plain, directory and `dir/**` forms. Wildcard
    patterns in the middle of a path aren't understood, so such an entry is not counted as covering anything."""
    text = None
    for rel in ("CODEOWNERS", ".github/CODEOWNERS", "docs/CODEOWNERS"):
        text = repo.read(rel)
        if text is not None:
            break
    if text is None:
        return "fail", ["no CODEOWNERS file"]
    entries = codeowners_entries(text)
    missing = []
    for pattern in repo.protected():
        path = _norm(pattern)
        covered = any(e == "*" or e == path or path.startswith(e + "/") for e in entries if "*" not in e or e == "*")
        if not covered:
            missing.append(f"{pattern} is not owned in CODEOWNERS")
    return _verdict(missing)


SECRET_SUFFIXES = {".pem", ".p12", ".pfx", ".kdbx", ".jks"}
SECRET_NAMES = {"id_rsa", "id_ed25519", "id_ecdsa", "credentials.json", "secrets.json", "service-account.json"}


def secret_file(rel: str) -> bool:
    """A file name that normally holds a secret. Names only: contents are never read. Deliberately narrower than the
    cloud-agent sensitivity list in cli.py, which also flags notes like journal.md that are fine to track."""
    p = Path(rel)
    base = p.name.lower()
    if base == ".env" or base.startswith(".env."):
        return not base.endswith((".example", ".sample", ".template"))
    if p.suffix.lower() in SECRET_SUFFIXES or base in SECRET_NAMES:
        return True
    return ".aws" in p.parts[:-1] and base == "credentials"


def no_tracked_secrets(repo: Repo) -> Outcome:
    r = subprocess.run(["git", "ls-files", "-z"], cwd=repo.path, capture_output=True, text=True)
    if r.returncode != 0:
        return "unknown", ["not a git repository"]
    return _verdict([f"{f} is tracked by git" for f in r.stdout.split("\0") if f and secret_file(f)])


def thin_claude_md(repo: Repo) -> Outcome:
    text = repo.read("CLAUDE.md")
    if text is None or "@AGENTS.md" not in text:
        return "fail", ["CLAUDE.md does not import AGENTS.md"]
    return _ok()


def one_check_entrypoint(repo: Repo) -> Outcome:
    makefile = repo.read("Makefile") or ""
    if re.search(r"^check\s*:", makefile, re.M) or repo.repo_cfg().get("ci"):
        return _ok()
    return "fail", ["no `check` target in a Makefile and no `ci:` list in .autopilot/repo.yaml"]


def license_present(repo: Repo) -> Outcome:
    if any((repo.path / n).is_file() for n in ("LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING")):
        return _ok()
    return "fail", ["no LICENSE file"]


def ruleset_present(repo: Repo) -> Outcome:
    """Any ruleset at all. Doctor separately asks for the specific `autopilot-main` one on installed repos."""
    if not repo.slug:
        return "unknown", ["no GitHub repo name to ask about"]
    try:
        r = repo.gh(["gh", "api", f"repos/{repo.slug}/rulesets", "--jq", ".[].name"], capture_output=True, text=True)
    except OSError as e:
        return "unknown", [f"gh could not run: {e}"]
    if r.returncode != 0:
        return "unknown", ["the ruleset list could not be read (gh missing, not logged in, or the plan doesn't expose it)"]
    return _ok() if r.stdout.strip() else ("fail", ["no ruleset on this repository (branch protection is not counted)"])


def agents_md_budget(repo: Repo) -> Outcome:
    text = repo.read("AGENTS.md")
    if text is None:
        return "skip", ["no AGENTS.md"]
    n = len(text.splitlines())
    return _ok() if n <= AGENTS_MD_BUDGET else ("fail", [f"AGENTS.md is {n} lines (budget {AGENTS_MD_BUDGET})"])


def how_this_was_built(repo: Repo) -> Outcome:
    """Presence of the heading only. Whether the section is accurate is judgment, and this does not judge it."""
    text = repo.read("README.md") or ""
    if re.search(r"^#+\s*how this was built\b", text, re.I | re.M):
        return _ok()
    return "fail", ["README.md has no 'How this was built' section (presence only; accuracy is judgment)"]


def journal_present(repo: Repo) -> Outcome:
    return _ok() if (repo.path / "docs/journal.md").is_file() else ("fail", ["no docs/journal.md"])


def dependency_updates(repo: Repo) -> Outcome:
    names = (".github/dependabot.yml", ".github/dependabot.yaml", "renovate.json", ".renovaterc", ".github/renovate.json")
    return _ok() if any((repo.path / n).is_file() for n in names) else ("fail", ["no Dependabot or Renovate config"])


def _first_file(repo: Repo, names: tuple[str, ...], what: str) -> Outcome:
    return _ok() if any((repo.path / n).is_file() for n in names) else ("fail", [f"no {what}"])


def gitignore_present(repo: Repo) -> Outcome:
    return _first_file(repo, (".gitignore",), ".gitignore")


def templates_present(repo: Repo) -> Outcome:
    names = (".github/pull_request_template.md", "pull_request_template.md", "docs/pull_request_template.md")
    pr = any((repo.path / n).is_file() for n in names)
    issues = (repo.path / ".github/ISSUE_TEMPLATE").is_dir() or (repo.path / ".github/ISSUE_TEMPLATE.md").is_file()
    missing = [n for n, ok in (("pull request template", pr), ("issue template", issues)) if not ok]
    return ("fail", [f"no {n}" for n in missing]) if missing else _ok()


def security_policy(repo: Repo) -> Outcome:
    return _first_file(repo, ("SECURITY.md", ".github/SECURITY.md", "docs/SECURITY.md"), "SECURITY.md")


def contributing_present(repo: Repo) -> Outcome:
    return _first_file(repo, ("CONTRIBUTING.md", ".github/CONTRIBUTING.md", "docs/CONTRIBUTING.md"), "CONTRIBUTING.md")


CHECKS: dict[str, Callable[[Repo], Outcome]] = {
    "pinned-actions": pinned_actions,
    "workflow-permissions": workflow_permissions,
    "no-privileged-triggers": no_privileged_triggers,
    "secret-exposed-workflows": secret_exposed,
    "codeowners-cover-protected-paths": codeowners_cover,
    "no-tracked-secrets": no_tracked_secrets,
    "thin-claude-md": thin_claude_md,
    "one-check-entrypoint": one_check_entrypoint,
    "license-present": license_present,
    "ruleset-present": ruleset_present,
    "agents-md-budget": agents_md_budget,
    "how-this-was-built": how_this_was_built,
    "journal-present": journal_present,
    "dependency-updates": dependency_updates,
    "gitignore-present": gitignore_present,
    "templates-present": templates_present,
    "security-policy": security_policy,
    "contributing-present": contributing_present,
}


def applies(rule: dict, repo: Repo) -> tuple[bool, str]:
    """Whether a rule applies to this repo, and why not. `applies_to: public` needs to know the repo is public."""
    scope = rule.get("applies_to", "all")
    if scope == "all":
        return True, ""
    if repo.public is None:
        return False, f"not in the portfolio, so whether it is {scope} can't be told"
    return (repo.public if scope == "public" else not repo.public), f"rule is for {scope} repos"


def github_public(slug: str | None, gh: Callable) -> bool | None:
    """Whether GitHub says the repo is public. None when it can't be asked or answers something else."""
    if not slug:
        return None
    try:
        r = gh(["gh", "api", f"repos/{slug}", "--jq", ".private"], capture_output=True, text=True)
    except OSError:
        return None
    answer = r.stdout.strip() if r.returncode == 0 else ""
    return {"false": True, "true": False}.get(answer)


def run(repo: Repo, only: list[str] | None = None, rules: dict | None = None) -> list[Result]:
    """Run every rule (or just `only`) and return one Result each, in checks.yaml order."""
    results = []
    for rule in (rules or load_checks())["checks"]:
        if only is not None and rule["id"] not in only:
            continue
        head = {"id": rule["id"], "label": rule["label"], "level": rule["level"]}
        ok, why = applies(rule, repo)
        if not ok:
            results.append(Result(**head, result="skip", findings=[why]))
            continue
        fn = CHECKS.get(rule["id"])
        if fn is None:
            results.append(Result(**head, result="unknown", findings=["no check is implemented for this rule"]))
            continue
        try:
            outcome, findings = fn(repo)
        except Exception as e:  # a broken check must never read as a pass
            outcome, findings = "unknown", [f"check raised {type(e).__name__}: {e}"]
        results.append(Result(**head, result=outcome, findings=findings))
    return results


def exit_code(results: list[Result], strict: bool = False) -> int:
    """1 when a level-`fail` rule fails (or, with strict, can't be answered). Warn-level rules never change the code."""
    for r in results:
        if r.level == "fail" and (r.result == "fail" or (strict and r.result == "unknown")):
            return 1
    return 0


def to_json(name: str, results: list[Result]) -> dict:
    return {"repo": name, "results": [asdict(r) for r in results]}
