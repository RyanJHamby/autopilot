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


AUTOPILOT_WORKFLOWS = {"agent-dispatch.yml", "agent-exec.yml", "guard.yml", "handshake.yml", "automerge.yml"}


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


CO_BEGIN, CO_END = "# BEGIN autopilot", "# END autopilot"
MERGED_FILES = {".claude/settings.json", ".github/CODEOWNERS"}  # merged into what is there; every other existing file is kept


def codeowners(owner: str, existing: str | None = None) -> str:
    """CODEOWNERS with a managed block for the protected paths. Anything already in the file is kept."""
    lines = [f"/{p} @{owner}" for p in (".github/", ".autopilot/", ".claude/", "AGENTS.md", "CLAUDE.md", ".mcp.json")]
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
    co = repo / ".github" / "CODEOWNERS"
    out[".github/CODEOWNERS"] = codeowners(owner, co.read_text() if co.exists() else None)
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
    out[".claude/settings.json"] = json.dumps(build_settings(existing, commands), indent=2) + "\n"
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
        if not e.get("enabled") or e.get("mode") == "dormant":
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

- `.github/workflows/{exec,dispatch,guard,handshake,automerge}.yml`: `workflow_call` workflows
- `runtime/*.py`: stdlib + PyYAML; no network access, no secrets

Contains no tokens or personal configuration. Never reference it by branch or tag; always by commit SHA.
"""
KIT_FORBIDDEN = [r"RyanJHamby", r"ryanhamby", r"/Users/", r"sk-ant-oat\d*-[A-Za-z0-9_-]{16,}", r"@gmail", r"ampentra"]  # regexes


def export_kit(dest: Path) -> list[str]:
    """Assemble the public shared-kit tree (reusable workflows + runtime scripts) and refuse if anything personal leaked."""
    subs = {"CHECKOUT_SHA": CHECKOUT_SHA, "ACTION_SHA": ACTION_SHA, "SETUP_NODE_SHA": SETUP_NODE_SHA}
    files: dict[str, str] = {"README.md": KIT_README}
    for f in sorted((KIT / "workflows").glob("*.yml")):
        files[f".github/workflows/{f.name}"] = render(f.read_text(), subs)
    for f in sorted((KIT / "runtime").glob("*.py")):
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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="ap", description=__doc__)
    ap.add_argument("--version", action="version", version=VERSION)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init", help="scaffold a local clone (branch autopilot/init, no push)")
    p.add_argument("repo")
    p.add_argument("--tier", choices=list("ABC"))
    p.add_argument("--mode", choices=["standard", "yolo", "dormant"])
    p.add_argument("--kit", metavar="OWNER/REPO@SHA", help="use thin callers into this pinned shared kit")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(fn=cmd_init)
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
