"""`ap standard converge`: which repos it audits, which it skips, that it reads only, and that it never reports a cut-off or
failed listing as 'everything is fine'."""

import argparse
import json
import subprocess
from datetime import date
from pathlib import Path

import pytest

from autopilot.converge import command, core

TODAY = date(2026, 11, 8)


@pytest.fixture(autouse=True)
def status_file(tmp_path_factory, monkeypatch):
    """No test may write to the real ~/.autopilot/converge/last.json."""
    path = tmp_path_factory.mktemp("status") / "last.json"
    monkeypatch.setattr(command, "STATUS", path)
    return path


def row(name, **kw):
    base = {
        "name": name,
        "isFork": False,
        "isArchived": False,
        "visibility": "PUBLIC",
        "isTemplate": False,
        "createdAt": "2025-01-01T00:00:00Z",
    }
    return {**base, **kw}


def cp(cmd, rc=0, out="", err=""):
    return subprocess.CompletedProcess(cmd, rc, out, err)


def fake_run(listing, *, clone_files=None, list_rc=0, clone_rc=0):
    calls = []

    def run(cmd, **kw):
        calls.append(list(cmd))
        if cmd[:3] == ["gh", "repo", "list"]:
            return cp(cmd, list_rc, json.dumps(listing) if not list_rc else "", "auth required" if list_rc else "")
        if cmd[:3] == ["gh", "repo", "clone"]:
            if clone_rc:
                return cp(cmd, clone_rc, "", "not found")
            dest = Path(cmd[3 + 1])
            (dest / ".git").mkdir(parents=True)
            for rel, text in (clone_files or {}).items():
                (dest / rel).parent.mkdir(parents=True, exist_ok=True)
                (dest / rel).write_text(text)
            return cp(cmd)
        return cp(cmd, 1)

    run.calls = calls
    return run


def portfolio(**kw):
    return {"owner": "Ryan", "repos": {}, "excluded": [], **kw}


def ns(root, **kw):
    """`all=True` by default so the older tests cover the whole list; scope tests pass all=False."""
    return argparse.Namespace(**{"owner": None, "root": str(root), "json": False, "all": True, "apply": False, **kw})


def clone(root: Path, name: str, files: dict[str, str] | None = None) -> Path:
    d = root / name
    (d / ".git").mkdir(parents=True)
    for rel, text in (files or {}).items():
        (d / rel).parent.mkdir(parents=True, exist_ok=True)
        (d / rel).write_text(text)
    return d


def tree(path: Path) -> list[str]:
    return sorted(str(p.relative_to(path)) for p in path.rglob("*"))


# --- listing -------------------------------------------------------------------------------------------------------------


def test_listing_maps_visibility_and_flags():
    got = core.parse_list(json.dumps([row("a"), row("b", visibility="PRIVATE", isFork=True), row("c", visibility="INTERNAL")]))
    assert [(r.name, r.public, r.fork) for r in got] == [("a", True, False), ("b", False, True), ("c", False, False)]


def test_a_failed_listing_is_an_error_not_an_empty_list():
    with pytest.raises(core.ListError, match="auth required"):
        core.list_repos("Ryan", run=fake_run([], list_rc=1))


def test_a_listing_that_hit_the_limit_is_an_error_because_repos_may_be_missing():
    with pytest.raises(core.ListError, match="limit"):
        core.list_repos("Ryan", run=fake_run([row(f"r{i}") for i in range(3)]), limit=3)


def test_a_large_listing_below_the_limit_is_returned_whole():
    assert len(core.list_repos("Ryan", run=fake_run([row(f"r{i}") for i in range(250)]))) == 250


def test_garbage_from_gh_is_an_error():
    with pytest.raises(core.ListError):
        core.parse_list("not json")


# --- gating --------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("listed", "pf", "why"),
    [
        (core.Listed("x", fork=True), portfolio(), "fork"),
        (core.Listed("x", archived=True), portfolio(), "archived"),
        (core.Listed("ryan"), portfolio(), "profile repo"),
        (core.Listed("x"), portfolio(excluded=["x"]), "excluded"),
        (core.Listed("x", template=True), portfolio(), "template"),
        (core.Listed("x"), portfolio(repos={"x": {"data_class": "restricted"}}), "restricted"),
    ],
)
def test_gate_skips_what_must_not_be_audited(listed, pf, why):
    assert why in core.gate(listed, "Ryan", pf)


