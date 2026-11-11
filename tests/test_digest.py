import datetime as dt
import json
import subprocess

import pytest

from autopilot import cli, digest
from autopilot.converge import command as converge_command

NOW = dt.datetime(2026, 10, 16, 8, 0, tzinfo=dt.timezone.utc)


@pytest.fixture(autouse=True)
def history_file(tmp_path, monkeypatch):
    """No digest test may read the real ~/.autopilot/converge/history.jsonl."""
    path = tmp_path / "history.jsonl"
    monkeypatch.setattr(converge_command, "HISTORY", path)
    return path


def iso(hours_ago):
    return (NOW - dt.timedelta(hours=hours_ago)).isoformat()


def pr(n, head="agent/1-x", state="OPEN", merged_h=None, title="t", draft=False):
    return {
        "number": n,
        "title": title,
        "headRefName": head,
        "state": state,
        "isDraft": draft,
        "url": f"https://github.com/o/r/pull/{n}",
        "mergedAt": iso(merged_h) if merged_h is not None else None,
    }


def run(i, conclusion="failure", hours_ago=3, title="agent #1"):
    return {"databaseId": i, "conclusion": conclusion, "createdAt": iso(hours_ago), "displayTitle": title}


def test_merged_only_agent_prs_in_last_24h():
    prs = [
        pr(1, state="MERGED", merged_h=2),
        pr(2, state="MERGED", merged_h=30),
        pr(3, head="feature/x", state="MERGED", merged_h=1),
    ]
    d = digest.summarize("r", prs, [], NOW)
    assert [p["number"] for p in d["merged"]] == [1]


def test_waiting_on_me_is_open_non_draft_agent_prs():
    prs = [pr(1), pr(2, draft=True), pr(3, head="feature/x"), pr(4, state="MERGED", merged_h=1)]
    d = digest.summarize("r", prs, [], NOW)
    assert [p["number"] for p in d["waiting"]] == [1]


def test_failed_runs_exclude_success_skipped_cancelled_and_old():
    runs = [
        run(1),
        run(2, "timed_out"),
        run(3, "success"),
        run(4, "skipped"),
        run(5, "cancelled"),
        run(6, hours_ago=48),
    ]
    d = digest.summarize("r", [], runs, NOW)
    assert [r["databaseId"] for r in d["failed"]] == [1, 2]


def test_render_markdown_sections_and_status():
    ds = [
        digest.summarize("alpha", [pr(1, state="MERGED", merged_h=2, title="Add x"), pr(2, title="Fix y")], [run(9)], NOW),
        digest.summarize("beta", [], [], NOW),
    ]
    out = digest.render(ds, {"alpha": "ok", "beta": "paused", "gamma": "held until 2026-11-01"}, NOW)
    assert out.startswith("# Autopilot digest 2026-10-16")
    assert "## Merged (1)" in out and "alpha #1 Add x" in out
    assert "## Waiting on you (1)" in out and "alpha #2 Fix y" in out
    assert "## Failed runs (1)" in out and "alpha run 9" in out
    assert "## Paused or held" in out and "beta: paused" in out and "gamma: held until 2026-11-01" in out
    assert "alpha: ok" not in out


def test_render_empty_says_none():
    out = digest.render([digest.summarize("a", [], [], NOW)], {}, NOW)
    assert out.count("none") == 4


def test_repo_status_dormant_held_paused_and_ok():
    held = {"mode": "standard", "hold_until": "2026-11-01T00:00:00Z"}
    assert digest.repo_status({"mode": "dormant"}, False, NOW) == "dormant"
    assert digest.repo_status(held, False, NOW) == "held until 2026-11-01T00:00:00Z"
    assert digest.repo_status({"mode": "standard"}, True, NOW) == "paused"
    assert digest.repo_status({"mode": "standard"}, False, NOW) == "ok"


def test_cmd_digest_is_read_only_and_calls_no_model(monkeypatch, capsys):
    pf = {
        "owner": "o",
        "defaults": {},
        "repos": {"a": {"enabled": True, "mode": "standard", "tier": "B"}, "off": {"enabled": False, "mode": "standard"}},
    }
    monkeypatch.setattr(cli, "load_portfolio", lambda: pf)
    calls = []

    def fake_run(args, **kw):
        calls.append(args)
        out = {"pr": json.dumps([pr(7, title="Hello")]), "run": "[]", "variable": "false"}[args[1]]
        return subprocess.CompletedProcess(args, 0, stdout=out, stderr="")

    monkeypatch.setattr(cli.subprocess, "run", fake_run)
    assert cli.main(["digest"]) == 0
    out = capsys.readouterr().out
    assert "a #7 Hello" in out
    assert all(c[0] == "gh" and c[1] in ("pr", "run", "variable") and c[2] in ("list", "get") for c in calls)
    assert not any("off" in " ".join(c) for c in calls)


