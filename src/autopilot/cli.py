"""`ap`: scaffold, audit and steer autopilot across repos.

Local-only unless a command says otherwise. Anything that changes GitHub (`enable`, `pause`,
`ruleset`) needs an explicit --apply; without it the command prints what it would do.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
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

BASE_TOOLS = [
    "Edit",
    "Write",
    "Read",
    "Glob",
    "Grep",
    "Bash(git add:*)",
    "mcp__github_file_ops__commit_files",  # signed commits via the GitHub API; plain git commit is intentionally absent
    "Bash(git status:*)",
    "Bash(git diff:*)",
    "Bash(git log:*)",
    "Bash(gh pr create:*)",
    "Bash(gh pr view:*)",
    "Bash(gh issue view:*)",
    "Bash(gh issue comment:*)",
    "Bash(gh issue edit:*)",
]
RETIRED = {"Write(.github/**)", "Write(.autopilot/**)", "Write(.claude/**)", "Write(AGENTS.md)", "Write(CLAUDE.md)", "Write(.mcp.json)", "mcp__*", "Bash(git checkout -b agent/*)", "Bash(git commit:*)", "Bash(git push origin agent/*)"}  # kit-owned rules removed from synced repos
STACKS = {  # marker file -> command prefixes
    "pyproject.toml": ["uv run", "uv sync", "pytest", "ruff", "python"],
    "package.json": ["npm test", "npm run"],  # no npx/pnpm: they fetch and run arbitrary registry code
    "Cargo.toml": ["cargo"],
    "pubspec.yaml": ["flutter test", "flutter analyze", "dart"],
    "Makefile": ["make"],
    "CMakeLists.txt": ["cmake", "ctest", "make"],
    "go.mod": ["go test", "go build", "go vet"],
}
RUNTIME_FILES = ["guard.py", "handshake.py", "gate.py"]


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_portfolio() -> dict:
    return yaml.safe_load((POLICY / "portfolio.yaml").read_text())


SKIP_DIRS = {".git", "node_modules", "build", "target", ".venv", "venv", "dist"}


AUTOPILOT_WORKFLOWS = {"agent-dispatch.yml", "agent-exec.yml", "guard.yml", "handshake.yml"}


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
        f"        with:\n          node-version: \"{ver}\"\n          cache: npm\n"
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


def build_settings(existing: dict | None, commands: list[str]) -> dict:
    deny = json.loads((POLICY / "deny.json").read_text())["permissions"]["deny"]
    s = dict(existing or {})
    s.setdefault("$schema", "https://json.schemastore.org/claude-code-settings.json")
    perms = dict(s.get("permissions", {}))
    perms["deny"] = sorted((set(perms.get("deny", [])) | set(deny)) - RETIRED)
    allow = set(perms.get("allow", [])) | set(BASE_TOOLS) | {f"Bash({c}:*)" for c in commands}
    perms["allow"] = sorted(allow - RETIRED)
    s["permissions"] = perms
    return s


def codeowners(owner: str) -> str:
    lines = [f"/{p} @{owner}" for p in (".github/", ".autopilot/", ".claude/", "AGENTS.md", "CLAUDE.md", ".mcp.json")]
    return "# autopilot-managed\n" + "\n".join(lines) + "\n"


def init_repo(repo: Path, tier: str, mode: str, *, dry_run: bool = False) -> list[str]:
    """Write the scaffold into a local clone. Returns the list of paths written/changed."""
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
    for f in (KIT / "repo" / ".github" / "workflows").glob("*.yml"):
        out[f".github/workflows/{f.name}"] = render(f.read_text(), subs)
    for f in (KIT / "repo" / ".github" / "ISSUE_TEMPLATE").glob("*.md"):
        out[f".github/ISSUE_TEMPLATE/{f.name}"] = f.read_text()
    out[".github/pull_request_template.md"] = (KIT / "repo/.github/pull_request_template.md").read_text()
    out[".github/CODEOWNERS"] = codeowners(owner)
    out["specs/_TEMPLATE.md"] = (KIT / "repo/specs/_TEMPLATE.md").read_text()
    out[".autopilot/CONSTITUTION.md"] = (POLICY / "CONSTITUTION.md").read_text()
    out[".autopilot/CONTRACT.md"] = (KIT / "contract/CONTRACT.md").read_text()
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

    settings_path = repo / ".claude" / "settings.json"
    existing = json.loads(settings_path.read_text()) if settings_path.exists() else None
    out[".claude/settings.json"] = json.dumps(build_settings(existing, commands), indent=2) + "\n"
    for rel, content in out.items():
        put(rel, content)
    put(".autopilot/repo.yaml", render((KIT / "repo/.autopilot/repo.yaml.tmpl").read_text(), subs), user_owned=True)

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
    written = init_repo(repo, tier, mode, dry_run=ns.dry_run)
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
    body = ruleset_json(["guard"] + ns.check)
    if not ns.apply:
        print(f"[dry run] would POST to repos/{slug}/rulesets:\n{json.dumps(body, indent=2)}")
        return 0
    r = subprocess.run(
        ["gh", "api", f"repos/{slug}/rulesets", "--method", "POST", "--input", "-"],
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
            print(f"  FAIL {name}: uses repo secrets on pull_request with no agent/* exclusion (an agent PR could read or spend them)")
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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="ap", description=__doc__)
    ap.add_argument("--version", action="version", version=VERSION)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init", help="scaffold a local clone (branch autopilot/init, no push)")
    p.add_argument("repo")
    p.add_argument("--tier", choices=list("ABC"))
    p.add_argument("--mode", choices=["standard", "yolo", "dormant"])
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(fn=cmd_init)
    p = sub.add_parser("handshake", help="lint a spec: ACCEPTED / NEEDS-WORK / REJECTED")
    p.add_argument("specs", nargs="+")
    p.add_argument("--config", default=".autopilot/repo.yaml")
    p.set_defaults(fn=cmd_handshake)
    p = sub.add_parser("doctor", help="audit installed repos (local files + gh)")
    p.add_argument("repos", nargs="+")
    p.set_defaults(fn=cmd_doctor)
    p = sub.add_parser("status", help="runs and agent PRs per enabled repo")
    p.set_defaults(fn=cmd_status)
    p = sub.add_parser("ruleset", help="print/apply the branch ruleset")
    p.add_argument("repo")
    p.add_argument("--check", action="append", default=[], help="extra required check name, e.g. ci")
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