def test_gate_lets_a_normal_repo_through_even_when_it_is_not_in_the_portfolio():
    assert core.gate(core.Listed("brand-new"), "Ryan", portfolio()) is None


def test_new_means_created_within_the_window():
    assert core.is_new("2026-11-01T10:00:00Z", TODAY)
    assert not core.is_new("2026-01-01T10:00:00Z", TODAY)
    assert not core.is_new("", TODAY) and not core.is_new("garbage", TODAY)


# --- auditing ------------------------------------------------------------------------------------------------------------


def test_audit_lists_failing_rules_and_the_files_fix_would_create(tmp_path):
    path = clone(tmp_path, "proj", {"LICENSE": "x"})
    a = core.audit(core.Listed("proj", public=True), path, "Ryan", portfolio(holder="H"), TODAY)
    assert any(g.startswith("security-policy:") for g in a.gaps)
    assert "SECURITY.md" in a.fixable and "LICENSE" not in a.fixable


def test_audit_reports_a_pawl_repo_as_skipped(tmp_path):
    path = clone(tmp_path, "p", {"policy/lanes.toml": ""})
    a = core.audit(core.Listed("p", public=True), path, "Ryan", portfolio(), TODAY)
    assert a.skipped and not a.gaps


def test_audit_counts_fail_level_rules_separately(tmp_path):
    path = clone(
        tmp_path, "proj", {".github/workflows/ci.yml": "on: push\njobs:\n  t:\n    steps:\n      - uses: actions/checkout@v4\n"}
    )
    a = core.audit(core.Listed("proj", public=True), path, "Ryan", portfolio(), TODAY)
    assert a.fail_level >= 1 and any(g.startswith("pinned-actions:") for g in a.gaps)


# --- the command ---------------------------------------------------------------------------------------------------------


def run_cmd(root, listing, capsys, pf=None, **runkw):
    run = fake_run(listing, **runkw)
    code = command.cmd_converge(
        ns(root), repo_name=lambda p: p.name, load_portfolio=lambda: pf or portfolio(), run=run, today=TODAY
    )
    return code, capsys.readouterr().out, run


def test_converge_audits_every_repo_on_github_not_just_the_portfolio(tmp_path, capsys):
    clone(tmp_path, "only-on-github")
    code, out, _ = run_cmd(tmp_path, [row("only-on-github")], capsys)
    assert code == 0 and "only-on-github" in out and "not in portfolio" in out


def test_a_new_repo_is_listed_first_and_flagged(tmp_path, capsys):
    clone(tmp_path, "old")
    clone(tmp_path, "fresh")
    _, out, _ = run_cmd(tmp_path, [row("old"), row("fresh", createdAt="2026-11-06T00:00:00Z")], capsys)
    assert out.index("fresh") < out.index("old") and "NEW" in out


def test_skipped_repos_are_named_with_a_reason(tmp_path, capsys):
    _, out, _ = run_cmd(tmp_path, [row("up", isFork=True), row("old", isArchived=True)], capsys)
    assert "skipped up: fork" in out and "skipped old: archived" in out


def test_a_repo_with_no_local_clone_is_audited_from_a_shallow_clone(tmp_path, capsys):
    code, out, run = run_cmd(tmp_path / "empty-root", [row("remote-only")], capsys, clone_files={"LICENSE": "x"})
    assert code == 0 and "shallow clone" in out
    clone_cmd = next(c for c in run.calls if c[:3] == ["gh", "repo", "clone"])
    assert "--depth" in clone_cmd and "Ryan/remote-only" in clone_cmd


def test_an_existing_local_clone_is_used_and_never_modified(tmp_path, capsys):
    path = clone(tmp_path, "proj", {"README.md": "hi"})
    before = tree(path)
    _, _, run = run_cmd(tmp_path, [row("proj")], capsys)
    assert tree(path) == before
    assert not any(c[:3] == ["gh", "repo", "clone"] for c in run.calls)


def test_a_failed_clone_is_reported_and_the_exit_code_is_nonzero(tmp_path, capsys):
    code, out, _ = run_cmd(tmp_path / "r", [row("x")], capsys, clone_rc=1)
    assert code == 1 and "ERROR x: could not get a checkout" in out


