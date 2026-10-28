"""`ap`: scaffold, audit and steer autopilot across repos.

Local-only unless a command says otherwise. Anything that changes GitHub (`enable`, `pause`,
`ruleset`) needs an explicit --apply; without it the command prints what it would do.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
KIT = ROOT / "kit"
POLICY = ROOT / "policy"
VERSION = "0.1.0"
BEGIN, END = "<!-- autopilot:begin -->", "<!-- autopilot:end -->"
CHECKOUT_SHA = "11d5960a326750d5838078e36cf38b85af677262"  # actions/checkout v4
SETUP_NODE_SHA = "49933ea5288caeca8642d1e84afbd3f7d6820020"  # actions/setup-node v4.4.0
ACTION_SHA = "34968b5981d5d170904281aa3df6f3c0d4a28855"  # anthropics/claude-code-action v1


def _load_runtime(name: str):
    import importlib.util

    spec = importlib.util.spec_from_file_location(f"kit_{name}", KIT / "runtime" / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _runtime_config():
    import importlib.util

    spec = importlib.util.spec_from_file_location("kit_config", KIT / "runtime" / "config.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


BASE_TOOLS = _runtime_config().BASE_TOOLS  # single source: the kit's runtime/config.py
RETIRED = {
    "Write(.github/**)",
    "Write(.autopilot/**)",
    "Write(.claude/**)",
    "Write(AGENTS.md)",
    "Write(CLAUDE.md)",
    "Write(.mcp.json)",
    "mcp__*",
    "Bash(git checkout -b agent/*)",
    "Bash(git commit:*)",
    "Bash(git push origin agent/*)",
}  # kit-owned rules removed from synced repos
STACKS = {  # marker file -> command prefixes
    "pyproject.toml": ["uv run", "uv sync", "pytest", "ruff", "python"],
    "package.json": ["npm test", "npm run"],  # no npx/pnpm: they fetch and run arbitrary registry code
    "Cargo.toml": ["cargo"],
    "pubspec.yaml": ["flutter test", "flutter analyze", "dart"],
    "Makefile": ["make"],
    "CMakeLists.txt": ["cmake", "ctest", "make"],
    "go.mod": ["go test", "go build", "go vet"],
}
RUNTIME_FILES = ["guard.py", "handshake.py", "gate.py", "tier.py"]


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_portfolio() -> dict:
    return yaml.safe_load((POLICY / "portfolio.yaml").read_text())


SKIP_DIRS = {".git", "node_modules", "build", "target", ".venv", "venv", "dist"}


SENSITIVE_DIRS = {".obsidian", ".gnupg", ".ssh", ".aws"}
SENSITIVE_STEMS = {
    "journal", "journals", "diary", "therapy", "medical", "health", "labs", "lab-results", "taxes", "tax", "passwords",
    "password", "secrets", "secret", "credentials", "id_rsa", "id_ed25519",
}  # fmt: skip
SENSITIVE_EXTS = {".asc", ".gpg", ".pem", ".p12", ".pfx", ".kdbx"}


def _sensitive_name(rel: str) -> bool:
    """Whole file stems only ('journal.md', 'secrets.json'), never substrings: 'health-checker.py' or a lesson called
    'secrets-and-key-management.md' is ordinary content. Dated journals ('journal-2026-10.md') still match."""
    base = Path(rel).name.lower()
    if base == ".env" or base.startswith(".env."):
        return not base.endswith((".example", ".sample"))
    stem = base.split(".")[0]
    if Path(base).suffix in SENSITIVE_EXTS:
        return True
    return stem in SENSITIVE_STEMS or bool(re.fullmatch(r"(journal|diary)[-_ ]?[\d-]+", stem))


def sensitive_findings(repo: Path, *, never_paths: list[str] | None = None, limit: int = 12) -> list[str]:
    """Why this clone should NOT be handed to a cloud agent: personal notes, key material, secrets, or a path the owner
    declared off-limits. Names only; file contents are never read."""
    found: list[str] = []
    here = str(repo.resolve())
    for np_ in never_paths or []:
        base = str(Path(np_).expanduser().resolve())
        if here == base or here.startswith(base + "/"):
            found.append(f"inside off-limits path {np_}")
    for root, dirs, files in os.walk(repo):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for d in list(dirs):
            if d in SENSITIVE_DIRS:
                found.append(f"{Path(root, d).relative_to(repo)}/ (personal/key directory)")
                dirs.remove(d)
        for f in files:
            rel = str(Path(root, f).relative_to(repo))
            if _sensitive_name(rel):
                found.append(rel)
        if len(found) >= limit:
            break
    return found[:limit]


AUTOPILOT_WORKFLOWS = {
    "agent-dispatch.yml",
    "agent-exec.yml",
    "guard.yml",
    "handshake.yml",
    "automerge.yml",
    "improve.yml",
    "audit.yml",
}


def secret_exposed_workflows(repo: Path) -> list[str]:
    """Host workflows that hand repo secrets to code from a PR branch (so an agent PR could read or spend them)
    and do not exclude agent/* branches. GITHUB_TOKEN does not count."""
    out: list[str] = []
    for wf in sorted((repo / ".github/workflows").glob("*.y*ml")):
        if wf.name in AUTOPILOT_WORKFLOWS:
            continue
        text = wf.read_text()
        uses_secret = any(s != "GITHUB_TOKEN" for s in re.findall(r"secrets\.([A-Za-z0-9_]+)", text))
        on_pr = re.search(r"^\s*pull_request(_target)?\s*:", text, re.M) is not None
        if uses_secret and on_pr and "agent/" not in text:
            out.append(wf.name)
    return out


def setup_steps(repo: Path) -> str:
    """Trusted workflow steps that prepare the agent's runner (before the model starts, outside its control)."""
    if not (repo / "package-lock.json").exists():
        return ""
    ver = "20"
    nvmrc = repo / ".nvmrc"
    if nvmrc.exists():
        m = re.search(r"\d+", nvmrc.read_text())
        ver = m.group(0) if m else ver
    return (
        f"      - uses: actions/setup-node@{SETUP_NODE_SHA} # v4\n"
        f'        with:\n          node-version: "{ver}"\n          cache: npm\n'
        "      - name: install dependencies (trusted step; install scripts disabled)\n"
        "        run: npm ci --ignore-scripts\n"
    )


def detect_commands(repo: Path) -> list[str]:
    """Command prefixes for the stacks found at the repo root or one directory down, plus any the owner
    listed under `commands:` in .autopilot/repo.yaml (so that file is the single place to extend them)."""
    cmds: list[str] = []
    subdirs = [d for d in sorted(repo.iterdir()) if d.is_dir() and d.name not in SKIP_DIRS and not d.name.startswith(".")]
    for marker, prefixes in STACKS.items():
        if (repo / marker).exists() or any((d / marker).exists() for d in subdirs):
            cmds += [p for p in prefixes if p not in cmds]
    cfg = repo / ".autopilot" / "repo.yaml"
    if cfg.exists():
        extra = (yaml.safe_load(cfg.read_text()) or {}).get("commands") or []
        cmds += [str(e) for e in extra if str(e) not in cmds]
    return cmds


def render(text: str, subs: dict[str, str]) -> str:
    for k, v in subs.items():
        text = text.replace("{{" + k + "}}", v)
    return text


def build_settings(existing: dict | None, commands: list[str], extra_protected: list[str] | None = None) -> dict:
    deny = json.loads((POLICY / "deny.json").read_text())["permissions"]["deny"]
    s = dict(existing or {})
    s.setdefault("$schema", "https://json.schemastore.org/claude-code-settings.json")
    perms = dict(s.get("permissions", {}))
    extra = {f"Edit({p})" for p in (extra_protected or [])}
    perms["deny"] = sorted((set(perms.get("deny", [])) | set(deny) | extra) - RETIRED)
    allow = set(perms.get("allow", [])) | set(BASE_TOOLS) | {f"Bash({c}:*)" for c in commands}
    perms["allow"] = sorted(allow - RETIRED)
    s["permissions"] = perms
    return s


def _extra_protected(repo: Path) -> list[str]:
    """guard.extra_protected from the repo's own (owner-edited) .autopilot/repo.yaml, validated as plain path globs."""
    cfg = repo / ".autopilot" / "repo.yaml"
    if not cfg.exists():
        return []
    raw = ((yaml.safe_load(cfg.read_text()) or {}).get("guard") or {}).get("extra_protected") or []
    return [p for p in raw if isinstance(p, str) and re.fullmatch(r"[\w./*-]+", p)]


CO_BEGIN, CO_END = "# BEGIN autopilot", "# END autopilot"
MERGED_FILES = {".claude/settings.json", ".github/CODEOWNERS"}  # merged into what is there; every other existing file is kept


def codeowners(owner: str, existing: str | None = None, extra_protected: list[str] | None = None) -> str:
    """CODEOWNERS with a managed block for the protected paths. Anything already in the file is kept."""
    paths = [".github/", ".autopilot/", ".claude/", "AGENTS.md", "CLAUDE.md", ".mcp.json"]
    paths += [
        p.removesuffix("**") for p in (extra_protected or [])
    ]  # the repo's own guard path (repo.yaml guard.extra_protected)
    lines = [f"/{p} @{owner}" for p in paths]
    block = f"{CO_BEGIN} (managed: protected paths)\n" + "\n".join(lines) + f"\n{CO_END}\n"
    if not existing:
        return block
    if CO_BEGIN in existing and CO_END in existing:
        a, b = existing.index(CO_BEGIN), existing.index(CO_END) + len(CO_END)
        return existing[:a] + block.rstrip("\n") + existing[b:]
    return existing.rstrip("\n") + "\n\n" + block


def init_repo(repo: Path, tier: str, mode: str, *, dry_run: bool = False, central: tuple[str, str] | None = None) -> list[str]:
    """Write the scaffold into a local clone. Returns the list of paths written/changed.

    central=(kit_repo, kit_sha): write thin callers into the pinned shared kit instead of copying the workflows and
    the guard/gate/handshake scripts into the repo."""
    pf = load_portfolio()
    owner = pf["owner"]
    commands = detect_commands(repo)
    subs = {
        "CHECKOUT_SHA": CHECKOUT_SHA,
        "ACTION_SHA": ACTION_SHA,
        "OWNER": owner,
        "TIER": tier,
        "MODE": mode,
        "SETUP_STEPS": setup_steps(repo),
        "COMMANDS": "\n".join(f'  - "{c}"' for c in commands) or "  []",
        "ALLOWED_TOOLS": ",".join(BASE_TOOLS + [f"Bash({c}:*)" for c in commands]),
    }
    out: dict[str, str] = {}
    if central:
        subs.update({"KIT_REPO": central[0], "KIT_SHA": central[1]})
        wf_dir = KIT / "callers"
    else:
        wf_dir = KIT / "repo" / ".github" / "workflows"
    for f in wf_dir.glob("*.yml"):
        out[f".github/workflows/{f.name}"] = render(f.read_text(), subs)
    for f in (KIT / "repo" / ".github" / "ISSUE_TEMPLATE").glob("*.md"):
        out[f".github/ISSUE_TEMPLATE/{f.name}"] = f.read_text()
    out[".github/pull_request_template.md"] = (KIT / "repo/.github/pull_request_template.md").read_text()
    extra = _extra_protected(repo)
    co = repo / ".github" / "CODEOWNERS"
    out[".github/CODEOWNERS"] = codeowners(owner, co.read_text() if co.exists() else None, extra)
    out["specs/_TEMPLATE.md"] = (KIT / "repo/specs/_TEMPLATE.md").read_text()
    out[".autopilot/CONSTITUTION.md"] = (POLICY / "CONSTITUTION.md").read_text()
    out[".autopilot/CONTRACT.md"] = (KIT / "contract/CONTRACT.md").read_text()
    if not central:
        for name in RUNTIME_FILES:
            out[f".autopilot/{name}"] = (KIT / "runtime" / name).read_text()
    for f in (KIT / "agents").glob("*.md"):
        out[f".claude/agents/{f.name}"] = f.read_text()
    out[".claude/settings.json"] = None  # merged below

    written: list[str] = []
    manifest_path = repo / ".autopilot" / "manifest.json"
    old_manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {"files": {}}
    manifest = {"kit_version": VERSION, "files": {}}

    def put(rel: str, content: str, *, user_owned: bool = False) -> None:
        p = repo / rel
        if user_owned and p.exists():
            return
        if p.exists() and rel not in MERGED_FILES and rel not in old_manifest["files"]:
            print(f"  ! {rel} already exists and is not autopilot's; leaving it as is", file=sys.stderr)
            return
        if p.exists() and p.read_text() == content:
            manifest["files"][rel] = _sha(content.encode())
            return
        prev = old_manifest["files"].get(rel)
        if p.exists() and prev and _sha(p.read_bytes()) != prev:
            print(f"  ! {rel} was edited by hand since last install; leaving it (diff vs kit by hand)", file=sys.stderr)
            return
        written.append(rel)
        manifest["files"][rel] = _sha(content.encode())
        if not dry_run:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content)

    if central:  # migrating from copy mode: drop vendored scripts we installed and nobody edited
        for name in RUNTIME_FILES:
            rel = f".autopilot/{name}"
            p = repo / rel
            if p.exists() and old_manifest["files"].get(rel) == _sha(p.read_bytes()):
                written.append(f"{rel} (removed)")
                if not dry_run:
                    p.unlink()

    settings_path = repo / ".claude" / "settings.json"
    existing = json.loads(settings_path.read_text()) if settings_path.exists() else None
    out[".claude/settings.json"] = json.dumps(build_settings(existing, commands, extra), indent=2) + "\n"
    for rel, content in out.items():
        put(rel, content)
    put(".autopilot/repo.yaml", render((KIT / "repo/.autopilot/repo.yaml.tmpl").read_text(), subs), user_owned=True)
    put(".autopilot/merge-policy.yaml", (KIT / "repo/.autopilot/merge-policy.yaml.tmpl").read_text(), user_owned=True)

    # AGENTS.md managed block + CLAUDE.md import
    block = f"{BEGIN}\n{(KIT / 'repo/AGENTS.block.md').read_text().rstrip()}\n{END}\n"
    agents = repo / "AGENTS.md"
    cur = agents.read_text() if agents.exists() else "# Working agreement for AI agents in this repo\n\n"
    if BEGIN in cur and END in cur:
        pre, rest = cur.split(BEGIN, 1)
        _, post = rest.split(END, 1)
        new = pre + block.rstrip("\n") + post
    else:
        new = cur.rstrip("\n") + "\n\n" + block
    if new != cur:
        written.append("AGENTS.md")
        if not dry_run:
            agents.write_text(new)
    claude_md = repo / "CLAUDE.md"
    if not claude_md.exists():
        written.append("CLAUDE.md")
        if not dry_run:
            claude_md.write_text("@AGENTS.md\n")
    if not dry_run:
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return written


def _run(*args: str, cwd: Path | None = None, check: bool = True) -> str:
    r = subprocess.run(list(args), cwd=cwd, capture_output=True, text=True, check=check)
    return r.stdout.strip()


def repo_name(repo: Path) -> str:
    """GitHub repo name from origin (dir names can differ, e.g. ~/dev/drillpad is drillpad-workspace)."""
    r = subprocess.run(["git", "remote", "get-url", "origin"], cwd=repo, capture_output=True, text=True)
    url = r.stdout.strip()
    if r.returncode == 0 and url:
        return url.rstrip("/").removesuffix(".git").rsplit("/", 1)[-1].rsplit(":", 1)[-1]
    return repo.name


def cmd_init(ns: argparse.Namespace) -> int:
    repo = Path(ns.repo).expanduser().resolve()
    if not (repo / ".git").exists():
        print(f"{repo} is not a git clone", file=sys.stderr)
        return 1
    pf = load_portfolio()
    name = repo_name(repo)
    if name in pf.get("excluded", []):
        print(f"{name} is excluded in policy/portfolio.yaml (fork or sunset project); refusing", file=sys.stderr)
        return 1
    entry = pf["repos"].get(name, {})
    if entry.get("data_class") == "restricted":
        print(f"{name} is data_class: restricted (crown-jewel IP or personal data): no cloud agents. Refusing.", file=sys.stderr)
        return 1
    bad = sensitive_findings(repo, never_paths=pf.get("never_paths", []))
    if bad and not ns.allow_sensitive:
        print(
            f"{name}: looks like it holds personal or secret material; refusing to scaffold a cloud agent here:", file=sys.stderr
        )
        for b in bad:
            print(f"  - {b}", file=sys.stderr)
        print(
            "Move that material out (or list the repo as data_class: restricted). To override: --allow-sensitive", file=sys.stderr
        )
        return 1
    tier = ns.tier or entry.get("tier")
    mode = ns.mode or entry.get("mode")
    if not tier or not mode:
        print(f"{name} is not in portfolio.yaml; pass --tier A|B|C and --mode standard|yolo|dormant", file=sys.stderr)
        return 1
    if not ns.dry_run:
        if _run("git", "status", "--porcelain", cwd=repo):
            print("working tree is not clean; commit or stash first", file=sys.stderr)
            return 1
        _run("git", "checkout", "-B", "autopilot/init", cwd=repo)
    central = None
    if ns.kit:
        m = re.fullmatch(r"([\w.-]+/[\w.-]+)@([0-9a-f]{40})", ns.kit)
        if not m:
            print("--kit must look like OWNER/REPO@<40-hex commit sha>", file=sys.stderr)
            return 1
        central = (m.group(1), m.group(2))
    written = init_repo(repo, tier, mode, dry_run=ns.dry_run, central=central)
    print(("would write" if ns.dry_run else "wrote") + f" {len(written)} file(s) in {repo} (tier {tier}, mode {mode}):")
    for w in written:
        print(f"  {w}")
    for name in secret_exposed_workflows(repo):
        print(
            f"\nWARNING {name}: uses repo secrets on pull_request and has no agent/* exclusion. An agent PR could read or\n"
            f"spend them. Add `if: ${{{{ !startsWith(github.head_ref, 'agent/') }}}}` to the secret-using job before enabling."
        )
    if not ns.dry_run:
        print(
            "\nNext: review, commit (signed), push, open the PR. Then set vars/secrets and run `ap ruleset --apply`.\n"
            "Nothing was pushed or changed on GitHub."
        )
    return 0


CALLER_PIN = re.compile(r"uses: ([\w.-]+/[\w.-]+)/\.github/workflows/[\w.-]+@([0-9a-f]{40})")


def _render_callers(kit: tuple[str, str]) -> dict[str, str]:
    """The caller workflows `ap init --kit` would write for this pin (rendered by init_repo into a scratch dir)."""
    import tempfile

    with tempfile.TemporaryDirectory(prefix="ap-upgrade-") as td:
        scratch = Path(td)
        init_repo(scratch, "B", "standard", central=kit)
        rels = [f".github/workflows/{f.name}" for f in sorted((KIT / "callers").glob("*.yml"))]
        return {rel: (scratch / rel).read_text() for rel in rels}


def cmd_upgrade(ns: argparse.Namespace) -> int:
    """Bump the pinned kit sha in an already-central repo's caller workflows, and nothing else. Refuses if any caller differs
    from what `ap init --kit` would write for the current pin (a hand edit must never be silently overwritten)."""
    repo = Path(ns.repo).expanduser().resolve()
    if not (repo / ".git").exists():
        print(f"{repo} is not a git clone", file=sys.stderr)
        return 1
    m = re.fullmatch(r"([\w.-]+/[\w.-]+)@([0-9a-f]{40})", ns.kit)
    if not m:
        print("--kit must look like OWNER/REPO@<40-hex commit sha>", file=sys.stderr)
        return 1
    new = (m.group(1), m.group(2))
    names = sorted(f.name for f in (KIT / "callers").glob("*.yml"))
    current: dict[str, str] = {}
    pins: set[tuple[str, str]] = set()
    for n in names:
        p = repo / ".github" / "workflows" / n
        text = p.read_text() if p.exists() else ""
        found = set(CALLER_PIN.findall(text))
        if not found:
            print(
                f"{repo} is not a central-mode repo (no pinned kit caller in .github/workflows/{n}); use `ap init --kit`",
                file=sys.stderr,
            )
            return 1
        current[f".github/workflows/{n}"] = text
        pins |= found
    if len(pins) != 1:
        print(
            f"callers disagree on the kit pin ({', '.join(f'{k}@{s[:7]}' for k, s in sorted(pins))}); fix by hand",
            file=sys.stderr,
        )
        return 1
    old = next(iter(pins))
    if old[0] != new[0]:
        print(f"repo is pinned to kit {old[0]}, not {new[0]}; upgrade only bumps the sha", file=sys.stderr)
        return 1
    drift = [rel for rel, want in _render_callers(old).items() if current[rel] != want]
    if drift:
        print(
            f"refusing: not what `ap init --kit {old[0]}@{old[1][:7]}` writes (hand-edited?); nothing changed:", file=sys.stderr
        )
        for rel in drift:
            print(f"  {rel}", file=sys.stderr)
        return 1
    if old == new:
        print(f"already on {new[1][:7]}")
        return 0
    if not ns.dry_run:
        if _run("git", "status", "--porcelain", cwd=repo):
            print("working tree is not clean; commit or stash first", file=sys.stderr)
            return 1
        _run("git", "checkout", "-B", "autopilot/upgrade", cwd=repo)
    changed = _render_callers(new)
    for rel, text in changed.items():
        if not ns.dry_run:
            (repo / rel).write_text(text)
    print(
        ("would bump" if ns.dry_run else "bumped") + f" kit {old[1][:7]} -> {new[1][:7]} in {len(changed)} caller(s) in {repo}:"
    )
    for rel in changed:
        print(f"  {rel}")
    if not ns.dry_run:
        print("\nNext: review, commit (signed), push, open the PR. Nothing was pushed or changed on GitHub.")
    return 0


def cmd_handshake(ns: argparse.Namespace) -> int:
    sys.path.insert(0, str(KIT / "runtime"))
    import handshake  # type: ignore

    cfg: dict = {}
    cfg_path = Path(ns.config)
    if cfg_path.exists():
        cfg = yaml.safe_load(cfg_path.read_text()) or {}
    worst = 0
    for s in ns.specs:
        v = handshake.evaluate(Path(s).read_text(), cfg)
        print(f"== {s}\n{v.render()}\n")
        worst = max(worst, v.exit_code)
    return worst


def ruleset_json(checks: list[str]) -> dict:
    return {
        "name": "autopilot-main",
        "target": "branch",
        "enforcement": "active",
        "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
        "bypass_actors": [{"actor_id": 5, "actor_type": "RepositoryRole", "bypass_mode": "pull_request"}],
        "rules": [
            {"type": "deletion"},
            {"type": "non_fast_forward"},
            {"type": "required_signatures"},
            {
                "type": "pull_request",
                "parameters": {
                    "required_approving_review_count": 0,
                    "dismiss_stale_reviews_on_push": False,
                    "require_code_owner_review": True,
                    "require_last_push_approval": False,
                    "required_review_thread_resolution": False,
                    "allowed_merge_methods": ["merge"],
                },
            },
            {
                "type": "required_status_checks",
                "parameters": {
                    "strict_required_status_checks_policy": False,
                    "required_status_checks": [{"context": c} for c in checks],
                },
            },
        ],
    }


def _slug(ns_repo: str, owner: str) -> str:
    return ns_repo if "/" in ns_repo else f"{owner}/{ns_repo}"


def cmd_ruleset(ns: argparse.Namespace) -> int:
    slug = _slug(ns.repo, load_portfolio()["owner"])
    # a reusable-workflow job reports as "<caller job> / <called job>"
    body = ruleset_json(["guard / guard" if ns.central else "guard"] + ns.check)
    if not ns.apply:
        print(f"[dry run] would POST (or PUT if it exists) to repos/{slug}/rulesets:\n{json.dumps(body, indent=2)}")
        return 0
    # update in place if the ruleset exists (a second POST would add a duplicate or 422)
    found = json.loads(_run("gh", "api", f"repos/{slug}/rulesets", check=False) or "[]")
    rid = next((x["id"] for x in found if isinstance(x, dict) and x.get("name") == body["name"]), None)
    url, method = (f"repos/{slug}/rulesets/{rid}", "PUT") if rid else (f"repos/{slug}/rulesets", "POST")
    r = subprocess.run(
        ["gh", "api", url, "--method", method, "--input", "-"],
        input=json.dumps(body),
        text=True,
        capture_output=True,
    )
    print(r.stdout or r.stderr)
    return r.returncode


def cmd_vars(ns: argparse.Namespace) -> int:
    """enable / pause / resume: set repo variables. Dry-run unless --apply."""
    pf = load_portfolio()
    repos = [ns.repo] if getattr(ns, "repo", None) else [n for n, e in pf["repos"].items() if e.get("enabled")]
    var, val = {
        "enable": ("AUTOPILOT_ENABLED", "true"),
        "pause": ("AUTOPILOT_PAUSED", "true"),
        "resume": ("AUTOPILOT_PAUSED", "false"),
    }[ns.cmd]
    for name in repos:
        if ns.cmd == "enable" and pf["repos"].get(name, {}).get("data_class") == "restricted":
            print(f"{name}: data_class restricted; refusing to enable")
            continue
        slug = _slug(name, pf["owner"])
        if not ns.apply:
            print(f"[dry run] gh variable set {var}={val} -R {slug}")
            continue
        r = subprocess.run(["gh", "variable", "set", var, "--body", val, "-R", slug], capture_output=True, text=True)
        print(f"{slug}: {var}={val}" if r.returncode == 0 else f"{slug}: FAILED {r.stderr.strip()}")
    return 0


def cmd_doctor(ns: argparse.Namespace) -> int:
    problems = 0
    for rp in ns.repos:
        repo = Path(rp).expanduser().resolve()
        print(f"== {repo_name(repo)}")
        m = repo / ".autopilot" / "manifest.json"
        if not m.exists():
            print("  FAIL not installed (run `ap init`)")
            problems += 1
            continue
        manifest = json.loads(m.read_text())
        if manifest.get("kit_version") != VERSION:
            print(f"  WARN kit {manifest.get('kit_version')} != {VERSION}: run `ap init` again to upgrade")
        for rel, sha in manifest["files"].items():
            p = repo / rel
            if not p.exists():
                print(f"  FAIL missing {rel}")
                problems += 1
            elif _sha(p.read_bytes()) != sha:
                print(f"  WARN modified since install: {rel}")
        for wf in (repo / ".github/workflows").glob("*.yml"):
            text = wf.read_text()
            for line in text.splitlines():
                if "uses:" in line and "@" in line and not line.split("@")[1].split()[0].isalnum():
                    continue
                if "uses:" in line and "@" in line:
                    ref = line.split("@")[1].split()[0]
                    if len(ref) != 40 and "autopilot" in text.splitlines()[0]:
                        print(f"  FAIL {wf.name}: action not pinned to a SHA: {line.strip()}")
                        problems += 1
        for name in secret_exposed_workflows(repo):
            print(
                f"  FAIL {name}: uses repo secrets on pull_request with no agent/* exclusion (an agent PR could read or spend them)"
            )
            problems += 1
        ci = [f for f in (repo / ".github/workflows").glob("*.yml") if f.name not in AUTOPILOT_WORKFLOWS]
        if ci and not any("push" in f.read_text() for f in ci):
            print("  WARN no CI workflow triggers on push; agent pushes will not fire PR checks (add `push:` trigger)")
        if not (repo / "CLAUDE.md").exists() or "@AGENTS.md" not in (repo / "CLAUDE.md").read_text():
            print("  WARN CLAUDE.md does not import AGENTS.md")
        slug = _slug(repo_name(repo), load_portfolio()["owner"])
        rs = subprocess.run(["gh", "api", f"repos/{slug}/rulesets", "--jq", ".[].name"], capture_output=True, text=True)
        if rs.returncode == 0 and "autopilot-main" not in rs.stdout:
            print("  FAIL ruleset autopilot-main not applied (`ap ruleset REPO --apply`)")
            problems += 1
        sec = subprocess.run(["gh", "secret", "list", "-R", slug], capture_output=True, text=True)
        if sec.returncode == 0 and "CLAUDE_CODE_OAUTH_TOKEN" not in sec.stdout:
            print("  WARN secret CLAUDE_CODE_OAUTH_TOKEN not set (needed before enabling)")
    print(
        "\nManual checks (cannot be verified by API):\n"
        "  - claude.ai connectors (Gmail, Calendar, Drive, Todoist, Asana): cloud routines/sessions attach ALL of them\n"
        "    by default and call them without asking. Remove every connector from any routine you create, and toggle\n"
        "    them off for cloud sessions that touch these repos.\n"
        "  - Claude GitHub App installed on this repo.\n"
    )
    return 1 if problems else 0


def cmd_status(ns: argparse.Namespace) -> int:
    pf = load_portfolio()
    print(f"{'repo':28} {'tier':4} {'mode':9} {'runs24h':8} {'agentPRs':8}")
    for name, e in pf["repos"].items():
        if not e.get("enabled"):
            continue
        slug = _slug(name, pf["owner"])
        runs = subprocess.run(
            ["gh", "run", "list", "-R", slug, "--workflow", "agent-exec.yml", "--limit", "30", "--json", "createdAt"],
            capture_output=True,
            text=True,
        )
        prs = subprocess.run(["gh", "pr", "list", "-R", slug, "--json", "headRefName"], capture_output=True, text=True)
        import datetime as dt

        n_runs = "-"
        if runs.returncode == 0:
            since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=24)
            n_runs = str(
                sum(
                    1
                    for r in json.loads(runs.stdout or "[]")
                    if dt.datetime.fromisoformat(r["createdAt"].replace("Z", "+00:00")) >= since
                )
            )
        n_prs = "-"
        if prs.returncode == 0:
            n_prs = str(sum(1 for p in json.loads(prs.stdout or "[]") if p["headRefName"].startswith("agent/")))
        print(f"{name:28} {e['tier']:4} {e['mode']:9} {n_runs:8} {n_prs:8}")
    return 0


def cmd_pick(ns: argparse.Namespace) -> int:
    """Plan (and with --apply, fire) the nightly dispatch: spread the global run pool by priority, work-conserving."""
    import datetime as dt

    from autopilot import picker

    pf = load_portfolio()
    now = dt.datetime.now(dt.timezone.utc)
    cands, notes = [], []
    for name, e in pf["repos"].items():
        if not e.get("enabled") or e.get("mode") == "dormant" or e.get("data_class") == "restricted":
            continue
        if picker.held(e, now):
            notes.append(f"{name}: held until {e['hold_until']}")
            continue
        slug = _slug(name, pf["owner"])
        r = subprocess.run(
            ["gh", "issue", "list", "-R", slug, "--label", "agent-ready", "--state", "open", "--json", "labels"],
            capture_output=True,
            text=True,
        )
        if r.returncode:
            notes.append(f"{name}: cannot read issues")
            continue
        skip = {"hold", "needs-human", "blocked", "agent-working"}
        eligible = sum(1 for i in json.loads(r.stdout or "[]") if not {x["name"] for x in i["labels"]} & skip)
        runs = subprocess.run(
            ["gh", "run", "list", "-R", slug, "--workflow", "agent-exec.yml", "--limit", "30", "--json", "createdAt,conclusion"],
            capture_output=True,
            text=True,
        )
        since = now - dt.timedelta(hours=24)
        used = sum(
            1
            for x in json.loads(runs.stdout or "[]")
            if x.get("conclusion") not in ("skipped", "cancelled")
            and dt.datetime.fromisoformat(x["createdAt"].replace("Z", "+00:00")) >= since
        )
        cap = int(pf["defaults"]["runs_per_day"].get(e.get("tier", "C"), 0))
        cands.append({"name": name, "priority": picker.priority(e), "capacity": min(eligible, max(cap - used, 0))})
    plan = picker.allocate(cands, int(pf["defaults"].get("global_runs_per_day", 12)), ns.reserve)
    print(f"{'repo':28} {'prio':4} {'capacity':8} runs")
    for c in cands:
        print(f"{c['name']:28} {c['priority']:<4} {c['capacity']:<8} {plan.get(c['name'], 0)}")
    for n in notes:
        print(f"note: {n}")
    if not ns.apply:
        print("\ndry run. --apply fires each repo's agent-dispatch (its own gate still decides).")
        return 0
    for name in plan:
        subprocess.run(["gh", "workflow", "run", "agent-dispatch.yml", "-R", _slug(name, pf["owner"])], check=False)
    return 0


def export_state(pf: dict, now) -> dict:
    from autopilot import picker

    repos = [
        {
            "name": n,
            "tier": e.get("tier", "C"),
            "mode": e.get("mode", "dormant"),
            "enabled": bool(e.get("enabled")),
            "priority": picker.priority(e),
            "hold_until": str(e["hold_until"]) if e.get("hold_until") else None,
            "public": bool(e.get("public")),
        }
        for n, e in pf["repos"].items()
    ]
    return {
        "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "owner": pf["owner"],
        "global_runs_per_day": int(pf["defaults"].get("global_runs_per_day", 12)),
        "repos": repos,
    }


OWNER_UUID = "00000000-0000-0000-0000-000068158512"  # stable stand-in id for the owner until Supabase Auth is used


def state_sql(state: dict) -> str:
    """Idempotent upsert of the portfolio into the control-plane database (ids/values are validated, not interpolated blindly)."""

    def lit(v: str) -> str:
        return "'" + v.replace("'", "''") + "'"

    out = [
        f"insert into orgs(id, name, owner_id) values ({lit(OWNER_UUID)}, {lit(state['owner'])}, {lit(OWNER_UUID)}) on conflict (id) do nothing;",
        f"insert into members(org_id, user_id, role) values ({lit(OWNER_UUID)}, {lit(OWNER_UUID)}, 'owner') on conflict do nothing;",
    ]
    for r in state["repos"]:
        if not re.fullmatch(r"[\w.-]+", r["name"]) or r["tier"] not in "ABC" or r["mode"] not in PF_KEYS["mode"]:
            raise SystemExit(f"refusing to seed odd repo entry: {r['name']}")
        hold = lit(r["hold_until"]) if r["hold_until"] else "null"
        out.append(
            "insert into projects(org_id, repo, tier, mode, enabled, priority, hold_until, is_public) values "
            f"({lit(OWNER_UUID)}, {lit(state['owner'] + '/' + r['name'])}, {lit(r['tier'])}, {lit(r['mode'])}, "
            f"{str(r['enabled']).lower()}, {int(r['priority'])}, {hold}, {str(r['public']).lower()}) "
            "on conflict (org_id, repo) do update set tier=excluded.tier, mode=excluded.mode, enabled=excluded.enabled, "
            "priority=excluded.priority, hold_until=excluded.hold_until, is_public=excluded.is_public;"
        )
    return "\n".join(out)


def cmd_export_state(ns: argparse.Namespace) -> int:
    import datetime as dt

    out = export_state(load_portfolio(), dt.datetime.now(dt.timezone.utc))
    if ns.sql:
        print(state_sql(out))
        return 0
    dest = Path(ns.dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, indent=2) + "\n")
    print(f"wrote {dest} ({len(out['repos'])} repos)")
    return 0


def cmd_report(ns: argparse.Namespace) -> int:
    """Read-only outcome scorecard for enabled, un-held repos (what merged, what was rejected, how fast)."""
    import datetime as dt

    from autopilot import picker, report

    pf = load_portfolio()
    now = dt.datetime.now(dt.timezone.utc)
    since = now - dt.timedelta(days=ns.days)
    fields = "number,title,body,headRefName,state,createdAt,mergedAt,closedAt,labels"
    print(f"agent PR outcomes, last {ns.days}d")
    print(f"{'repo':24} {'opened':6} {'merged':6} {'closed':6} {'open':4} {'revert':6} {'rate':5} {'med h':6}")
    for name, e in pf["repos"].items():
        if not e.get("enabled") or e.get("mode") == "dormant" or picker.held(e, now):
            continue
        r = subprocess.run(
            ["gh", "pr", "list", "-R", _slug(name, pf["owner"]), "--state", "all", "--limit", "200", "--json", fields],
            capture_output=True,
            text=True,
        )
        if r.returncode:
            print(f"{name:24} (cannot read)")
            continue
        prs = json.loads(r.stdout or "[]")
        c = report.scorecard(prs, since=since)
        rate = "-" if c["merge_rate"] is None else f"{c['merge_rate']:.0%}"
        med = "-" if c["median_hours_to_merge"] is None else str(c["median_hours_to_merge"])
        print(
            f"{name:24} {c['opened']:<6} {c['merged']:<6} {c['closed_unmerged']:<6} {c['open']:<4} {c['reverted']:<6} {rate:5} {med:6}"
        )
        for cls, v in c["by_class"].items():
            print(f"    {cls}: {v['merged']} merged, {v['reverted']} reverted")
        rr = subprocess.run(
            [
                "gh",
                "run",
                "list",
                "-R",
                _slug(name, pf["owner"]),
                "--workflow",
                "agent-exec.yml",
                "--limit",
                "100",
                "--json",
                "conclusion,createdAt,displayTitle,startedAt,updatedAt",
            ],
            capture_output=True,
            text=True,
        )
        if rr.returncode == 0:
            runs = [
                x
                for x in json.loads(rr.stdout or "[]")
                if dt.datetime.fromisoformat(x["createdAt"].replace("Z", "+00:00")) >= since
            ]
            pts = report.points_per_merged(runs, prs, since=since)
            print(f"    est. run-points per merged PR: {'-' if pts is None else pts} (estimate: turn cap x model weight)")
            mins = report.minutes_per_merged(runs, prs, since=since)
            print(f"    est. Actions minutes per merged PR: {'-' if mins is None else mins} (agent-exec only; private repos cap at $10)")
        else:
            print("    est. run-points per merged PR: (cannot read runs)")
        for cls in report.promotion_candidates(c, [], min_clean=ns.min_clean):
            print(f"    -> consider enabling auto-merge for '{cls}' (clean merges). Your call; it is a PR.")
    return 0


def cmd_digest(ns: argparse.Namespace) -> int:
    """Read-only: markdown summary of the last 24h across enabled repos. Uses gh list/get only; calls no model."""
    import datetime as dt

    from autopilot import digest

    pf = load_portfolio()
    now = dt.datetime.now(dt.timezone.utc)
    fields = "number,title,headRefName,state,isDraft,url,mergedAt"
    summaries, statuses = [], {}
    for name, e in pf["repos"].items():
        if not e.get("enabled"):
            continue
        slug = _slug(name, pf["owner"])

        def gh(*args: str) -> subprocess.CompletedProcess:
            return subprocess.run(["gh", *args], capture_output=True, text=True)

        p = gh("pr", "list", "-R", slug, "--state", "all", "--limit", "100", "--json", fields)
        r = gh(
            "run",
            "list",
            "-R",
            slug,
            "--workflow",
            "agent-exec.yml",
            "--limit",
            "50",
            "--json",
            "databaseId,conclusion,createdAt,displayTitle",
        )
        v = gh("variable", "get", "AUTOPILOT_PAUSED", "-R", slug)
        summaries.append(
            digest.summarize(
                name,
                json.loads(p.stdout or "[]") if p.returncode == 0 else [],
                json.loads(r.stdout or "[]") if r.returncode == 0 else [],
                now,
            )
        )
        statuses[name] = digest.repo_status(e, v.returncode == 0 and v.stdout.strip() == "true", now)
        if p.returncode or r.returncode:
            statuses[name] = "cannot read GitHub" if statuses[name] == "ok" else statuses[name] + " (cannot read GitHub)"
    print(digest.render(summaries, statuses, now), end="")
    return 0


def cmd_retro(ns: argparse.Namespace) -> int:
    """Read-only: why did agent work fail to land? Prints an evidence packet; writes nothing, calls no model."""
    import datetime as dt

    from autopilot import picker, retro

    pf = load_portfolio()
    now = dt.datetime.now(dt.timezone.utc)
    since = now - dt.timedelta(days=ns.days)
    runs, prs, ex = [], [], {}
    for name, e in pf["repos"].items():
        if not e.get("enabled") or e.get("mode") == "dormant" or picker.held(e, now):
            continue
        slug = _slug(name, pf["owner"])
        r = subprocess.run(
            [
                "gh",
                "run",
                "list",
                "-R",
                slug,
                "--workflow",
                "agent-exec.yml",
                "--limit",
                "50",
                "--json",
                "databaseId,conclusion,createdAt,displayTitle",
            ],
            capture_output=True,
            text=True,
        )
        for x in json.loads(r.stdout or "[]") if r.returncode == 0 else []:
            if dt.datetime.fromisoformat(x["createdAt"].replace("Z", "+00:00")) < since or x["conclusion"] in (
                "success",
                "skipped",
                "cancelled",
                "",
            ):
                continue
            jr = subprocess.run(
                ["gh", "run", "view", str(x["databaseId"]), "-R", slug, "--json", "jobs"], capture_output=True, text=True
            )
            step = ""
            for job in json.loads(jr.stdout or "{}").get("jobs", []) if jr.returncode == 0 else []:
                step = next((s["name"] for s in job.get("steps", []) if s.get("conclusion") == "failure"), step)
            item = {"conclusion": x["conclusion"], "failed_step": step}
            runs.append(item)
            ex.setdefault(retro.classify_run(item) or "", []).append(
                f"{name} run {x['databaseId']} ({x['displayTitle'].strip()})"
            )
        p = subprocess.run(
            [
                "gh",
                "pr",
                "list",
                "-R",
                slug,
                "--state",
                "closed",
                "--limit",
                "50",
                "--json",
                "number,title,state,mergedAt,headRefName,comments,closedAt",
            ],
            capture_output=True,
            text=True,
        )
        for x in json.loads(p.stdout or "[]") if p.returncode == 0 else []:
            if not x["headRefName"].startswith("agent/") or x.get("mergedAt") or not x.get("closedAt"):
                continue
            if dt.datetime.fromisoformat(x["closedAt"].replace("Z", "+00:00")) < since:
                continue
            item = {"state": x["state"], "mergedAt": x.get("mergedAt"), "comments": len(x.get("comments") or [])}
            prs.append(item)
            ex.setdefault(retro.classify_pr(item) or "", []).append(f"{name} PR #{x['number']} ({x['title']})")
    print(retro.packet(retro.causes(runs, prs), ex, min_count=ns.min_count))
    return 0


def _kit_slug_and_sha(ns_kit: str) -> tuple[str, str]:
    m = re.fullmatch(r"([\w.-]+/[\w.-]+)@([0-9a-f]{40})", ns_kit or "")
    if not m:
        raise SystemExit("--kit must look like OWNER/REPO@<40-hex sha>")
    return m.group(1), m.group(2)


def _approve_branch(sha: str) -> str:
    return f"approve-{sha[:7]}"


def _head_sha() -> str:
    r = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else ""


def cmd_provenance(ns: argparse.Namespace) -> int:
    """Read-only: is the kit tree at SHA exactly the render of kit/ at an autopilot commit on main? Exit 1 on any failure."""
    from autopilot import provenance as prov

    kit_repo, sha = _kit_slug_and_sha(ns.kit)
    opener = prov._default_opener
    approvals = _load_runtime("automerge").approvals_repo(kit_repo)
    try:
        source = ns.source or prov.parse_source_hint(
            prov._get(opener, f"{prov.API}/repos/{approvals}/contents/APPROVED?ref=main").decode(), sha
        )
        if ns.pins:
            pins = json.loads(Path(ns.pins).read_text())
        else:
            pins = json.loads(prov._get(opener, f"{prov.API}/repos/{approvals}/contents/.github/provenance/pins.json?ref=main"))
    except (prov.ProvenanceError, ValueError, OSError) as e:
        print(f"FAIL {e}", file=sys.stderr)
        return 1
    problems = prov.verify_provenance(
        kit_repo, sha, source, pins, previous_source=ns.previous_source, source_repo=ns.source_repo, opener=opener
    )
    if problems:
        for pr in problems:
            print(f"FAIL {pr}", file=sys.stderr)
        return 1
    print(f"OK {kit_repo}@{sha[:7]} is the render of autopilot@{source[:7]}")
    return 0


def cmd_approve(ns: argparse.Namespace) -> int:
    """Open a PR on the approvals repo adding a kit sha to APPROVED. Merging that PR (only you can) is the one approval a release
    needs; repos with the `kit-bump` class then take the pin bump without a second review."""
    import base64

    kit_repo, sha = _kit_slug_and_sha(ns.kit)
    kit = _load_runtime("automerge").approvals_repo(kit_repo)  # approvals live in <owner>/autopilot-approved
    cur = subprocess.run(["gh", "api", f"repos/{kit}/contents/APPROVED"], capture_output=True, text=True)
    body = "# Kit shas the owner approved. Only owner-reviewed PRs may change this file.\n"
    if cur.returncode == 0:
        j = json.loads(cur.stdout)
        body = base64.b64decode(j["content"]).decode()
    if sha in body:
        print(f"{sha[:7]} is already approved")
        return 0
    # `source=<autopilot sha>` names the commit this kit was exported from, so `ap provenance` can verify it; fetch_approved reads
    # only the first token of the line, so the note (and this hint) never affect which shas are approved.
    source = ns.source or _head_sha()
    if not re.fullmatch(r"[0-9a-f]{40}", source):
        print("--source must be the 40-hex autopilot commit the kit was exported from", file=sys.stderr)
        return 1
    note = " ".join(((ns.note or "approved") + f" source={source}").split())
    line = f"{sha}  {note}"
    body = body.rstrip("\n") + f"\n{line}\n"
    if not ns.apply:
        print(f"[dry run] would open a PR on {kit} adding:\n{line}")
        return 0
    import tempfile

    branch = _approve_branch(sha)
    with tempfile.TemporaryDirectory(prefix="ap-approve-") as td:
        dest = Path(td) / "approved"
        _run("gh", "repo", "clone", kit, str(dest))
        _run("git", "checkout", "-q", "-B", branch, "origin/main", cwd=dest)
        (dest / "APPROVED").write_text(body)
        _run("git", "add", "-A", cwd=dest)
        # a LOCAL signed commit: commits made through the contents API are unsigned and the approvals ruleset requires signatures
        _run("git", "commit", "-q", "-S", "-m", f"approve kit {sha[:7]}", cwd=dest)
        _run("git", "push", "-q", "-f", "origin", branch, cwd=dest)
        url = _run(
            "gh",
            "pr",
            "create",
            "-R",
            kit,
            "--base",
            "main",
            "--head",
            branch,
            "--title",
            f"approve kit {sha[:7]}",
            "--body",
            f"Approves `{sha}` for automatic pin bumps in repos that opted into the `kit-bump` class.\n\n{ns.note or ''}\n\nReview the diff of the kit between the previously approved sha and this one before merging.",
            cwd=dest,
        )
    print(url.strip())
    return 0


def _load_runtime_picker_held(entry: dict) -> bool:
    import datetime as dt

    from autopilot import picker

    return picker.held(entry, dt.datetime.now(dt.timezone.utc))


def rollout_candidates(pf: dict, only: list[str] | None = None):
    """(name, entry) for every repo a rollout may touch (enabled, not dormant, not restricted, selected)."""
    for name, e in pf["repos"].items():
        if not e.get("enabled") or e.get("mode") == "dormant" or e.get("data_class") == "restricted":
            continue
        if only and name not in only:
            continue
        yield name, e


def _rollout_branch(sha: str) -> str:
    return f"autopilot/kit-bump-{sha[:7]}"


def _bump_scratch(files: dict[str, str]):
    td = tempfile.TemporaryDirectory(prefix="ap-bump-")
    for rel, content in files.items():
        p = Path(td.name) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    return td


def bump_inputs(
    paths: list[str], kit_slug: str, sha: str, tier: str = "B", mode: str = "standard"
) -> tuple[list[str], list[str]]:
    """Which of a repo's files `bump_files` needs. `paths` = every file path in the repo. Returns (read these, presence only):
    the files init_repo would manage or merge, plus the stack markers and package-lock.json whose existence (not content)
    picks commands and setup steps. Presence-only files are passed to bump_files with empty content."""
    with tempfile.TemporaryDirectory(prefix="ap-bump-") as td:
        root = Path(td)
        init_repo(root, tier, mode, central=(kit_slug, sha))
        managed = {str(q.relative_to(root)) for q in root.rglob("*") if q.is_file()}
    managed |= {".autopilot/repo.yaml", ".nvmrc"} | {f".autopilot/{n}" for n in RUNTIME_FILES}  # the last: removed when migrating
    markers = set(STACKS) | {"package-lock.json"}
    have = set(paths)
    present = {
        p
        for p in have
        if (parts := p.split("/"))
        and parts[-1] in markers
        and (len(parts) == 1 or (len(parts) == 2 and parts[0] not in SKIP_DIRS and not parts[0].startswith(".")))
    }
    return sorted(managed & have), sorted(present - managed)


def bump_files(
    files: dict[str, str], kit_slug: str, sha: str, tier: str = "B", mode: str = "standard"
) -> dict[str, str | None] | None:
    """Pure core of a rollout: a repo's current files (see bump_inputs) -> {path: new content} for what changes
    (None = delete). Returns None when the repo is not on the shared kit yet or nothing changes. It is exactly what
    `ap init --kit` would do, run on a scratch copy, so the local and CI rollouts cannot drift apart."""
    if "autopilot-kit" not in files.get(".github/workflows/agent-exec.yml", ""):
        return None
    with _bump_scratch(files) as td:
        root = Path(td)
        init_repo(root, tier, mode, central=(kit_slug, sha))
        after = {str(q.relative_to(root)): q.read_text() for q in root.rglob("*") if q.is_file()}
    out: dict[str, str | None] = {p: c for p, c in after.items() if files.get(p) != c}
    out.update({p: None for p in files if p not in after})
    return out or None


def cmd_rollout(ns: argparse.Namespace) -> int:
    """Open a pin-bump PR in every enabled central-mode repo for an APPROVED kit sha. Repos that opted into `kit-bump` merge
    it themselves once checks pass; the rest wait for you like any other PR."""
    fetch_approved = _load_runtime("automerge").fetch_approved

    if getattr(ns, "ci", False):  # GitHub App mode (ROLLOUT_TOKEN): opens the PRs over REST, never merges
        from autopilot import rollout_ci

        return rollout_ci.run(ns)
    kit, sha = _kit_slug_and_sha(ns.kit)
    if sha not in fetch_approved(kit):
        print(
            f"{sha[:7]} is not on {kit}'s APPROVED list. Run `ap approve --kit {kit}@{sha}` and merge that PR first.",
            file=sys.stderr,
        )
        return 1
    pf = load_portfolio()
    for name, e in rollout_candidates(pf, ns.only):
        if _load_runtime_picker_held(e):
            print(f"{name}: held by the owner until {e['hold_until']}; skipped")
            continue
        slug = _slug(name, pf["owner"])
        if not ns.apply:
            print(f"[dry run] would open a pin-bump PR in {slug} -> {sha[:7]}")
            continue
        with tempfile.TemporaryDirectory(prefix="ap-rollout-") as td:
            dest = Path(td) / name
            r = subprocess.run(["gh", "repo", "clone", slug, str(dest), "--", "--depth", "50"], capture_output=True, text=True)
            if r.returncode:
                print(f"{slug}: clone failed")
                continue
            branch = _rollout_branch(sha)
            if (
                "autopilot-kit" not in (dest / ".github/workflows/agent-exec.yml").read_text()
                if (dest / ".github/workflows/agent-exec.yml").exists()
                else True
            ):
                print(f"{slug}: not on the shared kit yet; migrate it with `ap init --kit` first (rollout only bumps pins)")
                continue
            _run("git", "checkout", "-q", "-B", branch, cwd=dest)
            have = sorted(
                str(q.relative_to(dest)) for q in dest.rglob("*") if q.is_file() and ".git" not in q.relative_to(dest).parts
            )
            fetch, present = bump_inputs(have, kit, sha, e.get("tier", "B"), e.get("mode", "standard"))
            files = {rel: (dest / rel).read_text() for rel in fetch} | {rel: "" for rel in present}
            changes = bump_files(files, kit, sha, e.get("tier", "B"), e.get("mode", "standard"))
            for rel, content in (changes or {}).items():
                if content is None:
                    (dest / rel).unlink()
                else:
                    (dest / rel).parent.mkdir(parents=True, exist_ok=True)
                    (dest / rel).write_text(content)
            if not _run("git", "status", "--porcelain", cwd=dest):
                print(f"{slug}: already on {sha[:7]}")
                continue
            _run("git", "add", "-A", cwd=dest)
            _run("git", "commit", "-q", "-S", "-m", f"autopilot: bump kit to {sha[:7]}", cwd=dest)
            _run("git", "push", "-q", "-u", "origin", branch, "--force-with-lease", cwd=dest)
            url = _run(
                "gh",
                "pr",
                "create",
                "-R",
                slug,
                "--base",
                "main",
                "--head",
                branch,
                "--title",
                f"autopilot: bump kit to {sha[:7]}",
                "--body",
                f"Pin bump to the owner-approved kit `{sha}`. Auto-merges after checks if this repo has the `kit-bump` class; otherwise yours to review.",
                cwd=dest,
            )
            print(f"{slug}: {url.strip()}")
    return 0


def gather_preflight_facts(name: str, entry: dict, owner: str) -> dict:
    """Read-only: everything `preflight.evaluate` needs, from GitHub (REST/gh) and the portfolio."""
    slug = f"{owner}/{name}"

    def gh(*a: str):
        r = subprocess.run(["gh", *a], capture_output=True, text=True)
        return json.loads(r.stdout) if r.returncode == 0 and r.stdout.strip() else None

    def text(path: str) -> str:
        r = subprocess.run(
            ["gh", "api", f"repos/{slug}/contents/{path}", "-H", "Accept: application/vnd.github.raw+json"],
            capture_output=True,
            text=True,
        )
        return r.stdout if r.returncode == 0 else ""

    secrets = [x["name"] for x in gh("secret", "list", "-R", slug, "--json", "name") or []]
    variables = {x["name"]: x["value"] for x in gh("variable", "list", "-R", slug, "--json", "name,value") or []}
    rs_list = gh("api", f"repos/{slug}/rulesets") or []
    rs = None
    if rs_list:
        full = gh("api", f"repos/{slug}/rulesets/{rs_list[0]['id']}") or {}
        rules = {r["type"]: r.get("parameters", {}) for r in full.get("rules", [])}
        rs = {
            "checks": [c["context"] for c in rules.get("required_status_checks", {}).get("required_status_checks", [])],
            "signatures": "required_signatures" in rules,
            "codeowner": bool(rules.get("pull_request", {}).get("require_code_owner_review")),
        }
    co = text(".github/CODEOWNERS")
    shas = set()
    for wf in ("agent-exec", "agent-dispatch", "guard", "handshake", "automerge"):
        shas |= set(re.findall(r"autopilot-kit/\.github/workflows/[\w.-]+@([0-9a-f]{40})", text(f".github/workflows/{wf}.yml")))
    approved = _load_runtime("automerge").fetch_approved(f"{owner}/autopilot-kit")
    runs = gh("run", "list", "-R", slug, "--workflow", "agent-exec.yml", "--limit", "1", "--json", "conclusion,status") or []
    last_exec = (runs[0].get("conclusion") or runs[0]["status"]) if runs else None
    any_runs = gh("run", "list", "-R", slug, "--limit", "8", "--json", "conclusion,startedAt,updatedAt") or []

    def secs(r):
        import datetime as dt

        try:
            return (
                dt.datetime.fromisoformat(r["updatedAt"].replace("Z", "+00:00"))
                - dt.datetime.fromisoformat(r["startedAt"].replace("Z", "+00:00"))
            ).total_seconds()
        except Exception:
            return 99

    billing = bool(any_runs) and all(r.get("conclusion") == "failure" and secs(r) < 6 for r in any_runs[:3])
    prs = gh("pr", "list", "-R", slug, "--state", "open", "--json", "headRefName") or []
    issues = gh("issue", "list", "-R", slug, "--label", "agent-ready", "--state", "open", "--json", "labels") or []
    skip = {"hold", "needs-human", "blocked", "agent-working"}
    cfg = yaml.safe_load(text(".autopilot/repo.yaml") or "{}") or {}
    pol = yaml.safe_load(text(".autopilot/merge-policy.yaml") or "{}") or {}
    return {
        "secrets": secrets,
        "variables": variables,
        "ruleset": rs,
        "codeowners_catchall": bool(re.search(r"(?m)^\*\s", co)),
        "codeowners_has_block": "BEGIN autopilot" in co,
        "caller_shas": sorted(shas),
        "approved": approved,
        "latest_approved": approved[-1] if approved else None,
        "last_exec": last_exec,
        "billing_suspect": billing,
        "open_agent_prs": sum(1 for p_ in prs if p_["headRefName"].startswith("agent/")),
        "max_open_prs": int((cfg.get("budget") or {}).get("max_open_agent_prs", 3)),
        "agent_ready": sum(1 for i in issues if not {x["name"] for x in i["labels"]} & skip),
        "merge_classes": list(pol.get("auto_merge_classes") or []),
        "public": bool(entry.get("public")),
        "data_class": entry.get("data_class"),
    }


def cmd_preflight(ns: argparse.Namespace) -> int:
    from autopilot import preflight

    pf = load_portfolio()
    worst = 0
    for name in ns.repos:
        if name not in pf["repos"]:
            print(f"{name}: not in the portfolio", file=sys.stderr)
            return 1
        res = preflight.evaluate(gather_preflight_facts(name, pf["repos"][name], pf["owner"]))
        p_, w_, f_ = preflight.summarize(res)
        print(
            f"== {name}: {p_} pass, {w_} warn, {f_} fail -> {'NOT READY to leave unattended' if f_ else 'ready to run unattended' + (' (with warnings)' if w_ else '')}"
        )
        for lv, msg in res:
            if lv != preflight.PASS or ns.verbose:
                print(f"  {lv:4} {msg}")
        worst = max(worst, 1 if f_ else 0)
    return worst


_REDACT = [
    (re.compile(r"sk-ant-[A-Za-z0-9_-]{8,}"), "[redacted-key]"),
    (re.compile(r"\b(ghp|gho|ghs|ghu|github_pat)_[A-Za-z0-9_]{12,}"), "[redacted-token]"),
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{6,}"), "Bearer [redacted]"),
    (
        re.compile(r"(?i)\b(authorization|token|secret|password|api[_-]?key)(\s*[:=]\s*)(?!\[redacted)[^\s'\"]{6,}"),
        r"\1\2[redacted]",
    ),
    (re.compile(r"eyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}"), "[redacted-jwt]"),
]


def redact(text: str) -> str:
    """Strip anything key-shaped from log text before it goes into an issue (belt and braces: the logs are already masked)."""
    for rx, rep in _REDACT:
        text = rx.sub(rep, text)
    return text


def cmd_kit_fix(ns: argparse.Namespace) -> int:
    """Turn a failed agent run into a `kit-fix` issue on the kit-source repo. The label fires the kit-proposer workflow,
    which drafts a fix PR for your review. Evidence is the failed step's log tail, redacted."""
    pf = load_portfolio()
    m = re.fullmatch(r"([\w.-]+)(?:/([\w.-]+))?:(\d+)", ns.run or "")
    if not m:
        print("--run must look like REPO:RUN_ID (for example stencil:38989085293)", file=sys.stderr)
        return 1
    repo = f"{pf['owner']}/{m.group(2) or m.group(1)}" if "/" not in (ns.run or "") else f"{m.group(1)}/{m.group(2)}"
    r = subprocess.run(["gh", "run", "view", m.group(3), "-R", repo, "--log-failed"], capture_output=True, text=True)
    tail = redact("\n".join(r.stdout.splitlines()[-ns.lines :])) if r.returncode == 0 else "(could not read the run log)"
    body = (
        f"Failure in `{repo}` run {m.group(3)}.\n\n{ns.note or ''}\n\n<details><summary>failed-step log (last {ns.lines} lines, redacted)</summary>\n\n"
        f"```\n{tail}\n```\n</details>\n\nThe proposer should find the root cause in `kit/` or `src/autopilot/`, make the smallest fix with a test, and open a PR. "
        "Anything needing `.github/`, `.autopilot/`, `policy/` or `apps/` is for the owner."
    )
    kit_source = f"{pf['owner']}/autopilot"
    if not ns.apply:
        print(f"[dry run] would open an issue on {kit_source} labelled kit-fix:\n{ns.title}\n{body[:600]}")
        return 0
    subprocess.run(["gh", "label", "create", "kit-fix", "-R", kit_source, "--color", "B60205", "--force"], capture_output=True)
    url = _run("gh", "issue", "create", "-R", kit_source, "--title", ns.title, "--body", body, "--label", "kit-fix")
    print(url.strip())
    return 0


def scan_suggestions(repos: list[dict], pf: dict, now) -> list[dict]:
    """Read-only triage of an owner's repos. Tier A is a human decision, so it is never suggested."""
    import datetime as dt

    out = []
    for r in repos:
        name = r["name"]
        row = {"name": name, "action": "skip", "tier": "-", "mode": "-", "reason": ""}
        age = (now - dt.datetime.fromisoformat(r["pushedAt"].replace("Z", "+00:00"))).days if r.get("pushedAt") else 9999
        if name in pf.get("repos", {}):
            row.update(action="managed", tier=pf["repos"][name].get("tier", "-"), reason="already in portfolio")
        elif name in pf.get("excluded", []):
            row["reason"] = "excluded in portfolio"
        elif r.get("isFork"):
            row["reason"] = "fork"
        elif r.get("isArchived"):
            row["reason"] = "archived"
        elif age > 180:
            row["reason"] = f"stale ({age}d since last push)"
        else:
            tier, mode = ("B", "standard") if age <= 30 else ("C", "dormant")
            row.update(action="add", tier=tier, mode=mode, reason=f"pushed {age}d ago")
            if not r.get("isPrivate", True):
                row.update(
                    mode="dormant", reason=row["reason"] + "; public repo: prompt-injection surface, review before enabling"
                )
        out.append(row)
    return out


def _latest_approved(kit_repo: str) -> str:
    approved = _load_runtime("automerge").fetch_approved(kit_repo)
    if not approved:
        raise SystemExit(f"no approved kit sha on {kit_repo}'s approvals repo; run `ap approve` and merge it first")
    return approved[-1]


def _detect_checks(slug: str) -> list[str]:
    """Names of the repo's own CI checks on its default branch head (everything except autopilot's)."""
    names = _run("gh", "api", f"repos/{slug}/commits/HEAD/check-runs", "--jq", ".check_runs[].name", check=False).split()
    skip = ("guard", "automerge", "dispatch", "handshake", "agent")
    return sorted({n for n in names if not n.lower().startswith(skip)})


def cmd_onboard(ns: argparse.Namespace) -> int:
    """Opt a repo in. Stage 1 opens the scaffold PR (safety checks included). After you merge it, `--finish` applies the ruleset,
    enables the repo and runs preflight. The only manual steps are the ones that must be yours: the token and the App."""
    import tempfile

    pf = load_portfolio()
    slug = _slug(ns.repo, pf["owner"])
    name = slug.split("/")[1]
    kit_repo = ns.kit_repo
    if ns.finish:
        checks = ns.check or _detect_checks(slug)
        print(f"required checks besides guard: {checks or 'none detected (pass --check)'}")
        ruleset_ns = argparse.Namespace(repo=slug, check=checks, central=True, apply=ns.apply)
        if cmd_ruleset(ruleset_ns):
            return 1
        cmd_vars(argparse.Namespace(cmd="enable", repo=name, apply=ns.apply))
        if ns.apply:
            cmd_preflight(argparse.Namespace(repos=[name], verbose=False))
        return 0
    if name not in pf["repos"] and ns.apply:
        if not ns.tier or not ns.mode:
            print(f"{name} is new: pass --tier A|B|C --mode standard|yolo|dormant", file=sys.stderr)
            return 1
        cmd_portfolio(argparse.Namespace(cmd="add", repo=name, tier=ns.tier, mode=ns.mode, enabled="false"))
    sha = ns.sha or _latest_approved(kit_repo)
    if not ns.apply:
        print(f"[dry run] would open a scaffold PR in {slug} pinned to {kit_repo}@{sha[:7]}")
        return 0
    with tempfile.TemporaryDirectory(prefix="ap-onboard-") as td:
        dest = Path(td) / name
        _run("gh", "repo", "clone", slug, str(dest))
        rc = cmd_init(
            argparse.Namespace(
                repo=str(dest), tier=ns.tier, mode=ns.mode, kit=f"{kit_repo}@{sha}", allow_sensitive=False, dry_run=False
            )
        )
        if rc:
            return rc
        _run("git", "add", "-A", cwd=dest)
        _run("git", "commit", "-q", "-S", "-m", "autopilot: scaffold on the shared kit", cwd=dest)
        _run("git", "push", "-q", "-u", "origin", "autopilot/init", "--force-with-lease", cwd=dest)
        url = _run(
            "gh",
            "pr",
            "create",
            "-R",
            slug,
            "--base",
            _run("gh", "repo", "view", slug, "--json", "defaultBranchRef", "--jq", ".defaultBranchRef.name").strip(),
            "--head",
            "autopilot/init",
            "--title",
            "autopilot: scaffold on the shared kit",
            "--body",
            f"Thin caller workflows pinned to `{kit_repo}@{sha}`, plus config, constitution and deny rules. Nothing runs until the repo is enabled.\n\n\U0001f916 Generated with [Claude Code](https://claude.com/claude-code)",
            cwd=dest,
        ).strip()
    secrets = _run("gh", "secret", "list", "-R", slug, check=False)
    print(url)
    print("\nYour steps (nothing else is manual):")
    print(f"  1. review + merge {url}")
    if "CLAUDE_CODE_OAUTH_TOKEN" not in secrets:
        print(
            f'  2. token: run `claude setup-token`, then: read -rs T; gh secret set CLAUDE_CODE_OAUTH_TOKEN -R {slug} --body "$T"; unset T'
        )
    print(f"  3. add {name} to the Claude GitHub App (github.com/settings/installations)")
    print(f"  4. then I run: ap onboard {name} --finish --apply")
    return 0


def cmd_scan(ns: argparse.Namespace) -> int:
    import datetime as dt

    owner = ns.owner or load_portfolio()["owner"]
    fields = "name,isFork,isArchived,isPrivate,pushedAt"
    repos = json.loads(_run("gh", "repo", "list", owner, "--limit", "200", "--json", fields) or "[]")
    print(f"{'repo':32} {'action':8} {'tier':4} {'mode':9} reason")
    for s in scan_suggestions(repos, load_portfolio(), dt.datetime.now(dt.timezone.utc)):
        print(f"{s['name']:32} {s['action']:8} {s['tier']:4} {s['mode']:9} {s['reason']}")
    print("\nread-only. Add a repo with: ap init <local clone> --tier <T> --mode <M>")
    return 0


PF_KEYS = {"tier": list("ABC"), "mode": ["standard", "yolo", "dormant"]}
_PF_LINE = re.compile(r"^\s+[\w.-]+:\s*\{.*\}\s*$")


def _fmt_entry(entry: dict) -> str:
    def v(x):
        return str(x).lower() if isinstance(x, bool) else str(x)

    return "{" + ", ".join(f"{k}: {v(x)}" for k, x in entry.items()) + "}"


def edit_portfolio(text: str, name: str, updates: dict, *, add: bool = False) -> str:
    """Rewrite one flow-style repo line in portfolio.yaml, keeping comments and layout. Pure."""
    for k, v in updates.items():
        if k in PF_KEYS and v not in PF_KEYS[k]:
            raise SystemExit(f"{k} must be one of {PF_KEYS[k]}")
    if not re.fullmatch(r"[\w.-]+", name):
        raise SystemExit(f"bad repo name: {name}")
    lines = text.split("\n")
    pat = re.compile(rf"^(\s+){re.escape(name)}:\s*(\{{.*\}})\s*$")
    for i, ln in enumerate(lines):
        m = pat.match(ln)
        if m:
            if add:
                raise SystemExit(f"{name} is already in the portfolio")
            entry = yaml.safe_load(m.group(2))
            entry.update(updates)
            lines[i] = f"{m.group(1)}{(name + ':').ljust(23)}{_fmt_entry(entry)}"
            return "\n".join(lines)
    if not add:
        raise SystemExit(f"{name} is not in the portfolio (use `ap add`)")
    if name in (yaml.safe_load(text).get("excluded") or []):
        raise SystemExit(f"{name} is excluded in the portfolio")
    last = max(i for i, ln in enumerate(lines) if _PF_LINE.match(ln))
    entry = {"tier": "C", "mode": "dormant", "enabled": False, **updates}
    lines.insert(last + 1, f"  {(name + ':').ljust(23)}{_fmt_entry(entry)}")
    return "\n".join(lines)


def cmd_portfolio(ns: argparse.Namespace) -> int:
    path = POLICY / "portfolio.yaml"
    updates = {k: getattr(ns, k) for k in ("tier", "mode") if getattr(ns, k)}
    if ns.enabled is not None:
        updates["enabled"] = ns.enabled == "true"
    out = edit_portfolio(path.read_text(), ns.repo, updates, add=ns.cmd == "add")
    yaml.safe_load(out)  # never write a file that does not parse
    path.write_text(out)
    print(f"{ns.cmd} {ns.repo}: {updates or 'defaults (C/dormant/disabled)'} -> {path}")
    print("local policy only: nothing was pushed or enabled on GitHub.")
    return 0


KIT_README = """# autopilot-kit

Shared, deterministic building blocks for [autopilot](https://github.com): reusable GitHub Actions workflows and the
zero-token scripts they run (`guard`, `gate`, `handshake`, `config`). Consuming repos hold thin callers that pin this
repo by full commit SHA, so a change here reaches a repo only when its owner merges a PR bumping the SHA.

- `.github/workflows/{exec,dispatch,guard,handshake,automerge,improve,audit}.yml`: `workflow_call` workflows
- `runtime/*.py`: stdlib + PyYAML; no network access, no secrets

Contains no tokens or personal configuration. Never reference it by branch or tag; always by commit SHA.
"""
KIT_FORBIDDEN = [r"RyanJHamby", r"ryanhamby", r"/Users/", r"sk-ant-oat\d*-[A-Za-z0-9_-]{16,}", r"@gmail", r"ampentra"]  # regexes


def export_kit(dest: Path, kit: Path | None = None) -> list[str]:
    """Assemble the public shared-kit tree (reusable workflows + runtime scripts) and refuse if anything personal leaked."""
    subs = {"CHECKOUT_SHA": CHECKOUT_SHA, "ACTION_SHA": ACTION_SHA, "SETUP_NODE_SHA": SETUP_NODE_SHA}
    kit = kit or KIT
    files: dict[str, str] = {"README.md": KIT_README}
    for f in sorted((kit / "workflows").glob("*.yml")):
        files[f".github/workflows/{f.name}"] = render(f.read_text(), subs)
    for f in sorted((kit / "runtime").glob("*.py")):
        files[f"runtime/{f.name}"] = f.read_text()
    for rel, text in files.items():
        for bad in KIT_FORBIDDEN:
            if re.search(bad, text):
                raise SystemExit(f"refusing to export: {rel} contains {bad!r}")
    for rel, text in files.items():
        p = dest / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    return sorted(files)


def cmd_kit(ns: argparse.Namespace) -> int:
    dest = Path(ns.dest).expanduser().resolve()
    if dest.exists() and any(dest.iterdir()):
        print(f"{dest} is not empty; export to a new directory", file=sys.stderr)
        return 1
    for rel in export_kit(dest):
        print(f"  {rel}")
    print(f"\nexported to {dest}. Review every file, then publish by hand (nothing was pushed).")
    return 0


# ---- ap release: kit mirror PR -> approval PR -> rollout; resumable, never merges anything -------------------------------------


class ReleaseError(Exception):
    """Any unreachable API or unexpected answer: release fails closed."""


def _blob_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()  # noqa: S324 - git object id, not security


def _gh_get(path: str):
    r = subprocess.run(["gh", "api", path], capture_output=True, text=True)
    if r.returncode:
        raise ReleaseError(f"GET {path} failed: {r.stderr.strip()[:200]}")
    try:
        return json.loads(r.stdout)
    except ValueError as e:
        raise ReleaseError(f"GET {path} returned non-JSON") from e


def _pr_facts(gh, repo: str, branch: str) -> dict | None:
    """The newest PR whose head is `owner:branch` (any state) as {url, state, merge_sha}; None if there is none."""
    prs = gh(f"repos/{repo}/pulls?state=all&per_page=5&head={repo.split('/')[0]}:{branch}")
    if not isinstance(prs, list):
        raise ReleaseError(f"unexpected pulls answer for {repo}")
    if not prs:
        return None
    pr = prs[0]
    state = "merged" if pr.get("merged_at") else pr.get("state")
    if state not in ("open", "closed", "merged"):
        raise ReleaseError(f"unexpected PR state {state!r} for {pr.get('html_url')}")
    return {"url": pr.get("html_url", ""), "state": state, "merge_sha": pr.get("merge_commit_sha") if state == "merged" else None}


def _remote_tree(gh, repo: str, ref: str, prefix: str = "") -> dict[str, str]:
    t = gh(f"repos/{repo}/git/trees/{ref}?recursive=1")
    if not isinstance(t, dict) or t.get("truncated") or not isinstance(t.get("tree"), list):
        raise ReleaseError(f"tree of {repo}@{ref} unavailable or truncated")
    return {e["path"][len(prefix) :]: e["sha"] for e in t["tree"] if e.get("type") == "blob" and e["path"].startswith(prefix)}


def _local_tree(root: Path) -> dict[str, str]:
    return {str(f.relative_to(root)): _blob_sha(f.read_bytes()) for f in sorted(root.rglob("*")) if f.is_file()}


def publish_tree() -> dict[str, str]:
    """{path in the kit repo: blob sha} of what a release publishes (export_kit of the local kit/)."""
    import tempfile

    with tempfile.TemporaryDirectory(prefix="ap-release-tree-") as td:
        export_kit(Path(td))
        return _local_tree(Path(td))


def main_head_sha(gh, repo: str) -> str:
    """The commit autopilot main points at right now; release pins every later step to it so main cannot move underneath."""
    c = gh(f"repos/{repo}/commits/main")
    sha = c.get("sha") if isinstance(c, dict) else None
    if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ReleaseError(f"cannot resolve {repo}@main to a commit sha")
    return sha


def main_publish_tree(gh, repo: str, ref: str = "main") -> dict[str, str]:
    """What export_kit would publish from kit/ at `repo`@ref: fetch those blobs by REST (each verified against its git sha) and
    run export_kit itself on them, so the comparison uses the real transformation."""
    import base64
    import tempfile

    remote = _remote_tree(gh, repo, ref, "kit/")
    if not remote:
        return {}
    with tempfile.TemporaryDirectory(prefix="ap-release-main-") as td:
        for rel, sha in remote.items():
            if not (rel.startswith("workflows/") or rel.startswith("runtime/")):
                continue
            blob = gh(f"repos/{repo}/git/blobs/{sha}")
            if not isinstance(blob, dict) or blob.get("encoding") != "base64":
                raise ReleaseError(f"blob {sha} unavailable")
            data = base64.b64decode(blob["content"])
            if _blob_sha(data) != sha:
                raise ReleaseError(f"blob {sha} failed its hash check")
            (Path(td) / "kit" / rel).parent.mkdir(parents=True, exist_ok=True)
            (Path(td) / "kit" / rel).write_bytes(data)
        export_kit(Path(td) / "out", kit=Path(td) / "kit")
        return _local_tree(Path(td) / "out")


def gather_release_state(
    ns, gh=_gh_get, *, main_publish: dict | None = None, publish: dict | None = None, check_rollout: bool = True
) -> dict:
    """Read-only facts the planner needs. Raises ReleaseError on any API problem. `publish` is what export_kit makes of the local
    kit/; `main_publish` is what it makes of kit/ at autopilot main; they must match (tamper guard)."""
    kit = ns.kit_repo
    approvals = _load_runtime("automerge").approvals_repo(kit)
    publish = publish_tree() if publish is None else publish
    source = getattr(ns, "source", None) or main_head_sha(
        gh, ns.autopilot_repo
    )  # the autopilot commit exported (recorded as source=)
    if not re.fullmatch(r"[0-9a-f]{40}", source):
        raise ReleaseError("--source must be a 40-hex autopilot commit sha")
    main_publish = main_publish_tree(gh, ns.autopilot_repo, source) if main_publish is None else main_publish
    st: dict = {
        "source": source,
        "tree_ok": bool(main_publish) and main_publish == publish,
        "kit_pr": _pr_facts(gh, kit, ns.branch),
        "kit_merged_tree_ok": None,
        "approved": False,
        "approval_pr": None,
        "rollout_done": False,
        "sha": None,
    }
    pr = st["kit_pr"]
    if not pr or pr["state"] != "merged":
        return st
    sha = pr["merge_sha"]
    if not sha or not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise ReleaseError("merged kit PR has no merge commit sha")
    st["sha"] = sha
    remote = _remote_tree(gh, kit, sha)
    st["kit_merged_tree_ok"] = all(remote.get(p) == h for p, h in publish.items())
    st["approved"] = sha in _load_runtime("automerge").fetch_approved(kit)
    st["approval_pr"] = _pr_facts(gh, approvals, _approve_branch(sha))
    if st["approved"] and check_rollout:  # CI skips this: its token is not installed on the downstream repos
        pf = load_portfolio()
        slugs = [_slug(n, pf["owner"]) for n, _ in rollout_candidates(pf, getattr(ns, "only", None))]
        st["rollout_done"] = all(_pr_facts(gh, slug, _rollout_branch(sha)) is not None for slug in slugs)
    return st


def plan_release(st: dict) -> tuple[str, str]:
    """Pure: state in -> (next action, detail). Actions: open_kit_pr, wait, open_approval_pr, rollout, done, refuse."""
    if not st["tree_ok"]:
        return (
            "refuse",
            "the tree to publish differs from what export_kit makes of autopilot main's kit/ (or that kit/ is empty): refusing to publish",
        )
    pr = st["kit_pr"]
    if pr is None:
        return "open_kit_pr", "mirror kit/ into the kit repo on the release branch and open the kit PR"
    if pr["state"] == "open":
        return "wait", f"kit PR is open; merge it, then re-run: {pr['url']}"
    if pr["state"] == "closed":
        return "refuse", f"kit PR was closed without merging: {pr['url']}; use a new --branch"
    sha = st["sha"]
    if not st["kit_merged_tree_ok"]:
        return "refuse", f"kit repo at {sha[:7]} does not contain the tree this release publishes (tamper guard)"
    if st["approved"]:
        if st["rollout_done"]:
            return "done", f"{sha[:7]} is approved and every target repo has its pin-bump PR"
        return "rollout", f"open pin-bump PRs for {sha[:7]}"
    ap = st["approval_pr"]
    if ap is None:
        return "open_approval_pr", f"open the approval PR for {sha[:7]}"
    if ap["state"] == "open":
        return "wait", f"approval PR is open; merge it (only you), then re-run: {ap['url']}"
    if ap["state"] == "closed":
        return "refuse", f"approval PR was closed without merging: {ap['url']}"
    return "refuse", f"approval PR merged but {sha[:7]} is not on APPROVED (unreadable or edited); not rolling out"


def _release_steps(st: dict) -> list[tuple[str, str]]:
    pr, ap = st["kit_pr"], st["approval_pr"]
    return [
        ("1 kit PR opened", "done" if pr else "todo"),
        ("2 kit PR merged by owner", "done" if pr and pr["state"] == "merged" else "todo"),
        ("3 approval PR opened", "done" if ap or st["approved"] else "todo"),
        ("4 approval PR merged by owner", "done" if st["approved"] else "todo"),
        ("5 rollout PRs opened", "done" if st["rollout_done"] else "todo"),
    ]


def exec_open_kit_pr(ns) -> str:
    """Local clone of the kit repo, signed commit of the publish tree, push the release branch, open the PR. Never merges."""
    import tempfile

    with tempfile.TemporaryDirectory(prefix="ap-release-") as td:
        tree = Path(td) / "tree"
        files = export_kit(tree)
        dest = Path(td) / "kit"
        _run("gh", "repo", "clone", ns.kit_repo, str(dest))
        base = _run("git", "symbolic-ref", "--short", "refs/remotes/origin/HEAD", cwd=dest).strip()
        _run("git", "checkout", "-q", "-B", ns.branch, base, cwd=dest)
        for sub in (".github/workflows", "runtime"):  # managed dirs mirror exactly; other kit-repo files stay
            for old in (dest / sub).glob("*"):
                if old.is_file() and f"{sub}/{old.name}" not in files:
                    old.unlink()
        for rel in files:
            (dest / rel).parent.mkdir(parents=True, exist_ok=True)
            (dest / rel).write_bytes((tree / rel).read_bytes())
        _run("git", "add", "-A", cwd=dest)
        if not _run("git", "status", "--porcelain", cwd=dest).strip():
            return ""
        title = f"release: mirror autopilot kit ({ns.branch})"
        _run("git", "commit", "-q", "-S", "-m", title, cwd=dest)
        _run("git", "push", "-q", "origin", ns.branch, cwd=dest)
        body = "Mirror of `kit/` from autopilot main (exported by `ap release`). Review, then merge it yourself; `ap release` never merges."
        url = _run(
            "gh", "pr", "create", "-R", ns.kit_repo, "--base", base.split("/", 1)[-1],
            "--head", ns.branch, "--title", title, "--body", body, cwd=dest,
        )  # fmt: skip
    return url.strip()


def exec_open_approval_pr(ns, sha: str, source: str) -> int:
    return cmd_approve(argparse.Namespace(kit=f"{ns.kit_repo}@{sha}", note=f"release {ns.branch}", source=source, apply=True))


def exec_rollout(ns, sha: str) -> int:
    return cmd_rollout(argparse.Namespace(kit=f"{ns.kit_repo}@{sha}", only=getattr(ns, "only", []), apply=True))


def cmd_release(ns: argparse.Namespace, gh=_gh_get, executors: dict | None = None) -> int:
    """Print where the release stands and do (with --apply) only the next step. Re-run after each owner merge."""
    ex = {
        "open_kit_pr": exec_open_kit_pr,
        "open_approval_pr": exec_open_approval_pr,
        "rollout": exec_rollout,
        **(executors or {}),
    }
    if getattr(ns, "ci", False):  # GitHub App mode: merges only what it has verified (src/autopilot/release_ci.py)
        from autopilot import release_ci

        return release_ci.run(ns)
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", ns.kit_repo or "") or not re.fullmatch(r"release/[\w.-]+", ns.branch or ""):
        raise SystemExit("--kit-repo must be OWNER/REPO and --branch must be release/NAME")
    try:
        st = gather_release_state(ns, gh)
    except ReleaseError as e:
        print(f"release: failing closed: {e}", file=sys.stderr)
        return 1
    for label, status in _release_steps(st):
        print(f"  [{status}] {label}")
    action, detail = plan_release(st)
    if action == "refuse":
        print(f"release: refusing: {detail}", file=sys.stderr)
        return 1
    if action in ("wait", "done"):
        print(detail)
        return 0
    if not ns.apply:
        print(f"[dry run] next: {detail}")
        return 0
    print(f"next: {detail}")
    if action == "open_kit_pr":
        url = ex[action](ns)
        print(url or "kit repo already matches this tree: nothing to publish (use `ap approve` for an existing sha)")
        return 0
    if action == "open_approval_pr":
        return ex[action](ns, st["sha"], st["source"])
    return ex[action](ns, st["sha"])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="ap", description=__doc__)
    ap.add_argument("--version", action="version", version=VERSION)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init", help="scaffold a local clone (branch autopilot/init, no push)")
    p.add_argument("repo")
    p.add_argument("--tier", choices=list("ABC"))
    p.add_argument("--mode", choices=["standard", "yolo", "dormant"])
    p.add_argument("--kit", metavar="OWNER/REPO@SHA", help="use thin callers into this pinned shared kit")
    p.add_argument("--allow-sensitive", action="store_true", help="override the personal/secret material check")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(fn=cmd_init)
    p = sub.add_parser(
        "upgrade", help="bump only the pinned kit sha in a central repo's callers (branch autopilot/upgrade, no push)"
    )
    p.add_argument("repo")
    p.add_argument("--kit", required=True, metavar="OWNER/REPO@SHA")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(fn=cmd_upgrade)
    p = sub.add_parser("handshake", help="lint a spec: ACCEPTED / NEEDS-WORK / REJECTED")
    p.add_argument("specs", nargs="+")
    p.add_argument("--config", default=".autopilot/repo.yaml")
    p.set_defaults(fn=cmd_handshake)
    p = sub.add_parser("doctor", help="audit installed repos (local files + gh)")
    p.add_argument("repos", nargs="+")
    p.set_defaults(fn=cmd_doctor)
    p = sub.add_parser("scan", help="list an owner's repos with suggested tier/mode (read-only)")
    p.add_argument("--owner")
    p.set_defaults(fn=cmd_scan)
    for c in ("add", "set"):
        p = sub.add_parser(c, help=f"{c} a repo's tier/mode/enabled in policy/portfolio.yaml (local file only)")
        p.add_argument("repo")
        p.add_argument("--tier", choices=PF_KEYS["tier"])
        p.add_argument("--mode", choices=PF_KEYS["mode"])
        p.add_argument("--enabled", choices=["true", "false"])
        p.set_defaults(fn=cmd_portfolio, cmd=c)
    p = sub.add_parser("pick", help="plan the nightly dispatch across repos by priority (dry run unless --apply)")
    p.add_argument("--reserve", type=int, default=0, help="runs to keep back for your interactive use")
    p.add_argument("--apply", action="store_true")
    p.set_defaults(fn=cmd_pick)
    p = sub.add_parser("report", help="read-only outcome scorecard of agent PRs (merge rate, reverts, speed)")
    p.add_argument("--days", type=int, default=14)
    p.add_argument("--min-clean", type=int, default=10, help="clean merges before suggesting auto-merge for a class")
    p.set_defaults(fn=cmd_report)
    p = sub.add_parser("digest", help="read-only markdown summary of the last 24h across enabled repos (no model)")
    p.set_defaults(fn=cmd_digest)
    p = sub.add_parser("retro", help="read-only evidence packet: why agent runs/PRs failed to land")
    p.add_argument("--days", type=int, default=14)
    p.add_argument("--min-count", type=int, default=2)
    p.set_defaults(fn=cmd_retro)
    p = sub.add_parser("approve", help="open a PR on <owner>/autopilot-approved approving a kit sha for automatic pin bumps")
    p.add_argument("--kit", required=True, metavar="OWNER/REPO@SHA")
    p.add_argument("--note", default="")
    p.add_argument("--source", help="autopilot commit the kit was exported from (default: HEAD of this checkout)")
    p.add_argument("--apply", action="store_true")
    p.set_defaults(fn=cmd_approve)
    p = sub.add_parser("provenance", help="read-only: verify the kit tree at SHA is the render of kit/ at an autopilot commit")
    p.add_argument("--kit", required=True, metavar="OWNER/REPO@SHA")
    p.add_argument("--source", help="autopilot commit (default: the source= hint on the kit sha's APPROVED line)")
    p.add_argument("--previous-source", help="previously approved source commit; must be an ancestor of --source")
    p.add_argument("--source-repo", metavar="OWNER/REPO", help="default: <kit owner>/autopilot")
    p.add_argument("--pins", metavar="FILE", help="approved pins.json (default: fetched from the approvals repo)")
    p.set_defaults(fn=cmd_provenance)
    p = sub.add_parser("rollout", help="open pin-bump PRs in every enabled repo for an APPROVED kit sha")
    p.add_argument("--kit", required=True, metavar="OWNER/REPO@SHA")
    p.add_argument("--only", action="append", default=[], help="limit to these repo names")
    p.add_argument("--ci", action="store_true", help="GitHub App mode (ROLLOUT_TOKEN): open the PRs over REST, never merge")
    p.add_argument("--apply", action="store_true")
    p.set_defaults(fn=cmd_rollout)
    p = sub.add_parser("release", help="resumable: kit PR -> approval PR -> rollout; prints the next step, never merges")
    p.add_argument("--kit-repo", required=True, metavar="OWNER/REPO")
    p.add_argument("--branch", metavar="release/NAME", help="required unless --ci (then release/<source[:7]>)")
    p.add_argument("--autopilot-repo", default="RyanJHamby/autopilot")
    p.add_argument("--only", action="append", default=[], help="limit rollout to these repo names")
    p.add_argument("--source", metavar="SHA", help="release this autopilot commit instead of resolving main (CI: $GITHUB_SHA)")
    p.add_argument(
        "--ci", action="store_true", help="GitHub App mode (GH_TOKEN): kit PR, verified merges, approval PR, no rollout"
    )
    p.add_argument("--apply", action="store_true")
    p.set_defaults(fn=cmd_release)
    p = sub.add_parser("onboard", help="opt a repo in: scaffold PR now, ruleset+enable+preflight with --finish")
    p.add_argument("repo")
    p.add_argument("--tier", choices=list("ABC"))
    p.add_argument("--mode", choices=["standard", "yolo", "dormant"])
    p.add_argument("--sha", help="kit sha (default: newest approved)")
    p.add_argument("--kit-repo", default="RyanJHamby/autopilot-kit")
    p.add_argument("--check", action="append", default=[], help="required CI check name (default: detected)")
    p.add_argument("--finish", action="store_true")
    p.add_argument("--apply", action="store_true")
    p.set_defaults(fn=cmd_onboard)
    p = sub.add_parser("preflight", help="read-only readiness check before leaving a repo unattended")
    p.add_argument("repos", nargs="+")
    p.add_argument("-v", "--verbose", action="store_true", help="also list passing checks")
    p.set_defaults(fn=cmd_preflight)
    p = sub.add_parser("kit-fix", help="file a kit-fix issue from a failed run; the kit-proposer workflow drafts a fix PR")
    p.add_argument("title")
    p.add_argument("--run", required=True, metavar="REPO:RUN_ID")
    p.add_argument("--note", default="")
    p.add_argument("--lines", type=int, default=60)
    p.add_argument("--apply", action="store_true")
    p.set_defaults(fn=cmd_kit_fix)
    p = sub.add_parser("export-state", help="write the portfolio snapshot the control-plane UI reads")
    p.add_argument("dest", nargs="?", default=str(ROOT / "apps/control-plane/data/state.json"))
    p.add_argument("--sql", action="store_true", help="print the idempotent seed SQL instead of writing the file")
    p.set_defaults(fn=cmd_export_state)
    p = sub.add_parser("kit-export", help="assemble the public shared-kit tree in a new directory (no push)")
    p.add_argument("dest")
    p.set_defaults(fn=cmd_kit)
    p = sub.add_parser("status", help="runs and agent PRs per enabled repo")
    p.set_defaults(fn=cmd_status)
    p = sub.add_parser("ruleset", help="print/apply the branch ruleset")
    p.add_argument("repo")
    p.add_argument("--check", action="append", default=[], help="extra required check name, e.g. ci")
    p.add_argument("--central", action="store_true", help="repo uses the shared kit (check is named 'guard / guard')")
    p.add_argument("--apply", action="store_true")
    p.set_defaults(fn=cmd_ruleset)
    for c in ("enable", "pause", "resume"):
        p = sub.add_parser(c, help=f"{c}: set repo variable (dry run unless --apply)")
        p.add_argument("repo", nargs="?")
        p.add_argument("--apply", action="store_true")
        p.set_defaults(fn=cmd_vars)
    ns = ap.parse_args(argv)
    return ns.fn(ns)


if __name__ == "__main__":
    sys.exit(main())
