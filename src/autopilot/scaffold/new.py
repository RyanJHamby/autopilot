"""`ap new NAME --kind K`: a new local repo that starts on the standard. mkdir, `git init`, the files `ap standard fix` would write.

By default it is local only: no commit, nothing on GitHub, no push; those stay owner steps, printed at the end.
`--create` (owner-run) goes the whole way and cannot stop halfway quietly: signed first commit, `gh repo create --push`, the branch
ruleset, then a read-back of the ruleset from GitHub. If any step fails it says exactly what now exists, and the admin doctor
flags an unprotected repo anyway."""

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path

import yaml

from autopilot.scaffold import core
from autopilot.scaffold import templates as t
from autopilot.standard import engine

NEW_KINDS = ("library", "cli", "app", "notes")
NAME_OK = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def check_name(name: str, owner: str) -> str | None:
    if not NAME_OK.match(name) or name.endswith(".git"):
        return "a repo name is letters, digits, '.', '_' or '-', and starts with a letter or digit"
    if name.lower() == owner.lower():
        return "that is the profile repo's name; its README is the profile, not a project"
    return None


def create(
    root: Path, name: str, kind: str, owner: str, holder: str | None, public: bool, run=subprocess.run
) -> tuple[Path, list[str], list[core.Action]]:
    """Returns (path, files written, plan). Raises ValueError, and leaves nothing behind, if it cannot proceed."""
    why = check_name(name, owner)
    if why:
        raise ValueError(why)
    path = root / name
    if path.exists():
        raise ValueError(
            f"{path} already exists; `ap new` only makes a new directory (use `ap standard fix` on an existing repo)"
        )
    ctx = core.Ctx(name=name, owner=owner, public=public, holder=holder, kind=kind, empty=True, visibility="chosen with ap new")
    ctx.ecosystems = ["uv"] if kind in core.PACKAGE_KINDS else []
    ctx.has_workflows = True  # every kind gets a ci.yml, so dependabot also keeps its action pins fresh
    actions = core.plan(path, ctx)  # path does not exist yet: plan only reads it
    blocked = [a for a in actions if a.status == "blocked"]
    if blocked:
        raise ValueError("; ".join(f"{a.path}: {a.note}" for a in blocked))
    path.mkdir(parents=True)
    try:
        made = run(["git", "-C", str(path), "init", "-q", "-b", "main"], capture_output=True, text=True)
        if made.returncode != 0:
            raise ValueError(f"git init failed: {made.stderr.strip()}")
        written = core.write(path, actions)
        if not (path / "README.md").exists():
            (path / "README.md").write_text(t.readme(name), encoding="utf-8")
            written.append("README.md")
    except BaseException:
        import shutil

        shutil.rmtree(path, ignore_errors=True)
        raise
    return path, sorted(written), actions


class PublishError(Exception):
    """A --create step failed. The message says what now exists and what to run."""