def test_a_failed_listing_exits_nonzero_and_says_so(tmp_path, capsys):
    code, out, _ = run_cmd(tmp_path, [], capsys, list_rc=1)
    assert code == 1 and "ERROR cannot list Ryan's repos" in out and "0 audited" not in out


def test_dry_run_issues_no_write_commands(tmp_path, capsys):
    clone(tmp_path, "proj")
    _, _, run = run_cmd(tmp_path, [row("proj")], capsys)
    assert all(c[:3] in (["gh", "repo", "list"], ["gh", "repo", "clone"]) or c[0] != "gh" for c in run.calls)
    assert not any("issue" in c or "pr" in c[:2] for c in run.calls)


def test_json_output_has_audits_skipped_and_errors(tmp_path, capsys):
    clone(tmp_path, "proj")
    run = fake_run([row("proj"), row("f", isFork=True)])
    n = ns(tmp_path)
    n.json = True
    command.cmd_converge(n, repo_name=lambda p: p.name, load_portfolio=portfolio, run=run, today=TODAY)
    data = json.loads(capsys.readouterr().out)
    assert [a["name"] for a in data["audits"]] == ["proj"]
    assert data["skipped"] == [{"repo": "f", "why": "fork"}] and data["errors"] == []


# --- scope and issue filing ----------------------------------------------------------------------------------------------

from autopilot.converge import issues  # noqa: E402

OLD = "2024-01-01T00:00:00Z"
FRESH = "2026-11-06T00:00:00Z"


def with_issues(base, store=None, *, list_rc=0, write_rc=0, list_err="boom"):
    """Wrap fake_run with a tiny issue tracker: `store` maps 'owner/repo' to its open standard-gap issues."""
    store = {} if store is None else store
    calls = []

    def run(cmd, **kw):
        if cmd[:2] == ["gh", "label"]:
            calls.append(list(cmd))
            return cp(cmd)
        if cmd[:2] == ["gh", "issue"]:
            calls.append(list(cmd))
            slug = cmd[cmd.index("-R") + 1]
            if cmd[2] == "list":
                return cp(cmd, 1, "", list_err) if list_rc else cp(cmd, 0, json.dumps(store.get(slug, [])))
            if write_rc:
                return cp(cmd, write_rc, "", "issues are disabled")
            if cmd[2] == "create":
                store.setdefault(slug, []).append(
                    {"number": 7, "title": cmd[cmd.index("--title") + 1], "body": cmd[cmd.index("--body") + 1]}
                )
            if cmd[2] == "edit":
                issue = store[slug][0]
                issue["title"], issue["body"] = cmd[cmd.index("--title") + 1], cmd[cmd.index("--body") + 1]
            if cmd[2] == "close":
                store[slug] = []
            return cp(cmd)
        return base(cmd, **kw)

    run.calls, run.store, run.base = calls, store, base
    return run


def converge(root, listing, pf, *, flags=None, store=None, **kw):
    base = fake_run(listing)
    run = with_issues(base, store, **kw)
    code = command.cmd_converge(
        ns(root, **(flags or {})), repo_name=lambda p: p.name, load_portfolio=lambda: pf, run=run, today=TODAY
    )
    return code, run


def writes(run, verb=None):
    return [
        c for c in run.calls if c[:2] in (["gh", "issue"], ["gh", "label"]) and c[2] != "list" and (verb is None or c[2] == verb)
    ]


def test_by_default_only_portfolio_and_new_repos_are_audited_and_old_ones_are_never_cloned(tmp_path, capsys):
    pf = portfolio(repos={"mine": {}})
    listing = [row("mine", createdAt=OLD), row("old-thing", createdAt=OLD), row("fresh", createdAt=FRESH)]
    for n in ("mine", "old-thing", "fresh"):
        clone(tmp_path, n)
    code, run = converge(tmp_path, listing, pf, flags={"all": False})
    out = capsys.readouterr().out
    assert "mine" in out and "fresh" in out and "old-thing" not in out
    assert "1 older repo(s) outside the portfolio were not audited" in out
    assert not any(c[:3] == ["gh", "repo", "clone"] for c in run.calls)


def test_all_includes_old_repos_in_the_report(tmp_path, capsys):
    clone(tmp_path, "old-thing")
    converge(tmp_path, [row("old-thing", createdAt=OLD)], portfolio(), flags={"all": True})
    assert "old-thing" in capsys.readouterr().out


