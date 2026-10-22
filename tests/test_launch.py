"""launch-repo against a stateful fake of gh. No command runs for real; an unscripted command fails the test."""

from __future__ import annotations

import argparse
import base64
import json

import pytest

from autopilot import launch, ship

OWNER = "RyanJHamby"
NAME = "newrepo"
SLUG = f"{OWNER}/{NAME}"
OWN = f"{OWNER}/autopilot"
PROBE = "SENTINEL-not-a-real-credential-0123456789"
SCAFFOLD_PR = f"https://github.com/{SLUG}/pull/5"
PORTFOLIO_PR = f"https://github.com/{OWN}/pull/9"


class GH:
    """Just enough of GitHub: every write changes state that the read-back checks then see."""

    def __init__(self):
        self.calls: list[list[str]] = []
        self.stdin: list[tuple[list[str], str]] = []
        self.now = 0.0
        self.repo = {"id": 777, "default_branch": "main", "private": True, "archived": False, "permissions": {"admin": True}}
        self.perm = False
        self.vars: dict[str, str] = {}
        self.labels: set[str] = set()
        self.secrets: set[str] = set()
        self.manifest = False
        self.rulesets: list[dict] = []
        self.issues: list[tuple[str, str]] = []
        self.portfolio_on = False
        self.installs = {
            "autopilot-rollout": {"id": "11", "sel": "selected", "repos": set()},
            "claude": {"id": "22", "sel": "selected", "repos": set()},
        }
        self.api_add_ok = True
        self.ci = ["build", "guard / guard", "automerge / automerge", "dispatch / dispatch"]
        self.open_prs: dict[str, str] = {}
        self.checks = {"default": [{"name": "guard", "bucket": "pass"}]}
        self.drop_var: str | None = None
        self.merged: list[str] = []
        self.scaffolds = 0
        self.portfolio_prs = 0

    # --- fake gh ---
    def run(self, cmd):
        self.calls.append(list(cmd))
        line = " ".join(cmd)
        if cmd[:2] == ["gh", "api"] and len(cmd) == 3 and cmd[2] == f"repos/{SLUG}":
            return 0, json.dumps({**self.repo})
        if line == f"gh api repos/{SLUG}/actions/permissions/workflow":
            return 0, json.dumps({"can_approve_pull_request_reviews": self.perm})
        if line.startswith(f"gh api --method PUT repos/{SLUG}/actions/permissions/workflow"):
            self.perm = True
            return 0, ""
        if line.startswith(f"gh variable list -R {SLUG}"):
            if "--json" in cmd:  # not every gh version has it; the real call must not depend on it
                return 1, "unknown flag: --json"
            return 0, "".join(f"{k}\t{v}\t2026-10-22T11:27:22Z\n" for k, v in self.vars.items())
        if line.startswith("gh variable set"):
            name, val = cmd[3], cmd[5]
            if name != self.drop_var:
                self.vars[name] = val
            return 0, ""
        if line.startswith(f"gh label list -R {SLUG}"):
            return 0, json.dumps([{"name": n} for n in sorted(self.labels)])
        if line.startswith("gh label create"):
            self.labels.add(cmd[3])
            return 0, ""
        if line.startswith(f"gh api repos/{SLUG}/contents/.autopilot/manifest.json"):
            return (0, "{}") if self.manifest else (1, "")
        if line.startswith(f"gh pr list -R {SLUG} --head autopilot/init"):
            return 0, json.dumps([{"url": self.open_prs["scaffold"]}] if "scaffold" in self.open_prs else [])
        if line.startswith(f"gh pr list -R {OWN} --head launch/"):
            return 0, json.dumps([{"url": self.open_prs["portfolio"]}] if "portfolio" in self.open_prs else [])
        if line.startswith("gh pr checks"):
            repo = cmd[cmd.index("--repo") + 1]
            return 0, json.dumps(self.checks.get(repo, self.checks["default"]))
        if line.startswith("gh pr merge"):
            repo = cmd[cmd.index("--repo") + 1]
            self.merged.append(f"{cmd[3]}@{repo}")
            if repo == SLUG:
                self.manifest = True
            if repo == OWN:
                self.portfolio_on = True
            return 0, ""
        if line.startswith(f"gh secret list -R {SLUG}"):
            return 0, json.dumps([{"name": n} for n in sorted(self.secrets)])
        if line.startswith("gh api /user/installations --paginate"):
            return 0, "\n".join(f"{v['id']} {k} {v['sel']}" for k, v in self.installs.items())
        if line.startswith("gh api /user/installations/") and "--paginate" in cmd:
            iid = cmd[2].split("/")[3]
            app = next(v for v in self.installs.values() if v["id"] == iid)
            return 0, "\n".join(str(r) for r in sorted(app["repos"]))
        if line.startswith("gh api --method PUT /user/installations/"):
            if not self.api_add_ok:
                return 1, ""
            parts = cmd[4].split("/")
            app = next(v for v in self.installs.values() if v["id"] == parts[3])
            app["repos"].add(int(parts[5]))
            return 0, ""
        if line.startswith(f"gh api repos/{SLUG}/commits/HEAD/check-runs"):
            return 0, "\n".join(self.ci)
        if line == f"gh api repos/{SLUG}/rulesets":
            return 0, json.dumps(self.rulesets)
        if line.startswith(f"gh api repos/{OWN}/contents/policy/portfolio.yaml"):
            entry = f"  {NAME}: {{tier: B, mode: standard, enabled: true}}\n"
            other = "  other: {tier: C, mode: dormant, enabled: false}\n"
            text = f"owner: {OWNER}\nrepos:\n" + (entry if self.portfolio_on else other)
            return 0, base64.encodebytes(text.encode()).decode()
        if line.startswith(f"gh issue list -R {SLUG}"):
            return 0, json.dumps([{"title": t} for t, _ in self.issues])
        if line.startswith(f"gh issue create -R {SLUG}"):
            self.issues.append((cmd[cmd.index("--title") + 1], cmd[cmd.index("--label") + 1]))
            return 0, ""
        raise AssertionError(f"unscripted command: {line}")

    def run_in(self, cmd, text):
        self.stdin.append((list(cmd), text))
        line = " ".join(cmd)
        if line.startswith(f"gh secret set {launch.SECRET} -R {SLUG}"):
            self.secrets.add(launch.SECRET)
            return 0, ""
        if line.startswith(f"gh api repos/{SLUG}/rulesets") and "--input" in cmd:
            body = json.loads(text)
            kept = [r for r in self.rulesets if r["name"] != body["name"]]
            self.rulesets = kept + [{"id": 1, "name": body["name"], "body": body, "method": cmd[cmd.index("--method") + 1]}]
            return 0, ""
        raise AssertionError(f"unscripted stdin command: {line}")

    def sleep(self, s):
        self.now += s

    def clock(self):
        return self.now

    def scaffold(self, env, ctx):
        self.scaffolds += 1
        return SCAFFOLD_PR

    def portfolio_pr(self, env, ctx):
        self.portfolio_prs += 1
        return PORTFOLIO_PR

    def ran(self, prefix):
        return [c for c in self.calls if " ".join(c).startswith(prefix)]

    def writes(self):
        """Commands that change something."""
        marks = ("gh label create", "gh variable set", "gh pr merge", "gh issue create", "gh api --method")
        return [c for c in self.calls if " ".join(c).startswith(marks)] + [c for c, _ in self.stdin]


