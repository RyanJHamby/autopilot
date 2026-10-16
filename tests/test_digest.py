import datetime as dt
import json
import subprocess

from autopilot import cli, digest

NOW = dt.datetime(2026, 10, 16, 8, 0, tzinfo=dt.timezone.utc)


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