def test_dry_run_says_what_it_would_file_and_files_nothing(tmp_path, capsys):
    clone(tmp_path, "mine")
    code, run = converge(tmp_path, [row("mine")], portfolio(repos={"mine": {}}), flags={"all": False})
    out = capsys.readouterr().out
    assert "would create issue on mine: standard:" in out and "dry run: no issue was filed" in out
    assert writes(run) == []


def test_apply_creates_the_label_then_one_issue_with_the_gaps_and_the_command(tmp_path, capsys):
    clone(tmp_path, "mine")
    code, run = converge(tmp_path, [row("mine")], portfolio(repos={"mine": {}}), flags={"apply": True})
    kinds = [c[:3] for c in writes(run)]
    assert kinds == [["gh", "label", "create"], ["gh", "issue", "create"]]
    create = next(c for c in writes(run) if c[:3] == ["gh", "issue", "create"])
    assert "--label" in create and create[create.index("--label") + 1] == "standard-gap"
    body = create[create.index("--body") + 1]
    assert "## Gaps" in body and "ap standard fix --apply" in body and "Ryan/mine" in body
    assert code == 0


def test_a_second_run_with_the_same_gaps_writes_nothing(tmp_path, capsys):
    clone(tmp_path, "mine")
    pf = portfolio(repos={"mine": {}})
    _, first = converge(tmp_path, [row("mine")], pf, flags={"apply": True})
    _, second = converge(tmp_path, [row("mine")], pf, flags={"apply": True}, store=first.store)
    assert writes(second) == [] and len(first.store["Ryan/mine"]) == 1


def test_changed_gaps_edit_the_existing_issue_instead_of_filing_another(tmp_path, capsys):
    path = clone(tmp_path, "mine")
    pf = portfolio(repos={"mine": {}})
    _, first = converge(tmp_path, [row("mine")], pf, flags={"apply": True})
    (path / "LICENSE").write_text("x")  # a gap closes
    _, second = converge(tmp_path, [row("mine")], pf, flags={"apply": True}, store=first.store)
    assert [c[2] for c in writes(second)] == ["edit"] and len(second.store["Ryan/mine"]) == 1


def test_a_failed_issue_lookup_files_nothing_and_exits_nonzero(tmp_path, capsys):
    clone(tmp_path, "mine")
    code, run = converge(tmp_path, [row("mine")], portfolio(repos={"mine": {}}), flags={"apply": True}, list_rc=1)
    assert writes(run) == [] and code == 1 and "could not look up existing issues" in capsys.readouterr().out


def test_a_failed_issue_write_is_reported(tmp_path, capsys):
    clone(tmp_path, "mine")
    code, _ = converge(tmp_path, [row("mine")], portfolio(repos={"mine": {}}), flags={"apply": True}, write_rc=1)
    assert code == 1 and "issue create failed" in capsys.readouterr().out


def test_all_with_apply_still_files_issues_only_for_portfolio_and_new_repos(tmp_path, capsys):
    clone(tmp_path, "old-thing")
    _, run = converge(tmp_path, [row("old-thing", createdAt=OLD)], portfolio(), flags={"all": True, "apply": True})
    assert writes(run) == []


def test_a_repo_that_now_conforms_gets_its_issue_closed():
    a = core.Audit("mine", gaps=[], in_portfolio=True)
    op = issues.plan(
        a, "Ryan", with_issues(fake_run([]), {"Ryan/mine": [{"number": 3, "title": "standard: 2 gaps", "body": "x"}]})
    )
    assert (op.kind, op.number) == ("close", 3)
    assert issues.plan(a, "Ryan", with_issues(fake_run([]), {})).kind == "none"


def test_a_skipped_audit_files_nothing():
    a = core.Audit("p", skipped="pawl-scaffolded repo", in_portfolio=True)
    assert issues.plan(a, "Ryan", with_issues(fake_run([]), {})).kind == "none"


def test_the_issue_body_ignores_line_ending_differences_from_github():
    a = core.Audit("mine", gaps=["license-present: no LICENSE file"], fixable=["LICENSE"], in_portfolio=True)
    body = issues.body(a, "Ryan")
    store = {"Ryan/mine": [{"number": 1, "title": issues.title(a), "body": body.replace("\n", "\r\n")}]}
    assert issues.plan(a, "Ryan", with_issues(fake_run([]), store)).kind == "unchanged"