def ns(**kw):
    base = dict(repo=NAME, tier="B", mode="standard", kit_repo=None, claude_app="claude", rollout_app="autopilot-rollout",
                token_env=None, smoke=False, allow_public=False, dry_run=False, yes=True, timeout_minutes=20)  # fmt: skip
    base.update(kw)
    return argparse.Namespace(**base)


def mk(gh, *, portfolio=None, ask=lambda _: "y", secret=lambda _: PROBE, lines=None):
    pf = portfolio or {"owner": OWNER, "repos": {}, "excluded": []}
    sink = lines if lines is not None else []
    return launch.LaunchEnv(
        run=gh.run, say=sink.append, ask=ask, sleep=gh.sleep, clock=gh.clock, timeout=600.0,
        run_in=gh.run_in, secret=secret, portfolio=lambda: pf, approved=lambda kit: "d" * 40,
        scaffold=gh.scaffold, portfolio_pr=gh.portfolio_pr,
    )  # fmt: skip


def go(gh, **kw):
    lines: list[str] = []
    env = mk(gh, lines=lines, **{k: kw.pop(k) for k in list(kw) if k in ("portfolio", "ask", "secret")})
    try:
        report = launch.launch(env, ns(**kw))
        return report, lines
    except ship.Stop as e:
        return e, lines


