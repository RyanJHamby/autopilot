"""Plan which standard files a repo is missing, and write them only on request. Never overwrites, never commits.

`plan` is pure: it reads the repo and returns Actions. `write` is the only function that touches disk."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from autopilot.scaffold import templates as t

# Rules the scaffolder serves that are not in checks.yaml yet: adding a rule needs an owner edit (src/autopilot/standard/**
# is protected). Moving an id out of this set and into checks.yaml is part of that owner change.
PROPOSED_RULES = {"gitignore-present", "templates-present", "security-policy", "contributing-present", "commands-documented"}

KINDS = ("library", "cli", "app", "site", "notes", "research", "fork")
PACKAGE_KINDS = ("library", "cli")  # kinds that publish a package and so get a changelog


@dataclass
class Ctx:
    name: str
    owner: str
    public: bool | None  # None = nobody could say
    holder: str | None = None
    kind: str | None = None
    year: int = field(default_factory=lambda: date.today().year)
    ecosystems: list[str] = field(default_factory=list)
    has_workflows: bool = False
    has_check: bool = False  # a Makefile `check:` target or a `ci:` list already exists
    autopilot_managed: bool = False  # `ap init` owns CODEOWNERS, templates and workflows here
    has_commands: bool = False  # AGENTS.md already has a `## Commands` section
    pawl: bool = False
    restricted: bool = False
    empty: bool = False  # nothing in the directory but .git: the only case where a skeleton is written
    visibility: str = ""  # where `public` came from, shown in the output: it decides which files a repo gets


@dataclass
class Action:
    path: str
    status: str  # create | exists | skip | blocked
    rule: str | None
    note: str = ""
    content: str = ""
    mode: int | None = None  # applied only to a file this run creates (a git hook must be executable)


@dataclass
class Item:
    path: str
    rule: str | None
    render: Callable[[Ctx], str]
    applies: Callable[[Ctx], tuple[str, str] | None]  # None = applies; else (status, note)
    aliases: tuple[str, ...] = ()  # other names that already satisfy this item (globs allowed)
    mode: int | None = None  # e.g. 0o755 for a hook; None leaves the default


def detect_ecosystems(path: Path) -> list[str]:
    """Dependabot `package-ecosystem` names for the manifests found at the repo root."""
    eco = []
    if (path / "uv.lock").is_file():
        eco.append("uv")
    elif (path / "pyproject.toml").is_file() or (path / "requirements.txt").is_file():
        eco.append("pip")
    if (path / "package.json").is_file():
        eco.append("npm")
    if (path / "Cargo.toml").is_file():
        eco.append("cargo")
    if (path / "go.mod").is_file():
        eco.append("gomod")
    if (path / "Dockerfile").is_file():
        eco.append("docker")
    return eco


def read_ctx(path: Path, name: str, owner: str, public: bool | None, **extra) -> Ctx:
    """Everything about the checkout itself. Portfolio facts (holder, kind, data_class) come in through `extra`."""
    wf = path / ".github/workflows"
    makefile = path / "Makefile"
    has_check = makefile.is_file() and bool(re.search(r"^check\s*:", makefile.read_text(errors="replace"), re.M))
    agents = path / "AGENTS.md"
    has_commands = agents.is_file() and bool(re.search(r"^## Commands\b", agents.read_text(errors="replace"), re.M))
    empty = not any(p.name != ".git" for p in path.iterdir())
    kind = extra.get("kind")
    return Ctx(
        name=name,
        owner=owner,
        public=public,
        empty=empty,
        # a new Python package will be a uv project, so the files that depend on that are planned with it
        ecosystems=["uv"] if empty and kind in PACKAGE_KINDS else detect_ecosystems(path),
        has_workflows=wf.is_dir() and any(wf.glob("*.y*ml")),
        has_check=has_check or _has_ci_list(path),
        autopilot_managed=(path / ".autopilot/manifest.json").is_file(),
        has_commands=has_commands,
        pawl=(path / "policy/lanes.toml").is_file(),
        **extra,
    )


def _has_ci_list(path: Path) -> bool:
    cfg = path / ".autopilot/repo.yaml"
    return cfg.is_file() and bool(re.search(r"^ci\s*:", cfg.read_text(errors="replace"), re.M))


def refusal(ctx: Ctx) -> str | None:
    """Why this repo must not be scaffolded at all, or None."""
    if ctx.pawl:
        return "pawl-scaffolded repo (policy/lanes.toml): a repo is autopilot or pawl, never both"
    if ctx.restricted:
        return "data_class is restricted: nothing is written into it"
    if ctx.kind == "fork":
        return "an upstream fork: its files are not ours to scaffold"
    if ctx.name.lower() == ctx.owner.lower():
        return "the profile repo: its README is the profile, not a project"
    return None


# --- applicability -----------------------------------------------------------------------------------------------


def _public_only(ctx: Ctx) -> tuple[str, str] | None:
    if ctx.public is None:
        return "blocked", "cannot tell whether the repo is public (GitHub could not be asked and the portfolio has no entry)"
    return None if ctx.public else ("skip", "private repo")


def _license(ctx: Ctx) -> tuple[str, str] | None:
    gate = _public_only(ctx)
    if gate:
        return gate
    if not ctx.holder:
        return "blocked", "no holder: pass --holder or set `holder:` in policy/portfolio.yaml (a legal name is never guessed)"
    return None


def _unmanaged(ctx: Ctx) -> tuple[str, str] | None:
    return ("skip", "owned by `ap init` in this repo") if ctx.autopilot_managed else None


def _dependabot(ctx: Ctx) -> tuple[str, str] | None:
    if not ctx.ecosystems and not ctx.has_workflows:
        return "skip", "no manifests or workflows to keep updated"
    return None


def _changelog(ctx: Ctx) -> tuple[str, str] | None:
    return None if ctx.kind in PACKAGE_KINDS else ("skip", f"kind is {ctx.kind or 'unset'}, not a package")


def _makefile(ctx: Ctx) -> tuple[str, str] | None:
    if ctx.has_check:
        return "skip", "a check entrypoint already exists"
    if _generic_new(ctx):
        return None
    if not any(e in t.MAKEFILE for e in ctx.ecosystems):
        return "skip", "no known ecosystem to write a check command for"
    return None


def _justfile(ctx: Ctx) -> tuple[str, str] | None:
    if ctx.has_commands:
        return "skip", "AGENTS.md already has a ## Commands section"
    if not any(e in t.JUSTFILE for e in ctx.ecosystems):
        return "skip", "no known ecosystem to write commands for"
    return None


def _uv_only(ctx: Ctx) -> tuple[str, str] | None:
    return None if "uv" in ctx.ecosystems else ("skip", "only uv projects have a workflow template so far")


def _generic_new(ctx: Ctx) -> bool:
    """A brand-new repo with no package. It gets a generic `make check` and a CI job that runs it, so a ruleset has a status check
    to require. An existing repo, and the template (used for repos of every kind), are left alone: their CI is their owner's."""
    return ctx.empty and not ctx.ecosystems


