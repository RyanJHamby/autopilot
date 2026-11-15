"""Hands-off enrollment, part 2: a discovered repo goes LIVE only when its default-branch .autopilot/repo.yaml says `apx: live` AND
the latest commit touching that file is Verified and authored-and-committed by the owner or in a PR the owner merged, AND apx knows its
CI (repo.yaml `ci:` plus a ruleset requiring `guard / guard` and one CI check; or `private_ci: true` with a repo_ci.json entry), AND its
declared host tools pass the doctor's check as the sandbox account. Anything else: shadow, with the reason.
"""

import base64
import datetime as dt

import pytest
from test_apx_daemon import env

from autopilot.apx import daemon as dm
from autopilot.apx import doctor, enroll, repo_ci
from autopilot.apx.github import GitHubError

NEW = "RyanJHamby/newthing"
OWNER = "RyanJHamby"
NOW = dt.datetime(2026, 11, 15, 20, 0, tzinfo=dt.timezone.utc)
LIVE_YAML = "mode: standard\ntier: B\napx: live\nci:\n  - \"uv run pytest -q\"\n"
RULES = [{"type": "required_status_checks", "parameters": {"required_status_checks": [{"context": "guard / guard"}, {"context": "test"}]}}]


def commit(author=OWNER, committer="web-flow", verified=True):
    return {"sha": "c" * 40, "commit": {"verification": {"verified": verified}}, "author": {"login": author}, "committer": {"login": committer}}


class Repo:
    """One discovered repo's GitHub, as promotion reads it."""

    def __init__(self, yaml_text=LIVE_YAML, commits=None, prs=(), rules=RULES, fail=False):
        self.yaml, self.commits, self.prs, self.rules, self.fail = yaml_text, [commit()] if commits is None else commits, list(prs), rules, fail

    def __call__(self, repo):
        def api(method, path, body=None):
            assert method == "GET", path
            if self.fail:
                raise GitHubError(500, path, "x")
            if path == f"/repos/{repo}":
                return {"default_branch": "trunk", "private": True}
            if path == f"/repos/{repo}/contents/.autopilot/repo.yaml?ref=trunk":
                if self.yaml is None:
                    raise GitHubError(404, path, "nf")
                return {"content": base64.b64encode(self.yaml.encode()).decode()}
            if path == f"/repos/{repo}/commits?sha=trunk&path=.autopilot/repo.yaml&per_page=1":
                return self.commits
            if path == f"/repos/{repo}/commits/{'c' * 40}/pulls":
                return [{"number": p["number"], "merged_at": p.get("merged_at")} for p in self.prs]
            if path.startswith(f"/repos/{repo}/pulls/"):
                n = int(path.rsplit("/", 1)[1])
                return next(p for p in self.prs if p["number"] == n)
            if path == f"/repos/{repo}/rules/branches/trunk":
                return self.rules
            raise AssertionError(path)

        return api


def found():
    return {NEW: enroll.Found(NEW, 11, "shadow", "discovered (App installed); shadow by default")}


@pytest.fixture
def s(tmp_path):
    return dm.Settings.from_env(env(tmp_path, APX_CI_USER="apx-ci"))


def run(s, gh, tools=lambda repo, private: []):
    out, _ = enroll.promote(s, found(), gh, tools)
    return out[NEW]


def test_live_when_the_owner_set_it_verified_with_a_known_ci_and_tools(s):
    f = run(s, Repo())
    assert f.state == "live", f.reason
    meta = dm.plan_repos(enroll.with_found(s, {NEW: f}))[NEW]
    assert meta["loop"] is True and meta["contexts"] == ["guard / guard", "test"] and meta["discovered"] is True


def test_live_when_the_change_came_in_a_pr_the_owner_merged(s):
    pr = {"number": 4, "merged_at": "2026-11-15T19:00:00Z", "merged_by": {"login": OWNER}}
    assert run(s, Repo(commits=[commit(author="someone", committer="someone")], prs=[pr])).state == "live"


@pytest.mark.parametrize(
    "gh, why",
    [
        (Repo(commits=[commit(author="agent-bot", committer="agent-bot")]), "owner"),
        (Repo(commits=[commit(author=OWNER, committer="agent-bot")]), "owner"),  # a forged author is not enough
        (Repo(commits=[commit(verified=False)]), "Verified"),
        (Repo(commits=[]), "no commit"),
        (Repo(commits=[commit(author="x", committer="x")], prs=[{"number": 4, "merged_at": "t", "merged_by": {"login": "autopilot-apx[bot]"}}]), "merged by"),
    ],
)
def test_non_owner_or_unverified_stays_shadow(s, gh, why):
    f = run(s, gh)
    assert f.state == "shadow" and why in f.reason


def test_without_apx_live_it_stays_shadow(s):
    for text in ("mode: standard\n", "apx: shadow\n", None):
        f = run(s, Repo(yaml_text=text))
        assert f.state == "shadow"


def test_missing_tools_keep_it_shadow_and_say_which(s):
    f = run(s, Repo(), tools=lambda repo, private: ["host tool rustc: missing on the sandbox PATH"])
    assert f.state == "shadow" and "rustc" in f.reason


def test_no_sandbox_account_keeps_it_shadow(tmp_path):
    s = dm.Settings.from_env(env(tmp_path))
    f = run(s, Repo(), tools=None)
    assert f.state == "shadow" and "APX_CI_USER" in f.reason


def test_no_ci_list_or_no_usable_ruleset_keeps_it_shadow(s):
    assert "ci:" in run(s, Repo(yaml_text="apx: live\n")).reason
    no_guard = [{"type": "required_status_checks", "parameters": {"required_status_checks": [{"context": "test"}]}}]
    assert "guard / guard" in run(s, Repo(rules=no_guard)).reason
    assert run(s, Repo(rules=[])).state == "shadow"


def test_private_ci_needs_a_repo_ci_entry_and_then_is_checks_only(s, monkeypatch):
    gh = Repo(yaml_text="apx: live\nprivate_ci: true\n")
    f = run(s, gh)
    assert f.state == "shadow" and "repo_ci.json" in f.reason
    spec = repo_ci.parse_spec(NEW, {"checks": [{"context": "check", "steps": ["make check"]}], "tools": ["make"]})
    monkeypatch.setattr(repo_ci, "load_specs", lambda path=repo_ci.SPEC_FILE: {NEW: spec})
    seen = []
    f = run(s, gh, tools=lambda repo, private: seen.append(private) or [])
    assert f.state == "live" and seen == [True]
    meta = dm.plan_repos(enroll.with_found(s, {NEW: f}))[NEW]
    assert meta["spec_ci"] is True and meta["loop"] is False and meta["contexts"] == ["check"]


def test_a_read_error_keeps_it_shadow(s):
    f = run(s, Repo(fail=True))
    assert f.state == "shadow" and "could not" in f.reason


def test_the_doctor_shows_live_or_shadow_with_the_reason(s):
    lines = doctor.discovered_lines(enroll.promote(s, found(), Repo(commits=[commit(verified=False)]), lambda r, p: [])[0])
    assert lines == [f"{NEW}: shadow (latest .autopilot/repo.yaml commit is not Verified)"]