def test_full_launch_runs_every_stage_and_reads_each_one_back():
    gh = GH()
    report, _ = go(gh)
    assert isinstance(report, launch.Report) and report.green
    assert gh.perm and gh.vars == {"AUTOPILOT_DEBUG": "false", "AUTOPILOT_ENABLED": "true"}
    assert gh.labels == set(launch.LABELS) and launch.SECRET in gh.secrets
    assert all(v["repos"] == {777} for v in gh.installs.values())
    assert gh.manifest and gh.portfolio_on and gh.scaffolds == 1 and gh.portfolio_prs == 1
    assert sorted(gh.merged) == sorted([f"5@{SLUG}", f"9@{OWN}"])
    assert [t for t, _ in gh.issues] == [launch.CHARTER_TITLE] and gh.issues[0][1] == "needs-human"


def test_the_token_goes_only_to_stdin_and_never_into_argv_or_output():
    gh = GH()
    _, lines = go(gh)
    assert not any(PROBE in a for c in gh.calls for a in c)
    assert not any(PROBE in a for c, _ in gh.stdin for a in c)
    assert not any(PROBE in ln for ln in lines)
    secret_calls = [(c, t) for c, t in gh.stdin if c[:3] == ["gh", "secret", "set"]]
    assert len(secret_calls) == 1 and secret_calls[0][1] == PROBE


def test_nothing_forces_skips_signing_or_pushes_from_the_orchestrator():
    gh = GH()
    go(gh)
    flat = [a for c in gh.calls for a in c] + [a for c, _ in gh.stdin for a in c]
    assert not {"--force", "--force-with-lease", "--no-verify", "--no-gpg-sign", "push"} & set(flat)
    assert not any(c[:3] == ["gh", "pr", "review"] for c in gh.calls)


def test_second_run_changes_nothing():
    gh = GH()
    go(gh)
    before = len(gh.calls)
    gh.scaffolds = gh.portfolio_prs = 0
    report, _ = go(gh)
    assert report.green
    marks = ("gh label create", "gh variable set", "gh pr merge", "gh issue create", "gh api --method")
    assert not [c for c in gh.calls[before:] if " ".join(c).startswith(marks)]
    assert gh.scaffolds == 0 and gh.portfolio_prs == 0 and len(gh.stdin) == 2  # only the first run's secret + ruleset


def test_dry_run_writes_nothing():
    gh = GH()
    report, lines = go(gh, dry_run=True)
    assert not gh.writes() and gh.scaffolds == 0 and gh.portfolio_prs == 0 and not gh.stdin
    assert any("todo" in ln for ln in lines) and any("dry run" in ln for ln in lines)
    assert not report.green


RESTRICTED = {"owner": OWNER, "repos": {NAME: {"data_class": "restricted"}}, "excluded": []}


@pytest.mark.parametrize(
    "setup, kw, reason",
    [
        (lambda g: None, {"portfolio": {"owner": OWNER, "repos": {}, "excluded": [NAME]}}, "excluded"),
        (lambda g: None, {"portfolio": RESTRICTED}, "restricted"),
        (lambda g: None, {"repo": "someone-else/thing"}, "not in RyanJHamby's account"),
        (lambda g: g.repo.update(archived=True), {}, "archived"),
        (lambda g: g.repo.update(permissions={"admin": False}), {}, "not an admin"),
        (lambda g: g.repo.update(private=False), {}, "public"),
        (lambda g: g.repo.pop("id"), {}, "cannot read"),
        (lambda g: None, {"mode": None, "tier": None}, "is new"),
        (lambda g: None, {"repo": "bad name; x"}, "not a repo name"),
    ],
)
def test_refusals_stop_before_anything_is_written(setup, kw, reason):
    gh = GH()
    setup(gh)
    result, _ = go(gh, **kw)
    assert isinstance(result, ship.Stop) and reason in str(result)
    assert not gh.writes() and gh.scaffolds == 0


