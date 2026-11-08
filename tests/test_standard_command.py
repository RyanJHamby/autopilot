"""`ap standard check` and waivers: exit codes, finding clones by origin name, and base-ref waivers."""

import json
import subprocess
from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from test_engine import FULL_OWNERS, GOOD_WF, git_repo, write

from autopilot import cli
from autopilot.standard import command, engine, waivers

TODAY = date(2026, 11, 3)


def git(root, *args):
    subprocess.run(
        ["git", "-c", "commit.gpgsign=false", "-c", "user.email=t@t", "-c", "user.name=t", *args],
        cwd=root,
        check=True,
        capture_output=True,
    )


def clone(root, name, origin=None, files=None):
    """A git repo in `root/name` whose origin remote says it is the GitHub repo `origin` (default: the same name)."""
    d = root / name
    d.mkdir(parents=True)
    git_repo(d, files)
    git(d, "remote", "add", "origin", f"https://github.com/o/{origin or name}.git")
    return d


CLEAN = {
    ".github/workflows/ci.yml": GOOD_WF,
    "CODEOWNERS": FULL_OWNERS,
    "CLAUDE.md": "@AGENTS.md\n",
    "Makefile": "check:\n\ttrue\n",
}


@pytest.fixture
def portfolio(monkeypatch):
    pf = {"owner": "o", "repos": {}}
    monkeypatch.setattr(cli, "load_portfolio", lambda: pf)
    return pf["repos"]


def run(tmp_path, *args):
    return cli.main(["standard", "check", "--offline", *args])


# --- waivers: parsing -------------------------------------------------------------------------------------------


def entry(**kw):
    return {
        "repo": "r",
        "rule": "license-present",
        "owner": "me",
        "reason": "why",
        "granted": TODAY,
        "expires": TODAY + timedelta(days=10),
        **kw,
    }


def parsed(*entries):
    import yaml

    return waivers.parse(yaml.safe_dump({"waivers": list(entries)}))


def test_a_complete_waiver_is_valid():
    valid, notes = parsed(entry())
    assert len(valid) == 1 and notes == []


@pytest.mark.parametrize(
    ("bad", "why"),
    [
        (entry(owner=""), "missing owner"),
        (entry(rule="no-such-rule"), "unknown rule"),
        (entry(expires=TODAY + timedelta(days=31)), "the maximum is 30"),
        (entry(expires=TODAY), "not after granted"),
        (entry(expires="soon"), "must be dates"),
    ],
)
def test_an_invalid_waiver_is_ignored_and_says_why(bad, why):
    valid, notes = parsed(bad)
    assert valid == [] and why in notes[0]


def test_thirty_days_is_allowed_and_thirty_one_is_not():
    assert parsed(entry(expires=TODAY + timedelta(days=30)))[0]
    assert not parsed(entry(expires=TODAY + timedelta(days=31)))[0]


@pytest.mark.parametrize("text", ["waivers: [", "waivers: nope", "- a\n- b\n"])
def test_a_waivers_file_that_is_broken_grants_nothing(text):
    valid, notes = waivers.parse(text)
    assert valid == [] and notes


def test_no_text_means_no_waivers_and_no_noise():
    assert waivers.parse(None) == ([], [])


# --- waivers: applying ------------------------------------------------------------------------------------------


def result(rule="license-present", outcome="fail"):
    return engine.Result(id=rule, label="audited", level="warn", result=outcome, findings=["no LICENSE file"])


def test_a_live_waiver_turns_a_failure_into_waived_and_keeps_the_original_finding():
    (r,) = [result()]
    waivers.apply([r], "r", [entry()], TODAY)
    assert r.result == "waived" and "waived by me" in r.findings[0] and r.findings[1] == "no LICENSE file"


def test_an_expired_waiver_leaves_the_failure_and_says_it_expired():
    r = result()
    waivers.apply([r], "r", [entry(granted=TODAY - timedelta(days=20), expires=TODAY - timedelta(days=1))], TODAY)
    assert r.result == "fail" and "waiver expired" in r.findings[-1]


def test_a_waiver_expires_at_the_end_of_its_last_day():
    r = result()
    waivers.apply([r], "r", [entry(granted=TODAY - timedelta(days=5), expires=TODAY)], TODAY)
    assert r.result == "waived"


