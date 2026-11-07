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
PROPOSED_RULES = {"gitignore-present", "templates-present", "security-policy", "contributing-present"}

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
    pawl: bool = False
    restricted: bool = False
    visibility: str = ""  # where `public` came from, shown in the output: it decides which files a repo gets


@dataclass
class Action:
    path: str
    status: str  # create | exists | skip | blocked
    rule: str | None
    note: str = ""
    content: str = ""


@dataclass
class Item:
    path: str
    rule: str | None
    render: Callable[[Ctx], str]
    applies: Callable[[Ctx], tuple[str, str] | None]  # None = applies; else (status, note)
    aliases: tuple[str, ...] = ()  # other names that already satisfy this item (globs allowed)


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
    return Ctx(
        name=name,
        owner=owner,
        public=public,
        ecosystems=detect_ecosystems(path),
        has_workflows=wf.is_dir() and any(wf.glob("*.y*ml")),
        has_check=has_check or _has_ci_list(path),
        autopilot_managed=(path / ".autopilot/manifest.json").is_file(),
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
    if not any(e in t.MAKEFILE for e in ctx.ecosystems):
        return "skip", "no known ecosystem to write a check command for"
    return None


def _make_check(ctx: Ctx) -> str:
    return t.MAKEFILE[next(e for e in ctx.ecosystems if e in t.MAKEFILE)]


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
        lambda c: t.fill(t.CODEOWNERS, owner=c.owner),
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
]


# --- plan and write ----------------------------------------------------------------------------------------------


def _present(root: Path, item: Item) -> bool:
    if (root / item.path).exists():
        return True
    return any(next(root.glob(a), None) is not None if "*" in a else (root / a).exists() for a in item.aliases)


def plan(root: Path, ctx: Ctx, items: list[Item] | None = None) -> list[Action]:
    why = refusal(ctx)
    if why:
        return [Action(i.path, "skip", i.rule, why) for i in (items or ITEMS)]
    out = []
    for item in items or ITEMS:
        if _present(root, item):
            out.append(Action(item.path, "exists", item.rule, "already there; never overwritten"))
            continue
        gate = item.applies(ctx)
        if gate:
            out.append(Action(item.path, gate[0], item.rule, gate[1]))
            continue
        out.append(Action(item.path, "create", item.rule, "missing", item.render(ctx)))
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
        written.append(a.path)
    return written