def test_a_public_repo_can_be_launched_only_with_the_explicit_flag():
    gh = GH()
    gh.repo["private"] = False
    report, _ = go(gh, allow_public=True)
    assert report.green


def test_an_existing_portfolio_entry_supplies_tier_and_mode():
    gh = GH()
    pf = {"owner": OWNER, "repos": {NAME: {"tier": "C", "mode": "yolo", "enabled": False}}, "excluded": []}
    report, _ = go(gh, portfolio=pf, tier=None, mode=None)
    assert report.green


def test_dormant_mode_is_refused_because_launch_enables_the_repo():
    pf = {"owner": OWNER, "repos": {NAME: {"tier": "C", "mode": "dormant"}}, "excluded": []}
    result, _ = go(GH(), portfolio=pf, tier=None, mode=None)
    assert isinstance(result, ship.Stop) and "dormant" in str(result)


def test_declining_or_having_no_terminal_changes_nothing():
    def eof(_):
        raise EOFError

    for ask in (lambda _: "n", eof):
        gh = GH()
        result, _ = go(gh, yes=False, ask=ask)
        assert isinstance(result, ship.Stop) and "not confirmed" in str(result)
        assert not gh.writes()


def test_resumes_after_a_partial_run():
    gh = GH()
    gh.perm, gh.vars, gh.labels, gh.manifest = True, {"AUTOPILOT_DEBUG": "false"}, set(launch.LABELS), True
    report, lines = go(gh)
    assert report.green and gh.scaffolds == 0
    assert any(ln.strip().startswith("ok") and "labels" in ln for ln in lines)


def test_an_open_scaffold_pr_is_reused_not_recreated():
    gh = GH()
    gh.open_prs["scaffold"] = SCAFFOLD_PR
    report, _ = go(gh)
    assert report.green and gh.scaffolds == 0 and f"5@{SLUG}" in gh.merged


def test_failing_scaffold_checks_leave_the_pr_unmerged():
    gh = GH()
    gh.checks[SLUG] = [{"name": "guard", "bucket": "fail"}]
    result, _ = go(gh)
    assert isinstance(result, ship.Stop) and "checks failed" in str(result)
    assert not gh.merged


def test_a_new_repo_with_no_ci_at_all_still_gets_its_scaffold_merged():
    gh = GH()
    gh.checks[SLUG] = []
    report, _ = go(gh)
    assert report.green and f"5@{SLUG}" in gh.merged and gh.now >= ship.NO_CHECKS_GRACE


def test_red_checks_on_the_portfolio_pr_stop_before_its_merge():
    gh = GH()
    gh.checks[OWN] = [{"name": "test", "bucket": "fail"}]
    result, _ = go(gh)
    assert isinstance(result, ship.Stop) and f"9@{OWN}" not in gh.merged


def test_a_change_that_does_not_read_back_stops_the_run():
    gh = GH()
    gh.drop_var = "AUTOPILOT_DEBUG"  # GitHub accepts the write but the variable never shows up
    result, _ = go(gh)
    assert isinstance(result, ship.Stop) and "does not read back" in str(result)
    assert gh.scaffolds == 0 and not gh.labels  # later stages did not run


def test_token_from_the_environment_and_its_failure_modes(monkeypatch):
    monkeypatch.setenv("LAUNCH_T", PROBE)
    gh = GH()
    report, _ = go(gh, token_env="LAUNCH_T")
    assert report.green and any(t == PROBE for _, t in gh.stdin)
    monkeypatch.delenv("LAUNCH_T")
    result, _ = go(GH(), token_env="LAUNCH_T")
    assert isinstance(result, ship.Stop) and "not set" in str(result)
    result, _ = go(GH(), secret=lambda _: "   ")
    assert isinstance(result, ship.Stop) and "empty token" in str(result)


