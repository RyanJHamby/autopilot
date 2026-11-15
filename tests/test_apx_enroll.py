"""Hands-off enrollment, part 1: discovery. A repo the owner installs the App on gets SHADOW checks with no apx.env edit.

Discovered = listed by an installation apx.env already names, owned by the owner, not held back by policy, and not already in
APX_INSTALLATIONS (an env entry always wins). Shadow = `apx / guard` + `apx / build` only: no agents, merges or branch updates, even
with APX_SHADOW=0. APX_DISCOVERY=0 = env repos only. The listing is cached for at most an hour.
"""

import base64
import datetime as dt
import json
import re

import pytest
from test_apx_daemon import REPO, env
from test_apx_doctor import factory as doctor_factory
from test_apx_doctor import run as run_doctor

from autopilot.apx import caps, enroll
from autopilot.apx import daemon as dm
from autopilot.apx.github import GitHubError

NEW = "RyanJHamby/newthing"
NOW = dt.datetime(2026, 11, 15, 20, 0, tzinfo=dt.timezone.utc)
POLICY = "defaults: {}\nexcluded: [forky]\nrepos:\n  sleepy: {mode: dormant}\n  paused: {mode: standard, enabled: false}\n  ok: {mode: standard}\n"


@pytest.fixture(autouse=True)
def policy(tmp_path, monkeypatch):
    p = tmp_path / "portfolio.yaml"
    p.write_text(POLICY)
    monkeypatch.setattr(caps, "PORTFOLIO_FILE", p)
    return p


class Listing:
    """api_for(repo) for discovery: counts the installation listings it serves."""

    def __init__(self, repos=(REPO, NEW), total=None, fail=False):
        self.repos, self.total, self.fail, self.calls = list(repos), total, fail, 0

    def __call__(self, repo):
        def api(method, path, body=None):
            assert (method, path) == ("GET", "/installation/repositories?per_page=100"), path
            self.calls += 1
            if self.fail:
                raise GitHubError(502, path, "bad gateway")
            items = [r if isinstance(r, dict) else {"full_name": r} for r in self.repos]
            return {"total_count": self.total if self.total is not None else len(items), "repositories": items}

        return api


def settings(tmp_path, **over):
    return dm.Settings.from_env(env(tmp_path, **over))


def test_a_discovered_repo_defaults_to_shadow_even_with_shadow_off_and_an_agent_account(tmp_path):
    s = settings(tmp_path, APX_SHADOW="0", APX_AGENT_USER="apx-agent")
    found, log = enroll.discover(s, Listing(), NOW)
    assert list(found) == [NEW] and found[NEW].state == "shadow" and found[NEW].installation == 11
    s2 = enroll.with_found(s, found)
    meta = dm.plan_repos(s2)
    assert meta[NEW]["contexts"] == ["apx / guard", "apx / build"]
    assert (meta[NEW]["loop"], meta[NEW]["merge"], meta[NEW]["agents"], meta[NEW]["main_check"]) == (False, False, False, False)
    assert meta[NEW]["discovered"] is True
    assert meta[REPO]["loop"] is True and meta[REPO]["discovered"] is False  # the env repo keeps its own settings
    assert s.installations == {REPO: 11}  # the env Settings is not changed
    assert any(NEW in line and "shadow" in line for line in log)


def test_an_env_entry_overrides_discovery(tmp_path):
    s = settings(tmp_path, APX_INSTALLATIONS=f"{REPO}=11", APX_CUTOVER=REPO)
    found, _ = enroll.discover(s, Listing(repos=[REPO]), NOW)
    assert found == {}
    assert dm.plan_repos(enroll.with_found(s, found))[REPO]["loop"] is True


def test_discovery_off_means_env_repos_only_and_no_listing(tmp_path):
    s = settings(tmp_path, APX_DISCOVERY="0")
    lst = Listing()
    found, log = enroll.discover(s, lst, NOW)
    assert found == {} and lst.calls == 0 and "APX_DISCOVERY=0" in log[0]


def test_the_listing_is_cached_for_at_most_an_hour(tmp_path):
    s = settings(tmp_path)
    lst = Listing()
    enroll.discover(s, lst, NOW)
    enroll.discover(s, lst, NOW + dt.timedelta(minutes=59))
    assert lst.calls == 1
    enroll.discover(s, lst, NOW + dt.timedelta(minutes=61))
    assert lst.calls == 2
    assert oct(enroll.cache_path(s).stat().st_mode & 0o777) == "0o600"


@pytest.mark.parametrize("text", ["not json", '{"fetched_at": "2026-11-15T20:00:00+00:00", "repos": {"a/b": "11"}}', "[]"])
def test_a_bad_cache_file_is_ignored(tmp_path, text):
    s = settings(tmp_path)
    enroll.cache_path(s).write_text(text)
    lst = Listing()
    found, _ = enroll.discover(s, lst, NOW)
    assert lst.calls == 1 and list(found) == [NEW]


def test_a_cache_from_the_future_is_ignored(tmp_path):
    s = settings(tmp_path)
    enroll.cache_path(s).write_text(json.dumps({"fetched_at": (NOW + dt.timedelta(hours=2)).isoformat(), "repos": {"RyanJHamby/x": 11}}))
    lst = Listing()
    enroll.discover(s, lst, NOW)
    assert lst.calls == 1