def _ci(ctx: Ctx) -> tuple[str, str] | None:
    skip = _unmanaged(ctx)
    if skip or "uv" in ctx.ecosystems:
        return skip
    return None if _generic_new(ctx) else _uv_only(ctx)


def required_check(kind: str | None) -> str:
    """The CI job id a new repo's ruleset requires. It must be a job in the workflow `ap new` writes; a test pins that, because a
    required check that never reports blocks every merge."""
    return "test" if kind in PACKAGE_KINDS else "check"


def _release(ctx: Ctx) -> tuple[str, str] | None:
    if ctx.kind not in PACKAGE_KINDS:
        return "skip", f"kind is {ctx.kind or 'unset'}, not a package"
    return _public_only(ctx) or _uv_only(ctx)


def package_name(ctx: Ctx) -> str:
    """Import name: the repo name with anything that is not a letter, digit or underscore turned into `_`."""
    return re.sub(r"\W+", "_", ctx.name).strip("_").lower()


def _skeleton(ctx: Ctx) -> tuple[str, str] | None:
    return None if ctx.empty and ctx.kind in PACKAGE_KINDS else ("skip", "skeletons go only into an empty directory")


SKELETON: list[Item] = [
    Item(
        "pyproject.toml",
        None,
        lambda c: t.pyproject(c.name, package_name(c), c.owner, c.holder, bool(c.public), c.kind == "cli"),
        _skeleton,
    ),
    Item("README.md", None, lambda c: t.readme(c.name), _skeleton),
    Item("src/@pkg@/__init__.py", None, lambda c: t.init_py(c.kind == "cli"), _skeleton),
    Item("src/@pkg@/py.typed", None, lambda c: "", _skeleton),
    Item("tests/test_smoke.py", None, lambda c: t.smoke_test(package_name(c)), _skeleton),
]


