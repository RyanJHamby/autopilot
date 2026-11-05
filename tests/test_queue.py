import pytest

from autopilot import queue
from autopilot.apx.batch import Batch, BatchError, Item, parse

B = Batch("b", (Item(1), Item(2, depends_on=(1,)), Item(3), Item(4), Item(5), Item(6)))


def st(prs, labels):
    return dict(queue.item_states(B, prs, labels))


def pr(n, state="OPEN", merged=None):
    return {"headRefName": f"agent/{n}-x", "state": state, "mergedAt": merged}


def test_states():
    labels = {2: {"agent-ready"}, 3: {"agent-ready", "hold"}, 4: set(), 5: {"agent-ready"}}
    s = st([pr(1, "MERGED", "t")], labels)
    assert s[1] == "merged"
    assert s[2] == "ready"
    assert s[3].startswith("held")
    assert s[4] == "needs-label"
    assert s[5] == "ready"
    assert s[6] == "issue-closed-or-missing"


def test_waiting_and_pr_open_and_closed_unmerged():
    labels = {1: {"agent-ready"}, 2: {"agent-ready"}}
    s = st([], labels)
    assert s[2] == "waiting #1" and s[1] == "ready"
    assert st([pr(1)], labels)[1] == "pr-open"
    assert st([pr(1, "CLOSED")], labels)[1].startswith("closed-unmerged")


def test_non_agent_branches_ignored():
    assert st([{"headRefName": "feat/1-x", "state": "MERGED", "mergedAt": "t"}], {1: {"agent-ready"}})[1] == "ready"


def test_render_counts_merged():
    out = queue.render(B, queue.item_states(B, [pr(1, "MERGED", "t")], {}))
    assert out.startswith("batch b: 1/6 merged") and "after #1" in out


def test_scaffold_roundtrips_through_planner_parser(tmp_path):
    p = queue.scaffold("b1", ["10", "11:10", "12:10,11"], tmp_path / "x")
    b = parse(p.read_text())
    assert [(i.issue, i.depends_on) for i in b.items] == [(10, ()), (11, (10,)), (12, (10, 11))]


def test_scaffold_refuses_bad_and_existing(tmp_path):
    with pytest.raises(BatchError):
        queue.scaffold("b1", ["1:1"], tmp_path)
    with pytest.raises(BatchError):
        queue.scaffold("BAD ID", ["1"], tmp_path)
    assert not list(tmp_path.glob("*"))
    queue.scaffold("b1", ["1"], tmp_path)
    with pytest.raises(FileExistsError):
        queue.scaffold("b1", ["2"], tmp_path)


def _prs(*merged):
    return [{"headRefName": f"agent/{n}-x", "state": "MERGED", "mergedAt": "t"} for n in merged]


def test_preflight_rejects_merged_closed_and_warns_on_unlabelled():
    labels = {1: {"agent-ready"}, 2: set(), 4: {"agent-ready"}}
    errs, warns = queue.preflight(["1", "2:1", "3", "4"], _prs(4), labels)
    assert errs == [
        "#3 is closed or does not exist",
        "#4 already has a merged agent PR (pass --retry if you really want it run again)",
    ]
    assert warns == ["#2 is not labelled agent-ready yet (yours to apply)"]


def test_preflight_retry_allows_merged():
    assert queue.preflight(["4"], _prs(4), {4: {"agent-ready"}}, retry=True) == ([], [])


def test_cli_add_refuses_merged_issue_and_writes_nothing(monkeypatch, tmp_path, capsys):
    import json
    import subprocess

    from autopilot import cli

    def fake(args, **kw):
        out = json.dumps(_prs(5)) if args[1] == "pr" else json.dumps([{"number": 5, "labels": []}, {"number": 6, "labels": []}])
        return subprocess.CompletedProcess(args, 0, stdout=out, stderr="")

    monkeypatch.setattr(cli.subprocess, "run", fake)
    d = tmp_path / "b"
    assert cli.main(["queue", "add", "b1", "5", "--dir", str(d)]) == 2
    assert "merged agent PR" in capsys.readouterr().out and not d.exists()
    assert cli.main(["queue", "add", "b1", "6", "--dir", str(d)]) == 0
    assert (d / "b1.yaml").exists()


def test_cli_add_fails_closed_when_gh_unreadable_unless_offline(monkeypatch, tmp_path, capsys):
    import subprocess

    from autopilot import cli

    def boom(args, **kw):
        raise subprocess.CalledProcessError(1, args)

    monkeypatch.setattr(cli.subprocess, "run", boom)
    d = tmp_path / "b"
    assert cli.main(["queue", "add", "b1", "6", "--dir", str(d)]) == 2
    assert not d.exists()
    assert cli.main(["queue", "add", "b1", "6", "--dir", str(d), "--offline"]) == 0
