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
    return argparse.Namespace(owner=None, root=str(root), json=False, **kw)


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