def test_the_title_counts_gaps_and_pluralises():
    assert issues.title(core.Audit("a", gaps=["x"])) == "standard: 1 gap"
    assert issues.title(core.Audit("a", gaps=["x", "y"])) == "standard: 2 gaps"


# --- status file ---------------------------------------------------------------------------------------------------------


def test_apply_records_how_the_run_went(tmp_path, status_file):
    clone(tmp_path, "mine")
    converge(tmp_path, [row("mine")], portfolio(repos={"mine": {}}), flags={"apply": True})
    data = json.loads(status_file.read_text())
    assert data["ok"] is True and data["exit"] == 0 and data["audited"] == 1 and data["with_gaps"] == 1
    assert data["issues"]["create"] == 1 and data["errors"] == [] and data["time"]


def test_a_dry_run_writes_no_status_file(tmp_path, status_file):
    clone(tmp_path, "mine")
    converge(tmp_path, [row("mine")], portfolio(repos={"mine": {}}))
    assert not status_file.exists()


def test_a_failed_listing_is_recorded_as_not_ok_so_a_silent_failure_is_visible(tmp_path, status_file):
    command.cmd_converge(
        ns(tmp_path, apply=True), repo_name=lambda p: p.name, load_portfolio=portfolio, run=fake_run([], list_rc=1), today=TODAY
    )
    data = json.loads(status_file.read_text())
    assert data["ok"] is False and data["exit"] == 1 and "cannot list repos" in data["errors"][0]


def test_an_unwritable_status_file_warns_but_does_not_fail_the_run(tmp_path, capsys, monkeypatch):
    clone(tmp_path, "mine")
    blocker = tmp_path / "file"
    blocker.write_text("x")
    monkeypatch.setattr(command, "STATUS", blocker / "sub" / "last.json")  # a parent that is a file: mkdir fails
    code, _ = converge(tmp_path, [row("mine")], portfolio(repos={"mine": {}}), flags={"apply": True})
    assert code == 0 and "WARNING could not write the status file" in capsys.readouterr().out


# --- the launchd job -----------------------------------------------------------------------------------------------------

PLIST = Path(__file__).resolve().parent.parent / "deploy/launchd/com.autopilot.standard.converge.plist"


def test_the_launchd_job_is_weekly_files_nothing_at_install_and_stores_no_secret():
    import plistlib

    plist = plistlib.loads(PLIST.read_bytes())
    command_line = plist["ProgramArguments"][-1]
    assert "ap standard converge --apply" in command_line and "REPO_DIR" in command_line
    assert plist["StartCalendarInterval"] == {"Weekday": 1, "Hour": 9, "Minute": 0}
    assert plist["RunAtLoad"] is False  # installing it must not file anything
    assert "EnvironmentVariables" not in plist  # no token or key: it uses the owner's own gh login
    assert "--all" not in command_line  # the schedule never widens its scope


def _guard_repo(tmp_path):
    """A clone on main with a local origin, plus the plist's shell command pointed at it with the real converge call swapped for echo."""
    import plistlib
    import subprocess

    def git(*a, cwd):
        subprocess.run(["git", "-c", "commit.gpgsign=false", *a], cwd=cwd, check=True, capture_output=True)

    origin, work = tmp_path / "origin.git", tmp_path / "work"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
    git("clone", "-q", str(origin), str(work), cwd=tmp_path)
    git("checkout", "-q", "-b", "main", cwd=work)
    (work / "f.txt").write_text("1")
    git("add", "f.txt", cwd=work)
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "one", cwd=work)
    git("push", "-q", "-u", "origin", "main", cwd=work)
    cmd = plistlib.loads(PLIST.read_bytes())["ProgramArguments"][-1]
    assert "uv run ap standard converge --apply" in cmd
    return work, cmd.replace("REPO_DIR", str(work)).replace("uv run ap standard converge --apply", "echo RAN-CONVERGE")


def _sh(cmd):
    import subprocess

    return subprocess.run(["sh", "-c", cmd], capture_output=True, text=True)