def layout_notes(root: Path, ctx: Ctx) -> list[str]:
    """Advisory drift for a populated package repo. Nothing is moved, renamed or written."""
    if ctx.empty or ctx.kind not in PACKAGE_KINDS or refusal(ctx):
        return []
    notes = []
    if not (root / "tests").is_dir() and any(root.glob("test_*.py")):
        notes.append("tests sit at the repo root; the convention is a `tests/` directory")
    if not (root / "src").is_dir() and (root / "pyproject.toml").is_file():
        notes.append("no `src/` directory; the convention is `src/<package>/`")
    if not (root / "docs").is_dir():
        notes.append("no `docs/` directory")
    return notes


def _new_repo_only(ctx: Ctx) -> tuple[str, str] | None:
    """The day-0 layer goes only into a brand-new repo. In an existing one a hook or a `setup` target would point at files that are
    not there, and a new convention is theirs to adopt at retrofit, not something a routine fix should drop in."""
    return None if ctx.empty else ("skip", "day-0 files go only into a new repo; an existing repo adopts them at retrofit")


def _make_check(ctx: Ctx) -> str:
    if ctx.empty and "uv" in ctx.ecosystems:
        return t.makefile_new(lint="uv run ruff check .", test="uv run pytest -q", audit="uv audit")
    if _generic_new(ctx):
        return t.makefile_new()
    return t.MAKEFILE[next(e for e in ctx.ecosystems if e in t.MAKEFILE)]


def _just_commands(ctx: Ctx) -> str:
    return t.JUSTFILE[next(e for e in ctx.ecosystems if e in t.JUSTFILE)]


