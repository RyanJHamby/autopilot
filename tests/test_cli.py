import json
import re
import subprocess

import yaml

from autopilot import cli


def make_repo(tmp_path, files=None):
    def g(*a):
        subprocess.run(
            ["git", "-c", "commit.gpgsign=false", "-c", "user.email=t@t", "-c", "user.name=t", *a],
            cwd=tmp_path,
            check=True,
            capture_output=True,
        )

    g("init", "-q", "-b", "main")
    for k, v in (files or {"pyproject.toml": "[project]\nname='x'\n"}).items():
        (tmp_path / k).write_text(v)
    g("add", ".")
    g("commit", "-qm", "base")
    return tmp_path


def test_init_writes_scaffold_and_settings(tmp_path):
    repo = make_repo(tmp_path)
    written = cli.init_repo(repo, "A", "standard")
    for rel in [
        ".autopilot/guard.py",
        ".autopilot/gate.py",
        ".autopilot/handshake.py",
        ".autopilot/repo.yaml",
        ".autopilot/CONSTITUTION.md",
        ".github/workflows/agent-exec.yml",
        ".github/workflows/guard.yml",
        ".github/CODEOWNERS",
        ".claude/agents/implementer.md",
        "specs/_TEMPLATE.md",
        "CLAUDE.md",
        "AGENTS.md",
    ]:
        assert (repo / rel).exists(), rel
    assert ".claude/settings.json" in written
    s = json.loads((repo / ".claude/settings.json").read_text())
    assert "mcp__claude_ai_*" in s["permissions"]["deny"] and "Bash(git push --force*)" in s["permissions"]["deny"]
    assert "Bash(uv run:*)" in s["permissions"]["allow"]
    cfg = yaml.safe_load((repo / ".autopilot/repo.yaml").read_text())
    assert cfg["tier"] == "A" and cfg["mode"] == "standard" and cfg["comms"] == "none"
    for wf in (repo / ".github/workflows").glob("*.yml"):
        assert not re.search(r"\{\{[A-Z_]+\}\}", wf.read_text()), wf.name
    assert cli.ACTION_SHA in (repo / ".github/workflows/agent-exec.yml").read_text()


def test_init_is_idempotent_and_preserves_user_content(tmp_path):
    repo = make_repo(tmp_path, {"AGENTS.md": "# mine\n\nrule 1\n", "package.json": "{}"})
    (repo / ".claude").mkdir()
    (repo / ".claude/settings.json").write_text(json.dumps({"model": "sonnet", "permissions": {"deny": ["Bash(rm:*)"]}}))
    cli.init_repo(repo, "B", "standard")
    first = (repo / "AGENTS.md").read_text()
    assert first.startswith("# mine") and "rule 1" in first and cli.BEGIN in first
    s = json.loads((repo / ".claude/settings.json").read_text())
    assert s["model"] == "sonnet" and "Bash(rm:*)" in s["permissions"]["deny"] and "mcp__claude_ai_*" in s["permissions"]["deny"]
    assert cli.init_repo(repo, "B", "standard") == []  # second run changes nothing
    assert (repo / "AGENTS.md").read_text().count(cli.BEGIN) == 1


def test_hand_edited_managed_file_is_not_clobbered(tmp_path):
    repo = make_repo(tmp_path)
    cli.init_repo(repo, "B", "standard")
    wf = repo / ".github/workflows/guard.yml"
    wf.write_text(wf.read_text() + "\n# local tweak\n")
    cli.init_repo(repo, "B", "standard")
    assert "local tweak" in wf.read_text()


def test_repo_yaml_is_user_owned(tmp_path):
    repo = make_repo(tmp_path)
    cli.init_repo(repo, "B", "standard")
    (repo / ".autopilot/repo.yaml").write_text("tier: A\nmode: yolo\n")
    cli.init_repo(repo, "B", "standard")
    assert "yolo" in (repo / ".autopilot/repo.yaml").read_text()