def test_an_existing_secret_is_left_alone():
    gh = GH()
    gh.secrets.add(launch.SECRET)
    report, _ = go(gh)
    assert report.green and not [c for c, _ in gh.stdin if c[:3] == ["gh", "secret", "set"]]


def test_apps_all_repositories_installation_needs_no_change():
    gh = GH()
    for v in gh.installs.values():
        v["sel"] = "all"
    report, _ = go(gh)
    assert report.green and not gh.ran("gh api --method PUT /user/installations")


def test_apps_fall_back_to_the_url_when_the_api_refuses_and_verify_afterwards():
    gh = GH()
    gh.api_add_ok = False
    seen: list[str] = []

    def ask(prompt):
        if "added?" in prompt:
            seen.append(prompt)
            for v in gh.installs.values():
                v["repos"].add(777)
            return ""
        return "y"

    report, lines = go(gh, yes=False, ask=ask)
    assert report.green and seen
    assert any("settings/installations/11" in ln for ln in lines)


def test_apps_fallback_never_claims_success_unverified_or_without_a_terminal():
    gh = GH()
    gh.api_add_ok = False
    result, _ = go(gh, yes=False, ask=lambda p: "" if "added?" in p else "y")
    assert isinstance(result, ship.Stop) and "still not on" in str(result)

    gh2 = GH()
    gh2.api_add_ok = False

    def ask(p):
        if "added?" in p:
            raise EOFError
        return "y"

    result, _ = go(gh2, yes=False, ask=ask)
    assert isinstance(result, ship.Stop) and "no terminal" in str(result)


def test_apps_stage_still_runs_when_only_one_app_has_the_repo():
    gh = GH()
    gh.installs["autopilot-rollout"]["repos"].add(777)
    report, _ = go(gh)
    assert report.green and gh.installs["claude"]["repos"] == {777}
    assert len(gh.ran("gh api --method PUT /user/installations/22")) == 1
    assert not gh.ran("gh api --method PUT /user/installations/11")


def test_a_missing_app_installation_is_named():
    gh = GH()
    del gh.installs["claude"]
    result, _ = go(gh)
    assert isinstance(result, ship.Stop) and "claude" in str(result) and "github.com/apps/claude" in str(result)
    assert not gh.portfolio_on  # later stages did not run


def test_ruleset_requires_guard_plus_the_repos_own_ci_but_not_autopilot_checks():
    gh = GH()
    go(gh)
    body = gh.rulesets[0]["body"]
    flat = json.dumps(body)
    assert "guard / guard" in flat and "build" in flat
    assert "automerge" not in flat and "dispatch" not in flat
    assert gh.rulesets[0]["method"] == "POST"


def test_an_existing_ruleset_is_updated_in_place():
    from autopilot import cli

    gh = GH()
    name = cli.ruleset_json(["guard / guard"])["name"]
    gh.rulesets = [{"id": 42, "name": name}]
    gh.vars["AUTOPILOT_ENABLED"] = "false"
    go(gh)
    put = [c for c, _ in gh.stdin if "--input" in c]
    assert put and put[0][put[0].index("--method") + 1] == "PUT" and put[0][2].endswith("/42")


def test_smoke_opens_one_extra_agent_ready_issue():
    gh = GH()
    go(gh, smoke=True)
    assert sorted(gh.issues) == sorted([(launch.CHARTER_TITLE, "needs-human"), (launch.SMOKE_TITLE, "agent-ready")])


def test_main_exits_nonzero_with_the_reason_on_a_stop(monkeypatch, capsys):
    monkeypatch.setattr(launch, "sh", lambda cmd: (1, ""))
    monkeypatch.setattr(launch, "_load_portfolio", lambda: {"owner": OWNER, "repos": {}, "excluded": []})
    assert launch.main([NAME, "--tier", "B", "--mode", "standard", "--yes"]) == 1
    assert "STOPPED" in capsys.readouterr().out
