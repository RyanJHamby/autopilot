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
    assert "Write(.github/**)" not in cli.build_settings({"permissions": {"deny": ["Write(.github/**)"]}}, [])["permissions"]["deny"]


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
