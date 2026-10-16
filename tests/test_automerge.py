import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "kit" / "runtime"))
import automerge  # noqa: E402

PR = {"state": "OPEN", "isDraft": False, "headRefName": "agent/3-1", "author": {"login": "claude"}}
GREEN = [{"name": "guard / guard", "conclusion": "success"}, {"name": "test", "conclusion": "success"}]
T0 = {"tier": 0, "class": "docs-only", "reasons": ["x"]}


def d(pr=PR, checks=GREEN, res=T0, enabled=("docs-only",), dm=None):
    return automerge.decide(pr, checks, res, list(enabled), dm or {})


def test_happy_path():
    assert d() == (True, "docs-only")


def test_human_branches_never_auto_merged():
    assert not d(pr={**PR, "headRefName": "feature/x"})[0]


def test_dependabot_allowed():
    assert d(pr={**PR, "headRefName": "dependabot/npm/x", "author": {"login": "app/dependabot"}})[0]


def test_red_or_pending_check_blocks():
    assert not d(checks=GREEN + [{"name": "test", "conclusion": "pending"}])[0]
    assert not d(checks=[{"name": "test", "conclusion": "failure"}])[0]


def test_not_tier0_or_not_enabled_or_demoted():
    assert not d(res={"tier": 1, "class": "", "reasons": ["code"]})[0]
    assert not d(enabled=())[0]
    ok, why = d(dm={"docs-only": "reverted"})
    assert not ok and "demoted" in why


def test_draft_or_closed():
    assert not d(pr={**PR, "isDraft": True})[0]
    assert not d(pr={**PR, "state": "MERGED"})[0]


def test_history_flags_reverts_and_red(monkeypatch):
    def gh(*a):
        if "pulls?state=closed" in a[1]:
            return [
                {
                    "number": 7,
                    "title": "t",
                    "body": "",
                    "merged_at": "2026-10-10T00:00:00Z",
                    "merge_commit_sha": "a" * 40,
                    "labels": [{"name": "automerged:docs-only"}],
                },
                {
                    "number": 9,
                    "title": 'Revert "t"',
                    "body": "Reverts #7",
                    "merged_at": "2026-10-11T00:00:00Z",
                    "merge_commit_sha": "b" * 40,
                    "labels": [],
                },
            ]
        return {"check_runs": [{"conclusion": "success"}, {"conclusion": "failure"}]}

    h = automerge.history(gh)
    assert len(h) == 1 and h[0]["class"] == "docs-only" and h[0]["reverted"] and h[0]["main_red"]


def test_kit_bump_prs_only_from_the_owner(monkeypatch):
    monkeypatch.setenv("GITHUB_REPOSITORY_OWNER", "me")
    res = {"tier": 0, "class": "kit-bump", "reasons": ["x"]}
    mine = {**PR, "headRefName": "autopilot/kit-bump-abc1234", "author": {"login": "me"}}
    assert d(pr=mine, res=res, enabled=("kit-bump",)) == (True, "kit-bump")
    assert not d(pr={**mine, "author": {"login": "someone-else"}}, res=res, enabled=("kit-bump",))[0]
    monkeypatch.delenv("GITHUB_REPOSITORY_OWNER")
    assert not d(pr=mine, res=res, enabled=("kit-bump",))[0]


def test_fetch_approved_parses_and_fails_closed():
    txt = "# approved kit shas\n" + "a" * 40 + "  2026-10-16 canary green\nnot-a-sha\n" + "b" * 40 + "\n"
    seen = []
    assert automerge.fetch_approved("me/kit", opener=lambda u: seen.append(u) or txt) == ["a" * 40, "b" * 40]
    assert seen == ["https://api.github.com/repos/me/autopilot-approved/contents/APPROVED?ref=main"]
    assert automerge.fetch_approved("me/kit", opener=lambda u: (_ for _ in ()).throw(OSError("down"))) == []
    assert automerge.fetch_approved("bad repo; x") == []


def test_automerge_never_uses_graphql_pr_view():
    """The workflow token cannot read statusCheckRollup over GraphQL (found live on drillpad-workspace #41)."""
    src = (Path(__file__).resolve().parents[1] / "kit" / "runtime" / "automerge.py").read_text()
    assert '"pr", "view"' not in src and "statusCheckRollup" not in src.replace("statusCheckRollup` is GraphQL", "")
    assert "check-runs" in src


def test_main_end_to_end_merges_a_green_docs_pr_through_rest_only(tmp_path, monkeypatch, capsys):
    pol = tmp_path / "p.yaml"
    pol.write_text("auto_merge_classes: [docs-only]\n")
    sha = "a" * 40
    calls = []

    def gh(*a):
        calls.append(a)
        path = a[1] if a[0] == "api" else ""
        if path.endswith("/pulls/9"):
            return {"state": "open", "draft": False, "head": {"ref": "agent/9-1", "sha": sha}, "user": {"login": "claude[bot]"}}
        if "check-runs" in path:
            return {"check_runs": [{"name": "guard / guard", "conclusion": "success"}, {"name": "test", "conclusion": "success"}]}
        if "pulls?state=closed" in path:
            return []
        return {}

    diff = "diff --git a/docs/a.md b/docs/a.md\nnew file mode 100644\n--- /dev/null\n+++ b/docs/a.md\n@@ -0,0 +1 @@\n+hi\n"
    monkeypatch.setattr(automerge, "_gh", gh)
    monkeypatch.setattr(automerge, "_git", lambda *a: diff if a[0] == "diff" else "")
    monkeypatch.setattr(automerge, "fetch_approved", lambda k: [])
    ran = []
    monkeypatch.setattr(automerge.subprocess, "run", lambda *a, **k: ran.append(a[0]) or type("R", (), {"returncode": 0})())
    assert automerge.main(["--pr", "9", "--head-sha", sha, "--policy", str(pol)]) == 0
    assert "MERGE docs-only" in capsys.readouterr().out
    assert not any(c[:2] == ("pr", "view") for c in calls)  # no GraphQL
    merge = [c for c in calls if c[:3] == ("api", "-X", "PUT")]
    assert merge and "merge_method=merge" in merge[0] and f"sha={sha}" in merge[0]
    labels = [c for c in calls if len(c) > 1 and str(c[1]).endswith("/issues/9/labels")]
    assert labels, "labels must be added (history for demotion) before the merge"


def test_main_skips_when_a_check_is_red(tmp_path, monkeypatch, capsys):
    pol = tmp_path / "p.yaml"
    pol.write_text("auto_merge_classes: [docs-only]\n")
    sha = "b" * 40

    def gh(*a):
        path = a[1]
        if path.endswith("/pulls/9"):
            return {"state": "open", "draft": False, "head": {"ref": "agent/9-1", "sha": sha}, "user": {"login": "x"}}
        if "check-runs" in path:
            return {"check_runs": [{"name": "test", "conclusion": "failure"}]}
        return []

    monkeypatch.setattr(automerge, "_gh", gh)
    monkeypatch.setattr(
        automerge,
        "_git",
        lambda *a: (
            "diff --git a/docs/a.md b/docs/a.md\n--- a/docs/a.md\n+++ b/docs/a.md\n@@ -1 +1 @@\n+x\n" if a[0] == "diff" else ""
        ),
    )
    monkeypatch.setattr(automerge, "fetch_approved", lambda k: [])
    automerge.main(["--pr", "9", "--head-sha", sha, "--policy", str(pol)])
    assert "SKIP checks not green" in capsys.readouterr().out