def test_a_waiver_covers_only_its_own_repo_and_rule():
    other_repo, other_rule = result(), result("journal-present")
    waivers.apply([other_repo], "someone-else", [entry()], TODAY)
    waivers.apply([other_rule], "r", [entry()], TODAY)
    assert other_repo.result == "fail" and other_rule.result == "fail"


def test_unknown_and_pass_results_are_never_waived():
    u, p = result(outcome="unknown"), result(outcome="pass")
    waivers.apply([u, p], "r", [entry()], TODAY)
    assert (u.result, p.result) == ("unknown", "pass")


# --- waivers: reading from the base ref -------------------------------------------------------------------------

WAIVER_YAML = "waivers:\n  - {repo: r, rule: license-present, owner: me, reason: x, granted: 2026-11-01, expires: 2026-11-10}\n"


def checkout_with_origin(tmp_path, on_base=None, on_branch=None):
    """An autopilot-like checkout where origin/main holds `on_base` and the working tree holds `on_branch`."""
    root = tmp_path / "ap"
    root.mkdir()
    git_repo(root, {"policy/waivers.yaml": on_base} if on_base is not None else {"README.md": "x\n"})
    git(root, "remote", "add", "origin", str(root))
    git(root, "update-ref", "refs/remotes/origin/main", "HEAD")
    if on_branch is not None:
        write(root, {"policy/waivers.yaml": on_branch})
    return root


def test_waivers_are_read_from_the_base_ref_not_the_working_tree(tmp_path):
    root = checkout_with_origin(tmp_path, on_base="waivers: []\n", on_branch=WAIVER_YAML)
    text, note = waivers.read_base(root)
    assert "[]" in text and "license-present" not in text and note == ""


def test_a_waiver_added_only_on_a_branch_is_not_granted(tmp_path):
    root = checkout_with_origin(tmp_path, on_branch=WAIVER_YAML)
    assert waivers.read_base(root) == (None, "")


def test_the_base_ref_having_the_file_grants_it(tmp_path):
    text, _ = waivers.read_base(checkout_with_origin(tmp_path, on_base=WAIVER_YAML))
    assert waivers.parse(text)[0][0]["rule"] == "license-present"


def test_a_missing_base_ref_applies_no_waivers_and_says_to_fetch(tmp_path):
    root = checkout_with_origin(tmp_path, on_branch=WAIVER_YAML)
    git(root, "update-ref", "-d", "refs/remotes/origin/main")
    text, note = waivers.read_base(root)
    assert text is None and "git fetch" in note


def test_with_no_remote_at_all_the_working_tree_is_used_and_the_note_says_so(tmp_path):
    root = tmp_path / "solo"
    root.mkdir()
    git_repo(root, {"policy/waivers.yaml": WAIVER_YAML})
    text, note = waivers.read_base(root)
    assert "license-present" in text and "working tree" in note


# --- the command ------------------------------------------------------------------------------------------------


def test_a_clean_repo_exits_zero_and_a_failing_fail_level_rule_exits_one(tmp_path, portfolio, capsys):
    good = clone(tmp_path, "good", files=CLEAN)
    assert run(tmp_path, str(good)) == 0
    bad = clone(tmp_path, "bad", files={**CLEAN, ".github/workflows/ci.yml": GOOD_WF.replace("a" * 40, "main")})
    assert run(tmp_path, str(bad)) == 1
    out = capsys.readouterr().out
    assert "FAIL    pinned-actions" in out and "== bad" in out


def test_json_output_is_parseable_and_names_every_rule(tmp_path, portfolio, capsys):
    good = clone(tmp_path, "good", files=CLEAN)
    run(tmp_path, str(good), "--json")
    data = json.loads(capsys.readouterr().out)
    assert [len(r["results"]) for r in data["repos"]] == [18] and data["errors"] == []


def test_a_live_waiver_makes_a_failing_repo_pass_end_to_end(tmp_path, portfolio, monkeypatch, capsys):
    root = checkout_with_origin(
        tmp_path, on_base=WAIVER_YAML.replace("license-present", "pinned-actions").replace("repo: r", "repo: bad")
    )
    bad = clone(tmp_path, "bad", files={**CLEAN, ".github/workflows/ci.yml": GOOD_WF.replace("a" * 40, "main")})
    monkeypatch.setattr(cli, "ROOT", root)
    monkeypatch.setattr(command, "date", SimpleNamespace(today=lambda: date(2026, 11, 5)))
    assert run(tmp_path, str(bad)) == 0
    assert "waived by me" in capsys.readouterr().out