def workflow_jobs(path: Path) -> set[str]:
    wf = path / ".github" / "workflows" / "ci.yml"
    try:
        doc = yaml.safe_load(wf.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return set()
    return set((doc.get("jobs") or {}).keys())


def publish(path: Path, name: str, owner: str, kind: str, public: bool, *, run=subprocess.run, say=print) -> str:
    """Commit (signed), create the GitHub repo, push, apply the ruleset and read it back. Returns the repo slug.

    Everything that can be checked before touching GitHub is checked first, so the usual failures leave nothing outward behind."""
    from autopilot import cli  # lazy: cli imports this module lazily too

    slug = f"{owner}/{name}"
    check = core.required_check(kind)

    def sh(*cmd: str) -> subprocess.CompletedProcess:
        return run(list(cmd), capture_output=True, text=True)

    # --- before anything outward ---
    if check not in workflow_jobs(path):
        raise PublishError(
            f"the ruleset would require check {check!r} but ci.yml has jobs {sorted(workflow_jobs(path)) or 'none'}: "
            "a required check that never reports blocks every merge. Nothing was committed or created."
        )
    gpgsign = sh("git", "-C", str(path), "config", "--get", "commit.gpgsign").stdout.strip()
    key = sh("git", "-C", str(path), "config", "--get", "user.signingkey").stdout.strip()
    if gpgsign != "true" or not key:
        raise PublishError("commit signing is not on (commit.gpgsign=true and user.signingkey): refusing to make an unsigned first commit. Nothing was created.")

    # --- local ---
    for cmd in (["git", "-C", str(path), "add", "-A"], ["git", "-C", str(path), "commit", "-S", "-q", "-m", "Start on the standard"]):
        r = sh(*cmd)
        if r.returncode != 0:
            raise PublishError(f"`{' '.join(cmd[3:])}` failed: {(r.stderr or r.stdout).strip()[:200]}. Nothing is on GitHub.")
    say("  signed first commit made")

    # --- outward ---
    vis = "--public" if public else "--private"
    r = sh("gh", "repo", "create", slug, vis, "--source", str(path), "--remote", "origin", "--push")
    if r.returncode != 0:
        raise PublishError(
            f"`gh repo create {slug}` failed: {(r.stderr or r.stdout).strip()[:200]}. "
            f"Check github.com/{slug}: if it exists, finish with `ap ruleset {slug} --standalone --check {check} --apply`."
        )
    say(f"  created {slug} ({vis[2:]}) and pushed main")
    rc, text = cli.apply_ruleset(slug, [check], run=run)
    unprotected = (
        f"{slug} EXISTS BUT IS UNPROTECTED. Fix: `ap ruleset {slug} --standalone --check {check} --apply`. "
        "On a free GitHub plan, rulesets are not available on private repos (the admin doctor will go red for it after 7 days)."
    )
    if rc != 0:
        raise PublishError(f"applying the ruleset failed: {text.strip()[:200]}. {unprotected}")
    say("  ruleset applied")
    problems = cli.verify_ruleset(slug, [check], run=run)
    if problems:
        raise PublishError("the ruleset did not read back as asked: " + "; ".join(problems) + ". " + unprotected)
    say(f"  ruleset read back from GitHub: signed commits, no force-push or deletion, a PR, required check {check!r}")
    return slug


def next_steps(name: str, owner: str, public: bool) -> list[str]:
    vis = "--public" if public else "--private"
    return [
        f"cd {name} && pow init",
        "git add -A && git commit -S -m 'Start on the standard'   (signed, by you)",
        f"gh repo create {owner}/{name} {vis} --source . --push   (outward-facing: yours to run)",
        f"add {name} to policy/portfolio.yaml if autopilot should manage it, and set the ruleset",
    ]


def cmd_new(ns: argparse.Namespace, *, load_portfolio, run=subprocess.run) -> int:
    portfolio = load_portfolio()
    owner = ns.owner or portfolio["owner"]
    holder = ns.holder or portfolio.get("holder")
    try:
        path, written, _ = create(Path(ns.root).expanduser(), ns.name, ns.kind, owner, holder, bool(ns.public), run=run)
    except ValueError as e:
        print(f"ERROR {e}")
        return 1
    for p in written:
        print(f"  wrote {p}")
    if getattr(ns, "create", False):
        try:
            slug = publish(path, ns.name, owner, ns.kind, bool(ns.public), run=run)
        except PublishError as e:
            print(f"ERROR {e}")
            print(f"{path} is kept as it is.")
            return 1
        print(f"{slug} is created, pushed and protected. Your remaining steps:")
        print(f"  1. cd {path} && pow init")
        print(f"  2. add {ns.name} to policy/portfolio.yaml if autopilot should manage it (a protected path: yours to edit)")
        print("  The admin doctor discovers the repo from GitHub; nothing needs registering for it to be audited.")
        return 0
    results = engine.run(engine.Repo(path, github_public=bool(ns.public)))
    todo = [f"{r.id}: {'; '.join(r.findings)}" for r in results if r.result == "fail"]
    print(f"{path}: {len(written)} file(s), git initialised on main, nothing committed.")
    if todo:
        print("Still failing the standard (expected until the steps below):")
        for line in todo:
            print(f"  - {line}")
    print("Your steps (nothing outward-facing was done):")
    for i, s in enumerate(next_steps(ns.name, owner, bool(ns.public)), 1):
        print(f"  {i}. {s}")
    return 0
