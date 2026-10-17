import json
from pathlib import Path

import yaml

from autopilot import cli

ROOT = Path(__file__).resolve().parents[1]
WF = yaml.safe_load((ROOT / ".github/workflows/kit-proposer.yml").read_text())
ST = json.loads((ROOT / ".github/kit-proposer-settings.json").read_text())


def test_trigger_is_owner_only_and_label_scoped():
    job = WF["jobs"]["propose"]
    assert WF[True]["issues"]["types"] == ["labeled"]
    assert "github.event.label.name == 'kit-fix'" in job["if"] and "github.actor == github.repository_owner" in job["if"]
    assert "AUTOPILOT_PAUSED" in job["if"]


def test_it_can_propose_but_never_merge_or_push():
    text = (ROOT / ".github/workflows/kit-proposer.yml").read_text()
    assert "gh pr merge" in text.split("--disallowedTools")[1] and "git push:*" in text.split("--disallowedTools")[1]
    allow = ST["permissions"]["allow"]
    assert not any("merge" in a or "gh api" in a for a in allow)
    assert "Edit(.github/**)" not in allow and not any(a.startswith("Edit(policy") for a in allow)


def test_edit_rights_are_exactly_the_allowed_paths_and_the_guard_path_is_denied():
    allow = {a for a in ST["permissions"]["allow"] if a.startswith("Edit(")}
    assert allow == {"Edit(kit/**)", "Edit(src/autopilot/**)", "Edit(tests/**)", "Edit(docs/journal.md)"}
    deny = set(ST["permissions"]["deny"])
    for p in (
        ".github/**",
        ".claude/**",
        ".autopilot/**",
        "policy/**",
        "apps/control-plane/lib/auth.ts",
        "apps/control-plane/supabase/**",
        "CODEOWNERS",
    ):
        assert f"Edit({p})" in deny and f"Write({p})" in deny, p
    assert "Bash(git push *)" in deny and "Bash(gh pr merge *)" in deny


def test_a_trusted_step_rechecks_the_pr_paths_and_closes_it_on_violation():
    steps = {s["name"]: s for s in WF["jobs"]["propose"]["steps"] if "name" in s}
    chk = next(v for k, v in steps.items() if k.startswith("trusted path check"))
    assert "gh pr close" in chk["run"] and "kit/|src/autopilot/|tests/|docs/journal" in chk["run"] and chk["if"] == "always()"


def test_settings_are_swapped_in_the_working_tree_only():
    step = next(s for s in WF["jobs"]["propose"]["steps"] if s.get("name", "").startswith("proposer settings"))
    assert "kit-proposer-settings.json .claude/settings.json" in step["run"]


def test_redact_strips_key_shaped_text():
    # built at runtime so this file never contains a literal key-shaped string (the guard's secret scan would flag it)
    gh_tok = "gh" + "p_" + "abcdefghijklmnop1234"
    ant_key = "sk" + "-ant-" + "oat01-abcdefgh12345678"
    t = f"token {gh_tok} and {ant_key} and Authorization: Bearer abcdef123456 ok"
    out = cli.redact(t)
    assert gh_tok not in out and ant_key not in out and "abcdef123456" not in out and "ok" in out


def test_kit_fix_dry_run_needs_a_valid_run_and_prints(monkeypatch, capsys):
    assert cli.main(["kit-fix", "t", "--run", "nonsense"]) == 1
    monkeypatch.setattr(
        cli.subprocess, "run", lambda *a, **k: type("R", (), {"returncode": 0, "stdout": "a\nb\nfailed here", "stderr": ""})()
    )
    assert cli.main(["kit-fix", "Fix the thing", "--run", "stencil:123", "--note", "denied tsc"]) == 0
    out = capsys.readouterr().out
    assert "[dry run]" in out and "failed here" in out and "denied tsc" in out