def test_cmd_digest_shows_the_standard_burn_down_from_converges_history(monkeypatch, capsys, history_file):
    pf = {"owner": "o", "defaults": {}, "repos": {"a": {"enabled": True, "mode": "standard", "tier": "B"}}}
    monkeypatch.setattr(cli, "load_portfolio", lambda: pf)
    monkeypatch.setattr(
        cli.subprocess, "run", lambda args, **kw: subprocess.CompletedProcess(args, 0, stdout="[]" if args[1] != "variable" else "false", stderr="")
    )
    old = {"time": "t1", "repos": {"a": {"fail_level": 4, "warn": 2, "grandfathered": 1}}}
    new = {"time": "t2", "repos": {"a": {"fail_level": 1, "warn": 2, "grandfathered": 1}}}
    history_file.write_text(json.dumps(old) + "\n" + json.dumps(new) + "\n")
    assert cli.main(["digest"]) == 0
    out = capsys.readouterr().out
    assert "## Standard burn-down" in out and "a: 1 fail-level (was 4)" in out


def test_cmd_digest_without_any_history_says_so_instead_of_inventing_a_trend(monkeypatch, capsys):
    pf = {"owner": "o", "defaults": {}, "repos": {}}
    monkeypatch.setattr(cli, "load_portfolio", lambda: pf)
    assert cli.main(["digest"]) == 0
    assert "converge has not recorded a run yet" in capsys.readouterr().out


def rich(n, files=(), checks=(), add=0, dele=0, title="t"):
    return {
        **pr(n, title=title),
        "files": [{"path": f} for f in files],
        "statusCheckRollup": [dict(c) for c in checks],
        "additions": add,
        "deletions": dele,
    }


OK = {"conclusion": "SUCCESS", "status": "COMPLETED"}
RED = {"conclusion": "FAILURE", "status": "COMPLETED"}


def test_risk_ranks_protected_then_red_then_large_then_running_then_small():
    assert digest.risk(rich(1, files=[".github/workflows/x.yml"], checks=[OK]))[0] == 0
    assert digest.risk(rich(1, files=["supabase/migrations/1.sql"]))[0] == 0
    assert digest.risk(rich(1, files=["a.py"], checks=[RED]))[0] == 1
    assert digest.risk(rich(1, files=["a.py"], checks=[OK], add=300, dele=101))[0] == 2
    assert digest.risk(rich(1, files=["a.py"], checks=[{"status": "IN_PROGRESS"}]))[0] == 3
    assert digest.risk(rich(1, files=["a.py"], checks=[OK], add=10))[0] == 4


def test_risk_with_missing_fields_is_not_the_lowest_risk_signal():
    assert digest.risk(pr(1)) == (4, "no checks yet")


def test_waiting_list_is_riskiest_first_across_repos():
    a = digest.summarize(
        "a",
        [rich(1, files=["x.py"], checks=[OK], title="small"), rich(2, files=["docs/x.md"], checks=[RED], title="red")],
        [],
        NOW,
    )
    b = digest.summarize("b", [rich(3, files=[".claude/settings.json"], checks=[OK], title="prot")], [], NOW)
    out = digest.render([a, b], {}, NOW)
    assert out.index("b #3") < out.index("a #2") < out.index("a #1")
    assert "protected path .claude/settings.json" in out and "a check is failing" in out


def test_digest_out_writes_only_the_given_file(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(
        cli, "load_portfolio", lambda: {"owner": "o", "defaults": {}, "repos": {"a": {"enabled": True, "mode": "standard"}}}
    )
    seen = []

    def fake(a, **k):
        seen.append(a)
        return subprocess.CompletedProcess(a, 0, stdout="[]" if a[1] != "variable" else "false", stderr="")

    monkeypatch.setattr(cli.subprocess, "run", fake)
    f = tmp_path / "d.md"
    assert cli.main(["digest", "--out", str(f)]) == 0
    assert f.read_text().startswith("# Autopilot digest")
    pr_list = next(a for a in seen if a[1] == "pr")
    assert all(k in pr_list[pr_list.index("--json") + 1] for k in ("files", "additions", "deletions", "statusCheckRollup"))
    assert "# Autopilot digest" not in capsys.readouterr().out