def test_no_arguments_is_an_error_not_a_pass(portfolio, capsys):
    assert cli.main(["standard", "check", "--offline"]) == 2


def test_the_portfolio_finds_clones_by_origin_name_not_directory_name(tmp_path, portfolio, capsys):
    clone(tmp_path, "drillpad", origin="drillpad-workspace", files=CLEAN)
    portfolio["drillpad-workspace"] = {"enabled": True}
    assert run(tmp_path, "--portfolio", "--root", str(tmp_path)) == 0
    assert "== drillpad-workspace" in capsys.readouterr().out


def test_a_missing_clone_of_an_enabled_repo_is_an_error_by_name_and_the_rest_still_run(tmp_path, portfolio, capsys):
    clone(tmp_path, "here", files=CLEAN)
    portfolio.update({"here": {"enabled": True}, "gone": {"enabled": True}})
    assert run(tmp_path, "--portfolio", "--root", str(tmp_path)) == 1
    out = capsys.readouterr().out
    assert "ERROR no clone of gone" in out and "== here" in out


def test_a_disabled_repo_without_a_clone_is_not_required(tmp_path, portfolio):
    clone(tmp_path, "here", files=CLEAN)
    portfolio.update({"here": {"enabled": True}, "off": {"enabled": False}})
    assert run(tmp_path, "--portfolio", "--root", str(tmp_path)) == 0


def test_strict_turns_an_unanswerable_fail_level_rule_into_a_failure(tmp_path, portfolio):
    d = clone(tmp_path, "broken", files={**CLEAN, ".github/workflows/bad.yml": "on: [push\n  : x"})
    assert run(tmp_path, str(d)) == 0
    assert run(tmp_path, str(d), "--strict") == 1


def test_offline_never_calls_gh(tmp_path, portfolio, monkeypatch):
    calls = []
    real = subprocess.run
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: (calls.append(cmd[0]), real(cmd, **kw))[1])
    portfolio["good"] = {"enabled": True}
    run(tmp_path, str(clone(tmp_path, "good", files=CLEAN)))
    assert "gh" not in calls


def test_a_repo_outside_the_portfolio_is_still_checked_and_license_is_skipped(tmp_path, portfolio, capsys):
    run(tmp_path, str(clone(tmp_path, "stranger", files=CLEAN)))
    assert "skip    license-present" in capsys.readouterr().out


# --- GitHub's answer about public/private wins over the portfolio ------------------------------------------------


def fake_gh(visibility):
    """Answers `gh api repos/X --jq .private`; ruleset questions fail."""

    def gh(cmd, **kw):
        if cmd[3:5] == ["--jq", ".private"] and visibility is not None:
            return subprocess.CompletedProcess(cmd, 0, f"{visibility}\n", "")
        return subprocess.CompletedProcess(cmd, 1, "", "")

    return gh


def license_result(tmp_path, visibility, entry):
    d = clone(tmp_path, "r", files=CLEAN)
    pf = {"owner": "o", "repos": {"r": entry}}
    _, results, notes = command.check_one(d, pf, cli.repo_name, fake_gh(visibility), [], TODAY)
    return next(r for r in results if r.id == "license-present"), notes


def test_a_repo_github_says_is_public_is_held_to_the_license_rule_even_if_the_portfolio_forgot(tmp_path):
    result_, notes = license_result(tmp_path, "false", {"enabled": True})
    assert result_.result == "fail" and "GitHub says public but policy/portfolio.yaml says not public" in notes[0]


def test_a_repo_github_says_is_private_skips_the_license_rule_even_if_the_portfolio_says_public(tmp_path):
    result_, notes = license_result(tmp_path, "true", {"enabled": True, "public": True})
    assert result_.result == "skip" and "GitHub says private" in notes[0]


def test_agreement_between_github_and_the_portfolio_makes_no_note(tmp_path):
    assert license_result(tmp_path, "false", {"enabled": True, "public": True})[1] == []


def test_when_github_cannot_answer_the_portfolio_flag_is_used_and_nothing_is_noted(tmp_path):
    result_, notes = license_result(tmp_path, None, {"enabled": True, "public": True})
    assert result_.result == "fail" and notes == []


def test_an_unexpected_answer_from_gh_is_ignored():
    gh = lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, "maybe\n", "")  # noqa: E731
    assert engine.github_public("o/r", gh) is None and engine.github_public(None, gh) is None
