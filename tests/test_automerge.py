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