def test_installed_guard_runs_standalone(tmp_path):
    repo = make_repo(tmp_path)
    cli.init_repo(repo, "B", "standard")
    r = subprocess.run(
        ["python3", ".autopilot/handshake.py", "specs/_TEMPLATE.md", "--config", ".autopilot/repo.yaml"],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    assert "HANDSHAKE:" in r.stdout


def test_excluded_and_unknown_repos_refused(tmp_path, capsys):
    ex = tmp_path / "firecracker"
    ex.mkdir()
    make_repo(ex)
    assert cli.main(["init", str(ex), "--dry-run"]) == 1
    unk = tmp_path / "mystery"
    unk.mkdir()
    make_repo(unk)
    assert cli.main(["init", str(unk), "--dry-run"]) == 1


def test_ruleset_forbids_squash_requires_signatures_and_guard():
    rs = cli.ruleset_json(["guard", "ci"])
    kinds = {r["type"] for r in rs["rules"]}
    assert {"required_signatures", "non_fast_forward", "pull_request", "required_status_checks"} <= kinds
    pr = next(r for r in rs["rules"] if r["type"] == "pull_request")["parameters"]
    assert pr["allowed_merge_methods"] == ["merge"] and pr["require_code_owner_review"]
    ctx = [
        c["context"]
        for c in next(r for r in rs["rules"] if r["type"] == "required_status_checks")["parameters"]["required_status_checks"]
    ]
    assert ctx == ["guard", "ci"]


def test_remote_changes_are_dry_run_by_default(capsys):
    assert cli.main(["pause"]) == 0
    out = capsys.readouterr().out
    assert "[dry run]" in out and "AUTOPILOT_PAUSED=true" in out
    assert cli.main(["ruleset", "drillpad"]) == 0
    assert "[dry run]" in capsys.readouterr().out


def test_repo_name_comes_from_remote_not_dir(tmp_path):
    repo = make_repo(tmp_path / "somedir") if (tmp_path / "somedir").mkdir() is None else None
    subprocess.run(
        ["git", "remote", "add", "origin", "https://github.com/RyanJHamby/drillpad-workspace.git"], cwd=repo, check=True
    )
    assert cli.repo_name(repo) == "drillpad-workspace"
    subprocess.run(
        ["git", "remote", "set-url", "origin", "git@github.com:RyanJHamby/order-book-engine.git"], cwd=repo, check=True
    )
    assert cli.repo_name(repo) == "order-book-engine"


def test_runtime_files_opt_out_of_host_repo_linters():
    for name in cli.RUNTIME_FILES:
        head = (cli.KIT / "runtime" / name).read_text().splitlines()[:3]
        assert any(line.startswith("# ruff: noqa") for line in head), name


def test_exec_accepts_owner_or_dispatch_bot_only():
    text = (cli.KIT / "repo/.github/workflows/agent-exec.yml").read_text()
    line = next(ln for ln in text.splitlines() if ln.strip().startswith("if: vars.AUTOPILOT_ENABLED"))
    assert "github.repository_owner" in line and "github-actions[bot]" in line


def test_exec_allows_only_the_actions_bot_and_debug_is_opt_in():
    text = (cli.KIT / "repo/.github/workflows/agent-exec.yml").read_text()
    assert 'allowed_bots: "github-actions"' in text  # never "*"
    assert "show_full_output: ${{ vars.AUTOPILOT_DEBUG == 'true' }}" in text


def test_signed_commit_tool_is_allowed_and_not_denied():
    import json

    wf = (cli.KIT / "repo/.github/workflows/agent-exec.yml").read_text()
    deny = json.loads((cli.ROOT / "policy/deny.json").read_text())["permissions"]["deny"]
    tool = "mcp__github_file_ops__commit_files"
    assert tool in cli.BASE_TOOLS and "Bash(git commit:*)" not in cli.BASE_TOOLS
    assert tool not in wf.split("--disallowedTools")[1] and "mcp__*" not in deny and "mcp__*" not in wf
    assert "mcp__claude_ai_*" in deny and "mcp__claude_ai_*" in wf


def test_sync_drops_retired_rules_from_existing_settings():
    old = {"permissions": {"deny": ["mcp__*"], "allow": ["Bash(git commit:*)", "Bash(git push origin agent/*)", "Read"]}}
    s = cli.build_settings(old, [])
    assert "mcp__*" not in s["permissions"]["deny"]
    assert not {"Bash(git commit:*)", "Bash(git push origin agent/*)"} & set(s["permissions"]["allow"])
    assert "Read" in s["permissions"]["allow"] and "mcp__github_file_ops__commit_files" in s["permissions"]["allow"]


def test_exec_creates_the_branch_in_trusted_code_and_agent_cannot_branch():
    wf = (cli.KIT / "repo/.github/workflows/agent-exec.yml").read_text()
    assert wf.index("create agent branch") < wf.index("claude-code-action")
    assert 'git push origin "$BR"' in wf and "remove empty agent branch" in wf
    assert not any(t.startswith("Bash(git checkout") for t in cli.BASE_TOOLS)


def test_exec_pins_claude_branch_and_cleans_up_via_api():
    wf = (cli.KIT / "repo/.github/workflows/agent-exec.yml").read_text()
    assert "CLAUDE_BRANCH: agent/${{ inputs.issue }}-${{ github.run_id }}" in wf
    assert "git push -q origin --delete" not in wf and "-X DELETE" in wf


def test_no_redundant_write_deny_rules_and_push_retries():
    import json

    deny = json.loads((cli.ROOT / "policy/deny.json").read_text())["permissions"]["deny"]
    assert not [d for d in deny if d.startswith("Write(")] and "Edit(.github/**)" in deny
    assert "for i in 1 2 3; do git push" in (cli.KIT / "repo/.github/workflows/agent-exec.yml").read_text()
    assert (
        "Write(.github/**)" not in cli.build_settings({"permissions": {"deny": ["Write(.github/**)"]}}, [])["permissions"]["deny"]
    )


def test_exec_locks_issue_on_public_repos_before_the_model_runs():
    wf = (cli.KIT / "repo/.github/workflows/agent-exec.yml").read_text()
    assert "if: github.event.repository.private == false" in wf
    assert wf.index("lock issue conversation") < wf.index("claude-code-action")
    assert "ignore every comment whose author is not" in wf


def test_detect_commands_finds_nested_stacks_and_owner_extras(tmp_path):
    (tmp_path / "engine").mkdir()
    (tmp_path / "engine" / "CMakeLists.txt").write_text("project(x)\n")
    (tmp_path / "node_modules" / "pkg").mkdir(parents=True)
    (tmp_path / "node_modules" / "pkg" / "package.json").write_text("{}")
    assert "cmake" in cli.detect_commands(tmp_path) and "npm test" not in cli.detect_commands(tmp_path)
    (tmp_path / ".autopilot").mkdir()
    (tmp_path / ".autopilot" / "repo.yaml").write_text('commands:\n  - "./build/tests/orderbook_tests"\n')
    cmds = cli.detect_commands(tmp_path)
    assert "./build/tests/orderbook_tests" in cmds and cmds.count("cmake") == 1


def _wf(tmp_path, name, body):
    d = tmp_path / ".github" / "workflows"
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(body)


def test_secret_exposed_workflows_flags_pr_jobs_with_secrets_unless_agent_excluded(tmp_path):
    _wf(
        tmp_path,
        "eval.yml",
        "on:\n  pull_request:\njobs:\n  a:\n    steps:\n      - run: x\n        env:\n          K: ${{ secrets.OPENAI_API_KEY }}\n",
    )
    _wf(
        tmp_path,
        "safe.yml",
        "on:\n  pull_request:\njobs:\n  a:\n    if: ${{ !startsWith(github.head_ref, 'agent/') }}\n    env:\n      K: ${{ secrets.OPENAI_API_KEY }}\n",
    )
    _wf(tmp_path, "tokenonly.yml", "on:\n  pull_request:\njobs:\n  a:\n    env:\n      K: ${{ secrets.GITHUB_TOKEN }}\n")
    _wf(tmp_path, "pushonly.yml", "on:\n  push:\njobs:\n  a:\n    env:\n      K: ${{ secrets.DEPLOY }}\n")
    _wf(tmp_path, "agent-exec.yml", "on:\n  pull_request:\nenv: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}\n")
    assert cli.secret_exposed_workflows(tmp_path) == ["eval.yml"]


def test_exec_scrubs_subprocess_env_and_npx_is_not_allowed():
    wf = (cli.KIT / "repo/.github/workflows/agent-exec.yml").read_text()
    assert 'CLAUDE_CODE_SUBPROCESS_ENV_SCRUB: "1"' in wf
    assert "npx" not in cli.STACKS["package.json"]


def test_node_repos_get_pinned_trusted_install_steps_and_others_do_not(tmp_path):
    (tmp_path / "n").mkdir()
    (tmp_path / "p").mkdir()
    n = make_repo(tmp_path / "n", {"package.json": '{"name":"x"}', "package-lock.json": "{}", ".nvmrc": "v22.1.0\n"})
    p = make_repo(tmp_path / "p")
    cli.init_repo(n, "A", "standard")
    cli.init_repo(p, "A", "standard")
    wn = (n / ".github/workflows/agent-exec.yml").read_text()
    wp = (p / ".github/workflows/agent-exec.yml").read_text()
    assert f"actions/setup-node@{cli.SETUP_NODE_SHA}" in wn and 'node-version: "22"' in wn
    assert "npm ci --ignore-scripts" in wn and wn.index("npm ci") < wn.index("claude-code-action")
    assert "setup-node" not in wp and "{{" not in wp.replace("${{", "")
    yaml.safe_load(wn)
    yaml.safe_load(wp)


def test_existing_owner_files_are_kept_and_codeowners_is_merged(tmp_path):
    repo = make_repo(tmp_path)
    (repo / ".github").mkdir()
    (repo / ".github" / "pull_request_template.md").write_text("MY TEMPLATE\n")
    (repo / ".github" / "CODEOWNERS").write_text("* @me\n/docs/ @someone\n")
    cli.init_repo(repo, "A", "standard")
    assert (repo / ".github/pull_request_template.md").read_text() == "MY TEMPLATE\n"
    co = (repo / ".github/CODEOWNERS").read_text()
    assert co.startswith("* @me\n/docs/ @someone\n") and "/.github/ @" in co
    cli.init_repo(repo, "A", "standard")  # idempotent: block replaced, not duplicated
    assert (repo / ".github/CODEOWNERS").read_text().count(cli.CO_BEGIN) == 1


def _repo(name, **kw):
    base = {"name": name, "isFork": False, "isArchived": False, "isPrivate": True, "pushedAt": "2026-10-10T00:00:00Z"}
    return {**base, **kw}


def test_scan_suggests_tiers_and_never_tier_a():
    import datetime as dt

    now = dt.datetime(2026, 10, 16, tzinfo=dt.timezone.utc)
    pf = {"repos": {"stencil": {"tier": "A"}}, "excluded": ["vllm"]}
    out = {
        s["name"]: s
        for s in cli.scan_suggestions(
            [
                _repo("stencil"),
                _repo("fresh"),
                _repo("warm", pushedAt="2026-06-01T00:00:00Z"),
                _repo("old", pushedAt="2025-01-01T00:00:00Z"),
                _repo("forked", isFork=True),
                _repo("gone", isArchived=True),
                _repo("vllm"),
                _repo("pub", isPrivate=False),
            ],
            pf,
            now,
        )
    }
    assert out["stencil"]["action"] == "managed"
    assert (out["fresh"]["action"], out["fresh"]["tier"], out["fresh"]["mode"]) == ("add", "B", "standard")
    assert (out["warm"]["action"], out["warm"]["tier"], out["warm"]["mode"]) == ("add", "C", "dormant")
    assert out["old"]["action"] == "skip" and "stale" in out["old"]["reason"]
    assert out["forked"]["action"] == "skip" and out["gone"]["action"] == "skip" and out["vllm"]["action"] == "skip"
    assert "public" in out["pub"]["reason"] and out["pub"]["mode"] == "dormant"
    assert all(s["tier"] != "A" for s in out.values() if s["action"] == "add")


def _load_config_module():
    import importlib.util

    spec = importlib.util.spec_from_file_location("kit_config", cli.KIT / "runtime" / "config.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_runtime_config_node_and_tools(tmp_path):
    cfgmod = _load_config_module()
    (tmp_path / "package-lock.json").write_text("{}")
    assert cfgmod.node_version(tmp_path, {}) == "20"
    (tmp_path / ".nvmrc").write_text("v22.4.0\n")
    assert cfgmod.node_version(tmp_path, {}) == "22"
    assert cfgmod.node_version(tmp_path, {"stack": {"node": "18"}}) == "18"
    assert cfgmod.node_version(tmp_path / "nolock", {}) == ""
    tools = cfgmod.allowed_tools({"commands": ["npm test", "npm run"]}).split(",")
    assert "Bash(npm test:*)" in tools and "mcp__github_file_ops__commit_files" in tools
    assert not any("git commit" in t or "git push" in t for t in tools)


def test_runtime_config_rejects_unsafe_commands():
    import pytest

    cfgmod = _load_config_module()
    for bad in ['npm test", "--dangerously', "npm test; curl x", "$(id)", "a,b"]:
        with pytest.raises(SystemExit):
            cfgmod.allowed_tools({"commands": [bad]})
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "package-lock.json").write_text("{}")
        with pytest.raises(SystemExit):
            cfgmod.node_version(Path(d), {"stack": {"node": "x; rm"}})


def test_cli_and_runtime_share_base_tools():
    assert _load_config_module().BASE_TOOLS == cli.BASE_TOOLS


KIT_SHA = "a" * 40


def test_central_init_writes_pinned_callers_and_no_vendored_scripts(tmp_path):
    repo = make_repo(tmp_path, {"package.json": "{}", "package-lock.json": "{}"})
    cli.init_repo(repo, "A", "standard", central=("acme/autopilot-kit", KIT_SHA))
    for n in ("agent-exec", "agent-dispatch", "guard", "handshake", "automerge"):
        t = (repo / f".github/workflows/{n}.yml").read_text()
        assert "uses: acme/autopilot-kit/.github/workflows/" in t and f"@{KIT_SHA}" in t
        assert "{{" not in t.replace("${{", "")
        yaml.safe_load(t)
    for gone in ("guard.py", "gate.py", "handshake.py"):
        assert not (repo / ".autopilot" / gone).exists()
    assert (repo / ".autopilot/repo.yaml").exists() and (repo / ".autopilot/CONSTITUTION.md").exists()
    assert (repo / ".claude/settings.json").exists()


def test_migration_to_central_removes_only_untouched_vendored_scripts(tmp_path):
    repo = make_repo(tmp_path)
    cli.init_repo(repo, "A", "standard")
    assert (repo / ".autopilot/gate.py").exists()
    (repo / ".autopilot/guard.py").write_text("# edited by hand\n")
    written = cli.init_repo(repo, "A", "standard", central=("acme/autopilot-kit", KIT_SHA))
    assert not (repo / ".autopilot/gate.py").exists() and (repo / ".autopilot/guard.py").exists()
    assert ".autopilot/gate.py (removed)" in written


def test_reusable_workflows_are_wellformed_and_pinned():
    for f in sorted((cli.KIT / "workflows").glob("*.yml")):
        t = cli.render(
            f.read_text(), {"CHECKOUT_SHA": cli.CHECKOUT_SHA, "ACTION_SHA": cli.ACTION_SHA, "SETUP_NODE_SHA": cli.SETUP_NODE_SHA}
        )
        d = yaml.safe_load(t)
        assert "workflow_call" in d[True], f.name  # PyYAML parses the bare key `on` as True
        assert "{{" not in t.replace("${{", ""), f.name
        for ref in re.findall(r"uses:\s*\S+@(\S+)", t):
            assert len(ref) == 40, (f.name, ref)


def test_central_ruleset_check_name(capsys):
    assert cli.main(["ruleset", "x", "--central"]) == 0
    assert '"guard / guard"' in capsys.readouterr().out
    assert cli.main(["ruleset", "x"]) == 0
    assert '"guard / guard"' not in capsys.readouterr().out


def test_kit_export_tree_and_leak_check(tmp_path):
    files = cli.export_kit(tmp_path / "kit")
    assert files == [
        ".github/workflows/automerge.yml",
        ".github/workflows/dispatch.yml",
        ".github/workflows/exec.yml",
        ".github/workflows/guard.yml",
        ".github/workflows/handshake.yml",
        "README.md",
        "runtime/automerge.py",
        "runtime/config.py",
        "runtime/demote.py",
        "runtime/gate.py",
        "runtime/guard.py",
        "runtime/handshake.py",
        "runtime/patchcheck.py",
        "runtime/runner.py",
        "runtime/tier.py",
    ]
    blob = "".join(p.read_text() for p in (tmp_path / "kit").rglob("*") if p.is_file())
    assert not any(re.search(b, blob) for b in cli.KIT_FORBIDDEN)


def test_kit_export_refuses_personal_strings(tmp_path, monkeypatch):
    import pytest

    monkeypatch.setattr(cli, "KIT_README", "contact ryanhamby22 for help")
    with pytest.raises(SystemExit):
        cli.export_kit(tmp_path / "kit")
    assert not (tmp_path / "kit").exists()


PF_SAMPLE = """repos:
  # --- wave 1 ---
  alpha:                   {tier: A, mode: standard, enabled: true}
  stencil:                 {tier: C, mode: dormant, enabled: false}

excluded:
  - vllm
"""


def test_edit_portfolio_set_keeps_layout():
    out = cli.edit_portfolio(PF_SAMPLE, "stencil", {"tier": "A", "mode": "standard", "enabled": True})
    assert "# --- wave 1 ---" in out and "excluded:" in out
    assert cli.yaml.safe_load(out)["repos"]["stencil"] == {"tier": "A", "mode": "standard", "enabled": True}
    assert cli.yaml.safe_load(out)["repos"]["alpha"]["tier"] == "A"


def test_edit_portfolio_add_defaults_dormant():
    out = cli.edit_portfolio(PF_SAMPLE, "beta", {}, add=True)
    assert cli.yaml.safe_load(out)["repos"]["beta"] == {"tier": "C", "mode": "dormant", "enabled": False}


def test_edit_portfolio_refuses_bad_input():
    import pytest

    for args, kw in [
        (("alpha", {}), {"add": True}),  # duplicate
        (("vllm", {}), {"add": True}),  # excluded
        (("nope", {"tier": "A"}), {}),  # set on unknown
        (("alpha", {"tier": "Z"}), {}),  # bad tier
        (("a b", {}), {"add": True}),  # bad name
    ]:
        with pytest.raises(SystemExit):
            cli.edit_portfolio(PF_SAMPLE, *args, **kw)


def test_init_writes_empty_merge_policy(tmp_path):
    repo = tmp_path / "r"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    cli.init_repo(repo, "B", "standard")
    pol = cli.yaml.safe_load((repo / ".autopilot" / "merge-policy.yaml").read_text())
    assert pol["auto_merge_classes"] == []


def test_export_state_shape():
    import datetime as dt

    out = cli.export_state(cli.load_portfolio(), dt.datetime(2026, 10, 16, tzinfo=dt.timezone.utc))
    r = {x["name"]: x for x in out["repos"]}
    assert r["stencil"]["hold_until"] and r["stencil"]["priority"] == 8
    assert all(set(x) == {"name", "tier", "mode", "enabled", "priority", "hold_until", "public"} for x in out["repos"])


def test_state_sql_is_idempotent_and_quotes():
    import datetime as dt

    st = cli.export_state(cli.load_portfolio(), dt.datetime(2026, 10, 16, tzinfo=dt.timezone.utc))
    sql = cli.state_sql(st)
    assert sql.count("insert into projects") == len(st["repos"])
    assert "on conflict (org_id, repo) do update" in sql and "'RyanJHamby/stencil'" in sql
    st["repos"][0]["name"] = "x'; drop table projects; --"
    import pytest

    with pytest.raises(SystemExit):
        cli.state_sql(st)


def test_sensitive_findings_flags_personal_and_secret_material(tmp_path):
    repo = make_repo(tmp_path, {"README.md": "x", "app.py": "x"})
    assert cli.sensitive_findings(repo) == []
    (repo / ".obsidian").mkdir()
    (repo / "notes").mkdir()
    (repo / "notes" / "journal-2026.md").write_text("private")
    (repo / "keys.pem").write_text("x")
    (repo / ".env").write_text("A=1")
    (repo / ".env.example").write_text("A=")
    found = " ".join(cli.sensitive_findings(repo))
    assert ".obsidian" in found and "journal-2026.md" in found and "keys.pem" in found and ".env" in found
    assert ".env.example" not in found


def test_sensitive_findings_never_paths(tmp_path):
    repo = make_repo(tmp_path)
    assert cli.sensitive_findings(repo, never_paths=[str(tmp_path)])  # repo lives under an off-limits dir


def test_init_refuses_sensitive_and_restricted(tmp_path, capsys):
    repo = make_repo(tmp_path)
    (repo / "journal.md").write_text("dear diary")
    assert cli.main(["init", str(repo), "--tier", "B", "--mode", "standard", "--dry-run"]) == 1
    assert "journal.md" in capsys.readouterr().err
    assert cli.main(["init", str(repo), "--tier", "B", "--mode", "standard", "--dry-run", "--allow-sensitive"]) == 0


def test_portfolio_declares_never_paths():
    pf = cli.load_portfolio()
    assert "~/notes" in pf["never_paths"] and "~/Desktop/claude-docs" in pf["never_paths"]


def test_extra_protected_reaches_codeowners_and_deny(tmp_path):
    repo = make_repo(tmp_path)
    (repo / ".autopilot").mkdir()
    (repo / ".autopilot" / "repo.yaml").write_text(
        "guard:\n  extra_protected:\n    - kit/runtime/**\n    - 'bad path; rm'\n    - policy/**\n"
    )
    assert cli._extra_protected(repo) == ["kit/runtime/**", "policy/**"]
    co = cli.codeowners("me", None, cli._extra_protected(repo))
    assert "/kit/runtime/ @me" in co and "/policy/ @me" in co
    deny = cli.build_settings(None, [], cli._extra_protected(repo))["permissions"]["deny"]
    assert "Edit(kit/runtime/**)" in deny and "Edit(policy/**)" in deny
    cli.init_repo(repo, "B", "standard")
    assert "/kit/runtime/ @" in (repo / ".github/CODEOWNERS").read_text()


def test_exec_installs_bubblewrap_before_the_agent_and_keeps_the_scrub():
    wf = (cli.KIT / "workflows/exec.yml").read_text()
    assert "bubblewrap socat" in wf and wf.index("bubblewrap") < wf.index("claude-code-action@")
    assert 'CLAUDE_CODE_SUBPROCESS_ENV_SCRUB: "1"' in wf


def test_exec_fails_loudly_when_the_agent_step_was_skipped():
    wf = (cli.KIT / "workflows/exec.yml").read_text()
    assert "id: agent" in wf and "steps.agent.outputs.execution_file == ''" in wf


def test_sensitive_names_are_whole_stems_not_substrings():
    for ok in [
        "src/health-checker-circuit.py",
        "lessons/07-secrets-and-key-management.md",
        "docs/taxonomy.md",
        "README.md",
        ".env.example",
    ]:
        assert not cli._sensitive_name(ok), ok
    for bad in [
        "journal.md",
        "notes/journal-2026-10.md",
        "secrets.json",
        "keys.pem",
        ".env",
        ".env.local",
        "Medical.PDF".lower(),
    ]:
        assert cli._sensitive_name(bad) or bad == "medical.pdf", bad
    assert cli._sensitive_name("medical.pdf")


def test_uv_detected_and_exec_prepares_python_deps(tmp_path):
    rc = cli._runtime_config()
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n")
    assert rc.uses_uv(tmp_path) == ""
    (tmp_path / "uv.lock").write_text("")
    assert rc.uses_uv(tmp_path) == "true"
    wf = (cli.KIT / "workflows/exec.yml").read_text()
    assert "uv sync --frozen" in wf and "uv==0.12.16" in wf
    assert wf.index("uv sync --frozen") < wf.index("claude-code-action@")


def test_implementer_infers_acceptance_instead_of_stopping():
    role = (cli.KIT / "agents/implementer.md").read_text()
    assert "INFER" in role and "Inferred acceptance" in role and "[inferred tests]" in role
    assert "stop and add `needs-human`" not in role.split("2. Write")[0]
    assert "infer them" in (cli.KIT / "workflows/exec.yml").read_text()


def test_rollout_refuses_unapproved_sha_and_dry_runs_approved(monkeypatch, capsys):
    sha = "d" * 40
    am = cli._load_runtime("automerge")
    monkeypatch.setattr(am, "fetch_approved", lambda kit: [])
    monkeypatch.setattr(cli, "_load_runtime", lambda n: am)
    assert cli.main(["rollout", "--kit", f"me/kit@{sha}"]) == 1
    assert "not on me/kit's APPROVED list" in capsys.readouterr().err
    monkeypatch.setattr(am, "fetch_approved", lambda kit: [sha])
    assert cli.main(["rollout", "--kit", f"me/kit@{sha}", "--only", "drillpad-workspace"]) == 0
    out = capsys.readouterr().out
    assert "[dry run]" in out and "drillpad-workspace" in out and "stencil" not in out


def test_approve_dry_run_prints_the_line(monkeypatch, capsys):
    sha = "e" * 40
    monkeypatch.setattr(cli.subprocess, "run", lambda *a, **k: type("R", (), {"returncode": 1, "stdout": "", "stderr": ""})())
    assert cli.main(["approve", "--kit", f"me/kit@{sha}", "--note", "canary green"]) == 0
    assert f"{sha}  canary green" in capsys.readouterr().out


def test_exec_flags_runs_with_no_pr_and_no_blocker():
    wf = (cli.KIT / "workflows/exec.yml").read_text()
    assert "neither a PR nor a blocker" in wf and "needs-human" in wf
    assert wf.index("neither a PR nor a blocker") < wf.index("remove empty agent branch")


NEW_SHA = "b" * 40
KIT_SLUG = "acme/autopilot-kit"
CALLERS = ("agent-exec", "agent-dispatch", "guard", "handshake", "automerge")


def _git(repo, *a):
    return subprocess.run(
        ["git", "-c", "commit.gpgsign=false", "-c", "user.email=t@t", "-c", "user.name=t", *a],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def _central_repo(tmp_path):
    repo = make_repo(tmp_path)
    cli.init_repo(repo, "A", "standard", central=(KIT_SLUG, KIT_SHA))
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "init")
    return repo


def test_upgrade_bumps_only_the_kit_sha_in_callers(tmp_path):
    repo = _central_repo(tmp_path)
    before = {n: (repo / f".github/workflows/{n}.yml").read_text() for n in CALLERS}
    repo_yaml = (repo / ".autopilot/repo.yaml").read_text()
    policy = (repo / ".autopilot/merge-policy.yaml").read_text()
    assert cli.main(["upgrade", str(repo), "--kit", f"{KIT_SLUG}@{NEW_SHA}"]) == 0
    for n in CALLERS:
        after = (repo / f".github/workflows/{n}.yml").read_text()
        assert after == before[n].replace(KIT_SHA, NEW_SHA) and KIT_SHA not in after
    assert (repo / ".autopilot/repo.yaml").read_text() == repo_yaml
    assert (repo / ".autopilot/merge-policy.yaml").read_text() == policy
    changed = sorted(line[3:] for line in _git(repo, "status", "--porcelain").splitlines())
    assert changed == sorted(f".github/workflows/{n}.yml" for n in CALLERS)
    assert _git(repo, "branch", "--show-current").strip() == "autopilot/upgrade"


def test_upgrade_refuses_a_hand_edited_caller_and_changes_nothing(tmp_path, capsys):
    repo = _central_repo(tmp_path)
    guard = repo / ".github/workflows/guard.yml"
    guard.write_text(guard.read_text() + "# my tweak\n")
    _git(repo, "commit", "-qam", "tweak")
    assert cli.main(["upgrade", str(repo), "--kit", f"{KIT_SLUG}@{NEW_SHA}"]) == 1
    assert "guard.yml" in capsys.readouterr().err
    assert KIT_SHA in (repo / ".github/workflows/agent-exec.yml").read_text()
    assert NEW_SHA not in guard.read_text()
    assert _git(repo, "status", "--porcelain") == ""
    assert _git(repo, "branch", "--show-current").strip() == "main"


def test_upgrade_refuses_a_repo_that_is_not_central(tmp_path, capsys):
    repo = make_repo(tmp_path)
    cli.init_repo(repo, "A", "standard")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "init")
    assert cli.main(["upgrade", str(repo), "--kit", f"{KIT_SLUG}@{NEW_SHA}"]) == 1
    assert "central" in capsys.readouterr().err


def test_upgrade_refuses_a_different_kit_repo_and_a_bad_kit_spec(tmp_path):
    repo = _central_repo(tmp_path)
    assert cli.main(["upgrade", str(repo), "--kit", f"other/kit@{NEW_SHA}"]) == 1
    assert cli.main(["upgrade", str(repo), "--kit", f"{KIT_SLUG}@main"]) == 1
    assert KIT_SHA in (repo / ".github/workflows/guard.yml").read_text()


def test_upgrade_dry_run_writes_nothing(tmp_path):
    repo = _central_repo(tmp_path)
    assert cli.main(["upgrade", str(repo), "--kit", f"{KIT_SLUG}@{NEW_SHA}", "--dry-run"]) == 0
    assert KIT_SHA in (repo / ".github/workflows/guard.yml").read_text()
    assert _git(repo, "branch", "--show-current").strip() == "main"


def test_implementer_never_ends_with_a_background_command_running():
    role = (cli.KIT / "agents/implementer.md").read_text()
    assert "Never end your turn while a command is still running" in role and "left to CI" in role
    assert "background" in (cli.KIT / "workflows/exec.yml").read_text()