def test_only_the_owners_unheld_unarchived_repos_are_discovered(tmp_path):
    repos = [REPO, NEW, "stranger/x", "RyanJHamby/forky", "RyanJHamby/sleepy", "RyanJHamby/paused", "RyanJHamby/ok",
             {"full_name": "RyanJHamby/old", "archived": True}, {"full_name": "bad name/x"}]
    found, _ = enroll.discover(settings(tmp_path), Listing(repos=repos), NOW)
    assert sorted(found) == [NEW, "RyanJHamby/ok"]


@pytest.mark.parametrize("lst", [Listing(total=101), Listing(fail=True)])
def test_a_listing_that_is_cut_short_or_fails_means_env_only(tmp_path, lst):
    found, log = enroll.discover(settings(tmp_path), lst, NOW)
    assert found == {} and "discovery failed" in log[0]


def test_unreadable_policy_means_env_only(tmp_path, policy):
    policy.write_text("repos: [unclosed")
    found, log = enroll.discover(settings(tmp_path), Listing(), NOW)
    assert found == {} and "discovery failed" in log[0]


def pass_factory(writes):
    def factory(token):
        def api(method, path, body=None):
            if path.startswith("/app/"):
                return {"token": "ghs_x", "expires_at": "2099-01-01T00:00:00Z"}
            if method != "GET":
                writes.append((method, path))
                return {}
            if path.startswith("/installation/repositories"):
                return {"total_count": 2, "repositories": [{"full_name": REPO}, {"full_name": NEW}]}
            if f"/repos/{REPO}/actions/variables/AUTOPILOT_ENABLED" in path:
                return {"value": "true"}
            if "/actions/variables/" in path:
                raise GitHubError(404, path, "")
            if "contents/.autopilot/repo.yaml" in path:
                return {"content": base64.b64encode(b"mode: standard\ntier: A\n").decode()}
            if path.endswith("/git/ref/heads/main"):
                return {"object": {"sha": "m" * 40}}
            if "/check-runs" in path:
                return {"check_runs": []}
            if re.search(r"/pulls/\d+$", path):
                return {"mergeable_state": "clean", "labels": []}
            m = re.match(r"/repos/([^/]+/[^/]+)/pulls\?state=open", path)
            if m:
                sha = ("n" if m.group(1) == NEW else "s") * 40
                return [{"number": 1, "head": {"ref": "agent/5-1", "sha": sha, "repo": {"full_name": m.group(1)}}, "user": {"login": "RyanJHamby"}}]
            return []

        return api

    return factory


def test_a_pass_posts_only_shadow_checks_for_a_discovered_repo(tmp_path, monkeypatch):
    monkeypatch.delenv("APX_LIVE", raising=False)
    writes = []
    out = dm.run_once(settings(tmp_path, APX_SHADOW="0", APX_AGENT_USER="apx-agent"), api_factory=pass_factory(writes))
    assert any(line.startswith(f"discovered: {NEW}") for line in out)
    assert any(line.startswith(f"{NEW}: 1 action(s) - shadow: checks only") for line in out), out
    mine = [line for line in out if line.startswith("DRY-RUN") and NEW in line]
    assert mine and all(line.startswith("DRY-RUN check-pr") for line in mine)
    assert writes == []


def test_a_pass_with_discovery_off_never_touches_the_new_repo(tmp_path, monkeypatch):
    monkeypatch.delenv("APX_LIVE", raising=False)
    out = dm.run_once(settings(tmp_path, APX_DISCOVERY="0"), api_factory=pass_factory([]))
    assert not any(NEW in line for line in out)


def test_doctor_lists_discovered_repos_and_their_state(tmp_path):
    s = settings(tmp_path, APX_SHARED=str(tmp_path / "shared"))
    out = run_doctor(s, api_factory=doctor_factory(repos=[REPO, NEW]))
    assert out[f"installation for {REPO}"].ok, out[f"installation for {REPO}"].detail
    c = out["discovered repos (App installed, not in APX_INSTALLATIONS)"]
    assert c.ok and f"{NEW}: shadow" in c.detail


def test_doctor_with_discovery_off_still_calls_extra_repos_out_of_scope(tmp_path):
    s = settings(tmp_path, APX_SHARED=str(tmp_path / "shared"), APX_DISCOVERY="0")
    out = run_doctor(s, api_factory=doctor_factory(repos=[REPO, NEW]))
    c = out[f"installation for {REPO}"]
    assert not c.ok and "OUT OF SCOPE" in c.detail


def test_doctor_still_calls_a_policy_held_or_foreign_repo_out_of_scope(tmp_path):
    s = settings(tmp_path, APX_SHARED=str(tmp_path / "shared"))
    for extra in ("RyanJHamby/sleepy", "stranger/x"):
        c = run_doctor(s, api_factory=doctor_factory(repos=[REPO, extra]))[f"installation for {REPO}"]
        assert not c.ok and "OUT OF SCOPE" in c.detail and extra in c.detail