ITEMS: list[Item] = [
    Item(
        "LICENSE",
        "license-present",
        lambda c: t.fill(t.MIT, year=c.year, holder=c.holder),
        _license,
        ("LICENSE.md", "LICENSE.txt", "COPYING"),
    ),
    Item("SECURITY.md", "security-policy", lambda c: t.SECURITY, _public_only, (".github/SECURITY.md", "docs/SECURITY.md")),
    Item(
        "CONTRIBUTING.md",
        "contributing-present",
        lambda c: t.CONTRIBUTING,
        _public_only,
        (".github/CONTRIBUTING.md", "docs/CONTRIBUTING.md"),
    ),
    Item(
        ".github/dependabot.yml",
        "dependency-updates",
        lambda c: t.dependabot(c.ecosystems, c.has_workflows),
        _dependabot,
        (".github/dependabot.yaml", "renovate.json", ".renovaterc", ".github/renovate.json"),
    ),
    Item(".gitignore", "gitignore-present", lambda c: t.gitignore(c.ecosystems), lambda c: None),
    Item(
        ".github/CODEOWNERS",
        "codeowners-cover-protected-paths",
        lambda c: t.fill(t.CODEOWNERS, handle=f"@{c.owner}"),
        _unmanaged,
        ("CODEOWNERS", "docs/CODEOWNERS"),
    ),
    Item(
        ".github/pull_request_template.md",
        "templates-present",
        lambda c: t.PULL_REQUEST,
        _unmanaged,
        ("pull_request_template.md", "docs/pull_request_template.md"),
    ),
    Item(".github/ISSUE_TEMPLATE/bug.md", "templates-present", lambda c: t.ISSUE_BUG, _unmanaged, (".github/ISSUE_TEMPLATE/*",)),
    Item("CHANGELOG.md", None, lambda c: t.CHANGELOG, _changelog),
    Item("Makefile", "one-check-entrypoint", _make_check, _makefile),
    # Day-0 layer, new repos only. The hook is executable because git silently ignores one that is not.
    Item(".githooks/pre-commit", None, lambda c: t.HOOK_PRE_COMMIT, _new_repo_only, mode=0o755),
    Item(".editorconfig", None, lambda c: t.EDITORCONFIG, _new_repo_only),
    Item(".gitattributes", None, lambda c: t.GITATTRIBUTES, _new_repo_only),
    Item("docs/decisions/README.md", None, lambda c: t.DECISIONS_README, _new_repo_only),
    Item("docs/runbooks/README.md", None, lambda c: t.RUNBOOKS_README, _new_repo_only),
    Item("docs/postmortems/TEMPLATE.md", None, lambda c: t.POSTMORTEM_TEMPLATE, _new_repo_only),
    Item("justfile", "commands-documented", _just_commands, _justfile, ("Justfile",)),
    # Any existing workflow counts as CI: a second competing ci.yml is worse than none.
    Item(
        ".github/workflows/ci.yml",
        "pinned-actions",
        lambda c: t.CI_UV if "uv" in c.ecosystems else t.CI_GENERIC,
        _ci,
        (".github/workflows/*.y*ml",),
    ),
    Item(
        ".github/workflows/release.yml",
        "pinned-actions",
        lambda c: t.RELEASE_UV,
        _release,
        (".github/workflows/release*.y*ml", ".github/workflows/publish*.y*ml"),
    ),
]


# --- plan and write ----------------------------------------------------------------------------------------------


def _present(root: Path, item: Item) -> bool:
    if (root / item.path).exists():
        return True
    return any(next(root.glob(a), None) is not None if "*" in a else (root / a).exists() for a in item.aliases)


def _resolve(item: Item, ctx: Ctx) -> Item:
    """Fill the `@pkg@` placeholder in a skeleton path."""
    if "@pkg@" not in item.path:
        return item
    return Item(item.path.replace("@pkg@", package_name(ctx)), item.rule, item.render, item.applies, item.aliases, item.mode)


def plan(root: Path, ctx: Ctx, items: list[Item] | None = None) -> list[Action]:
    why = refusal(ctx)
    if why:
        return [Action(i.path, "skip", i.rule, why) for i in (items or ITEMS)]
    out = []
    chosen = list(items or ITEMS)
    if items is None and ctx.empty and ctx.kind in PACKAGE_KINDS:
        chosen += SKELETON
    for item in chosen:
        item = _resolve(item, ctx)
        if _present(root, item):
            out.append(Action(item.path, "exists", item.rule, "already there; never overwritten"))
            continue
        gate = item.applies(ctx)
        if gate:
            out.append(Action(item.path, gate[0], item.rule, gate[1]))
            continue
        out.append(Action(item.path, "create", item.rule, "missing", item.render(ctx), item.mode))
    return out


def write(root: Path, actions: list[Action]) -> list[str]:
    """Create the files `plan` said to create. Exclusive-create, so a file that appeared meanwhile is never touched."""
    written = []
    for a in actions:
        if a.status != "create":
            continue
        target = root / a.path
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(target, "x", encoding="utf-8") as f:
                f.write(a.content)
        except FileExistsError:
            a.status, a.note = "exists", "appeared while writing; left alone"
            continue
        if a.mode is not None:
            target.chmod(a.mode)  # only after our own exclusive create, so a file that was already there is never touched
        written.append(a.path)
    return written