def test_the_job_runs_from_a_clean_main(tmp_path):
    _, cmd = _guard_repo(tmp_path)
    r = _sh(cmd)
    assert r.returncode == 0 and "RAN-CONVERGE" in r.stdout


def test_the_job_refuses_a_feature_branch(tmp_path):
    import subprocess

    work, cmd = _guard_repo(tmp_path)
    subprocess.run(["git", "checkout", "-q", "-b", "feat/x"], cwd=work, check=True)
    r = _sh(cmd)
    assert r.returncode != 0 and "RAN-CONVERGE" not in r.stdout and "not on main" in r.stdout


def test_the_job_refuses_uncommitted_changes_to_tracked_files(tmp_path):
    work, cmd = _guard_repo(tmp_path)
    (work / "f.txt").write_text("edited")
    r = _sh(cmd)
    assert r.returncode != 0 and "RAN-CONVERGE" not in r.stdout and "uncommitted" in r.stdout


def test_untracked_files_do_not_block_the_job(tmp_path):
    work, cmd = _guard_repo(tmp_path)
    (work / "key.pub").write_text("x")
    assert "RAN-CONVERGE" in _sh(cmd).stdout


def test_the_job_pulls_main_before_running(tmp_path):
    import subprocess

    work, cmd = _guard_repo(tmp_path)
    other = tmp_path / "other"
    subprocess.run(["git", "clone", "-q", str(tmp_path / "origin.git"), str(other)], check=True, capture_output=True)
    (other / "g.txt").write_text("2")
    for a in (
        ["add", "g.txt"],
        ["-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "two"],
        ["push", "-q", "origin", "main"],
    ):
        subprocess.run(["git", *a], cwd=other, check=True, capture_output=True)
    assert "RAN-CONVERGE" in _sh(cmd).stdout
    assert (work / "g.txt").exists()


def test_a_failed_pull_stops_the_job(tmp_path):
    import shutil

    work, cmd = _guard_repo(tmp_path)
    shutil.rmtree(tmp_path / "origin.git")
    r = _sh(cmd)
    assert r.returncode != 0 and "RAN-CONVERGE" not in r.stdout


def test_the_job_finds_uv_without_a_zshrc(tmp_path):
    """launchd's login shell skips .zshrc, so uv in ~/.local/bin was not found (exit 127). The command must set PATH itself."""
    import plistlib
    import subprocess

    work, _ = _guard_repo(tmp_path)
    home = tmp_path / "home"
    (home / ".local/bin").mkdir(parents=True)
    fake = home / ".local/bin/uv"
    fake.write_text('#!/bin/sh\necho "FAKE-UV $@"\n')
    fake.chmod(0o755)
    cmd = plistlib.loads(PLIST.read_bytes())["ProgramArguments"][-1].replace("REPO_DIR", str(work))
    r = subprocess.run(["sh", "-c", cmd], capture_output=True, text=True, env={"HOME": str(home), "PATH": "/usr/bin:/bin"})
    assert r.returncode == 0, r.stderr
    assert "FAKE-UV run ap standard converge --apply" in r.stdout


# --- repos with issues disabled, and public repos ------------------------------------------------------------------------

DISABLED_MSG = "the 'Ryan/mine' repository has disabled issues"


def test_a_repo_with_issues_disabled_is_a_note_not_an_error(tmp_path, capsys, status_file):
    clone(tmp_path, "mine")
    code, run = converge(
        tmp_path, [row("mine")], portfolio(repos={"mine": {}}), flags={"apply": True}, list_rc=1, list_err=DISABLED_MSG
    )
    out = capsys.readouterr().out
    assert code == 0 and "no issue on mine: issues are disabled" in out and "ERROR" not in out
    assert writes(run) == []
    assert json.loads(status_file.read_text())["ok"] is True


def test_a_different_lookup_failure_is_still_an_error(tmp_path, capsys):
    clone(tmp_path, "mine")
    code, run = converge(
        tmp_path, [row("mine")], portfolio(repos={"mine": {}}), flags={"apply": True}, list_rc=1, list_err="rate limited"
    )
    assert code == 1 and writes(run) == []


SECRET = "no-tracked-secrets: keys/prod.pem is tracked by git"
WORKFLOW = "secret-exposed-workflows: deploy.yml uses repo secrets on pull_request with no agent/* exclusion"


def audit_with(public, *gaps):
    return core.Audit("mine", public=public, gaps=list(gaps), fixable=["SECURITY.md"], in_portfolio=True)


def test_a_public_issue_never_names_a_security_weakness():
    text = issues.body(audit_with(True, "license-present: no LICENSE file", SECRET, WORKFLOW), "Ryan")
    assert "prod.pem" not in text and "deploy.yml" not in text and "agent/*" not in text
    assert "2 security-related gap(s) are not listed here because this repository is public" in text
    assert "license-present: no LICENSE file" in text  # ordinary gaps are still listed


def test_a_private_issue_lists_the_security_findings_in_full():
    text = issues.body(audit_with(False, SECRET), "Ryan")
    assert "keys/prod.pem" in text and "not listed here" not in text


def test_an_unknown_visibility_is_treated_as_public_so_the_safe_mistake_is_saying_too_little():
    text = issues.body(audit_with(None, SECRET), "Ryan")
    assert "prod.pem" not in text and "1 security-related gap(s) are not listed here" in text


def test_the_redacted_text_is_what_is_actually_sent_to_github(tmp_path):
    import subprocess as sp

    path = clone(tmp_path, "mine", {"keys/prod.pem": "placeholder, not a key\n"})
    sp.run(["git", "-C", str(path), "init", "-q"], check=True, capture_output=True)
    sp.run(["git", "-C", str(path), "add", "-A"], check=True, capture_output=True)
    _, run = converge(tmp_path, [row("mine")], portfolio(repos={"mine": {}}), flags={"apply": True})
    create = next((c for c in writes(run) if c[:3] == ["gh", "issue", "create"]), None)
    assert create is not None
    body = create[create.index("--body") + 1]
    assert "prod.pem" not in body and "security-related gap(s) are not listed here" in body  # the rule did fire


# --- --only --------------------------------------------------------------------------------------------------------------


def two_repos(tmp_path):
    for n in ("mine", "other"):
        clone(tmp_path, n)
    return portfolio(repos={"mine": {}, "other": {}}), [row("mine"), row("other")]


def test_only_audits_and_reports_just_the_named_repo(tmp_path, capsys):
    pf, listing = two_repos(tmp_path)
    code, run = converge(tmp_path, listing, pf, flags={"all": False, "only": ["mine"]})
    out = capsys.readouterr().out
    assert code == 0 and "mine" in out and "other" not in out and "older repo(s)" not in out


def test_only_with_apply_files_exactly_one_issue_in_the_named_repo(tmp_path, capsys):
    pf, listing = two_repos(tmp_path)
    _, run = converge(tmp_path, listing, pf, flags={"all": False, "only": ["mine"], "apply": True})
    creates = [c for c in writes(run) if c[:3] == ["gh", "issue", "create"]]
    assert len(creates) == 1 and creates[0][creates[0].index("-R") + 1] == "Ryan/mine"
    assert not any("Ryan/other" in c for c in run.calls if c[:2] == ["gh", "issue"])


def test_only_is_repeatable(tmp_path, capsys):
    pf, listing = two_repos(tmp_path)
    _, run = converge(tmp_path, listing, pf, flags={"only": ["mine", "other"], "apply": True})
    assert len([c for c in writes(run) if c[:3] == ["gh", "issue", "create"]]) == 2


def test_only_with_an_unknown_name_is_an_error_not_a_silent_no_op(tmp_path, capsys):
    pf, listing = two_repos(tmp_path)
    code, run = converge(tmp_path, listing, pf, flags={"only": ["typo"], "apply": True})
    assert code == 1 and "--only typo: no such repo" in capsys.readouterr().out and writes(run) == []


def test_only_an_old_repo_outside_the_portfolio_is_audited_but_never_gets_an_issue(tmp_path, capsys):
    clone(tmp_path, "old-thing")
    code, run = converge(tmp_path, [row("old-thing", createdAt=OLD)], portfolio(), flags={"only": ["old-thing"], "apply": True})
    out = capsys.readouterr().out
    assert "old-thing" in out and "never files into it" in out and writes(run) == []


def test_only_still_respects_the_gates(tmp_path, capsys):
    code, run = converge(tmp_path, [row("up", isFork=True)], portfolio(repos={"up": {}}), flags={"only": ["up"], "apply": True})
    assert "skipped up: fork" in capsys.readouterr().out and writes(run) == []
