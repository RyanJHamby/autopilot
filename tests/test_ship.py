"""ship-kit against a scripted fake of git and gh. No command is run for real; an unscripted command fails the test."""

from __future__ import annotations

import json

import pytest

from autopilot import ship

KIT = "d" * 40
MERGE_SHA = "c" * 40
OWNER = "RyanJHamby"
REPO = f"{OWNER}/autopilot"
BUMPS = {
    "stencil": ("https://github.com/RyanJHamby/stencil/pull/82", "82"),
    "autopilot": ("https://github.com/RyanJHamby/autopilot/pull/71", "71"),
    "drillpad-workspace": ("https://github.com/RyanJHamby/drillpad-workspace/pull/60", "60"),
}


class Fake:
    def __init__(self):
        self.calls: list[list[str]] = []
        self.handlers: list[tuple[str, object]] = []
        self.now = 0.0

    def on(self, prefix: str, response):
        self.handlers.append((prefix, response))

    def run(self, cmd):
        self.calls.append(list(cmd))
        line = " ".join(cmd)
        for prefix, response in reversed(self.handlers):
            if line.startswith(prefix):
                if isinstance(response, list):
                    r = response.pop(0) if len(response) > 1 else response[0]
                else:
                    r = response
                return r(cmd) if callable(r) else r
        raise AssertionError(f"unscripted command: {line}")

    def sleep(self, s):
        self.now += s

    def clock(self):
        return self.now

    def ran(self, prefix: str) -> list[list[str]]:
        return [c for c in self.calls if " ".join(c).startswith(prefix)]


def pr_json(state="OPEN", author="app/autopilot-rollout", head=f"autopilot/kit-bump-{KIT[:7]}", oid="e" * 40):
    return (0, json.dumps({"state": state, "author": {"login": author}, "headRefName": head, "headRefOid": oid}))


def checks(*buckets):
    return (0, json.dumps([{"name": f"c{i}", "bucket": b} for i, b in enumerate(buckets)]))


RELEASE_LOG = "\n".join(
    [f"release\tRelease\t2026-10-21Z kit_sha={KIT}"]
    + [f"release\tRoll out\t2026-10-21Z {OWNER}/{name}: {url}" for name, (url, _) in BUMPS.items()]
)


def scripted(files="kit/runtime/tier.py\ntests/test_x.py\n", sig="G", bumps=None) -> Fake:
    f = Fake()
    f.on("git branch --show-current", (0, "feat-x\n"))
    f.on("git status --porcelain", (0, ""))
    f.on("git fetch origin main", (0, ""))
    f.on("git merge-base --is-ancestor", (0, ""))
    f.on("git diff --name-only", (0, files))
    f.on("git log --format=%H %G?", (0, f"{'a' * 40} {sig}\n"))
    f.on("gh repo view", (0, REPO + "\n"))
    f.on("git diff --stat", (0, " 2 files changed\n"))
    f.on("env PYTHONPATH=src uv run python -m pytest", (0, "ok"))
    f.on("git push -u origin feat-x", (0, ""))
    f.on("gh pr view feat-x", (1, ""))
    f.on("git log -1 --format=%s", (0, "kit: a change\n"))
    f.on("gh pr create", (0, f"https://github.com/{REPO}/pull/70\n"))
    f.on(f"gh pr checks 70 --repo {REPO}", checks("pass", "pass"))
    f.on(f"gh pr merge 70 --repo {REPO}", (0, ""))
    f.on(
        f"gh pr view 70 --repo {REPO} --json state,mergeCommit",
        (0, json.dumps({"state": "MERGED", "mergeCommit": {"oid": MERGE_SHA}})),
    )
    f.on("gh run list", (0, json.dumps([{"databaseId": 9, "url": "https://github.com/x/actions/runs/9"}])))
    f.on("gh run watch", (0, ""))
    f.on("gh run view 9", (0, RELEASE_LOG))
    f.on("gh pr list", (0, "[]"))
    for name, (_, n) in BUMPS.items():
        r = f"{OWNER}/{name}"
        f.on(f"gh pr view {n} --repo {r} --json state,author", (bumps or {}).get(name, pr_json()))
        f.on(f"gh pr checks {n} --repo {r}", checks("pass", "pass"))
        f.on(f"gh pr merge {n} --repo {r}", (0, ""))
    return f


def go(f: Fake, *, yes=True, dry=False, answer="y"):
    lines: list[str] = []
    env = ship.Env(run=f.run, say=lines.append, ask=lambda _: answer, sleep=f.sleep, clock=f.clock, timeout=600.0)
    try:
        result = ship.ship(env, assume_yes=yes, dry_run=dry)
        code = ship.print_result(env, result)
        return code, result, lines
    except ship.Stop as e:
        return None, e, lines


def merges(f: Fake) -> list[str]:
    return sorted(c[3] + "@" + c[c.index("--repo") + 1] for c in f.ran("gh pr merge"))


def test_happy_path_merges_exactly_the_kit_pr_and_the_three_verified_bumps():
    f = scripted()
    code, result, _ = go(f)
    assert code == 0 and not result.left_open
    assert merges(f) == sorted([f"70@{REPO}", f"82@{OWNER}/stencil", f"71@{OWNER}/autopilot", f"60@{OWNER}/drillpad-workspace"])
    assert all("--merge" in c and "--admin" in c for c in f.ran("gh pr merge"))
    assert not f.ran("git push -f") and f.ran("git push -u origin feat-x")


def test_bump_merges_are_pinned_to_the_head_that_was_checked():
    f = scripted()
    go(f)
    for c in f.ran("gh pr merge"):
        if c[3] != "70":
            assert c[c.index("--match-head-commit") + 1] == "e" * 40


def test_nothing_ever_forces_or_skips_signing():
    f = scripted()
    go(f)
    flat = [a for c in f.calls for a in c]
    assert not {"-f", "--force", "--force-with-lease", "--no-gpg-sign", "-n", "--no-verify"} & set(flat)
    assert not any(c[:2] == ["gh", "api"] for c in f.calls)


@pytest.mark.parametrize(
    "setup, reason",
    [
        (lambda f: f.on("git branch --show-current", (0, "main\n")), "not from main"),
        (lambda f: f.on("git branch --show-current", (0, "\n")), "from a branch"),
        (lambda f: f.on("git status --porcelain", (0, " M kit/x\n")), "uncommitted"),
        (lambda f: f.on("git merge-base --is-ancestor", (1, "")), "on top of origin/main"),
        (lambda f: f.on("git diff --name-only", (0, "")), "no changes"),
        (lambda f: f.on("git diff --name-only", (0, "kit/a.py\n.github/workflows/x.yml\n")), "also touched"),
        (lambda f: f.on("git diff --name-only", (0, "src/autopilot/cli.py\nkit/a.py\n")), "also touched"),
        (lambda f: f.on("git diff --name-only", (0, "tests/test_x.py\ndocs/a.md\n")), "no kit/ file"),
        (lambda f: f.on("git log --format=%H %G?", (0, f"{'a' * 40} N\n")), "not signed"),
        (lambda f: f.on("git log --format=%H %G?", (0, f"{'a' * 40} G\n{'b' * 40} E\n")), "not signed"),
    ],
)
def test_preflight_refusals_stop_before_anything_is_pushed(setup, reason):
    f = scripted()
    setup(f)
    code, err, _ = go(f)
    assert code is None and reason in str(err)
    assert not f.ran("git push") and not f.ran("gh pr")


def test_failing_tests_stop_before_the_push():
    f = scripted()
    f.on("env PYTHONPATH=src uv run python -m pytest", (1, "F\n1 failed\n"))
    code, err, _ = go(f)
    assert code is None and "tests failed" in str(err) and "1 failed" in str(err)
    assert not f.ran("git push")


def test_dry_run_stops_after_the_tests():
    f = scripted()
    code, _, lines = go(f, dry=True)
    assert code is None or code == 0
    assert not f.ran("git push") and not f.ran("gh pr")
    assert any("dry run" in ln for ln in lines)


def test_declining_the_confirmation_pushes_nothing():
    f = scripted()
    code, err, _ = go(f, yes=False, answer="n")
    assert code is None and "not confirmed" in str(err)
    assert not f.ran("git push")
    f2 = scripted()
    code, _, _ = go(f2, yes=False, answer="y")
    assert code == 0 and f2.ran("git push -u origin feat-x")


def test_no_terminal_to_ask_on_is_a_clean_no(capsys):
    f = scripted()

    def eof(_):
        raise EOFError

    lines: list[str] = []
    env = ship.Env(run=f.run, say=lines.append, ask=eof, sleep=f.sleep, clock=f.clock, timeout=600.0)
    with pytest.raises(ship.Stop) as e:
        ship.ship(env, assume_yes=False, dry_run=False)
    assert "not confirmed" in str(e.value) and "--yes" in str(e.value)
    assert not f.ran("git push") and not f.ran("gh pr")


def test_red_kit_pr_checks_leave_it_unmerged():
    f = scripted()
    f.on(f"gh pr checks 70 --repo {REPO}", checks("pass", "fail"))
    code, err, _ = go(f)
    assert code is None and "checks failed" in str(err)
    assert not f.ran("gh pr merge")


def test_pending_checks_are_waited_for():
    f = scripted()
    f.on(f"gh pr checks 70 --repo {REPO}", [checks("pass", "pending"), checks("pass", "pending"), checks("pass", "pass")])
    code, _, _ = go(f)
    assert code == 0 and f.now > 0


def test_a_pr_with_no_checks_ever_is_not_merged():
    f = scripted()
    f.on(f"gh pr checks 70 --repo {REPO}", (1, ""))
    code, err, _ = go(f)
    assert code is None and "no checks reported" in str(err)
    assert not f.ran("gh pr merge")


def test_existing_open_pr_is_reused_not_recreated():
    f = scripted()
    f.on("gh pr view feat-x", (0, json.dumps({"number": 70, "state": "OPEN", "url": f"https://github.com/{REPO}/pull/70"})))
    code, _, _ = go(f)
    assert code == 0 and not f.ran("gh pr create")


def test_release_that_never_starts_stops_the_script():
    f = scripted()
    f.on("gh run list", (0, "[]"))
    code, err, _ = go(f)
    assert code is None and "never started" in str(err)
    assert len(f.ran("gh pr merge")) == 1  # only the kit PR was merged


def test_failed_release_run_does_not_touch_bumps():
    f = scripted()
    f.on("gh run watch", (1, ""))
    code, err, _ = go(f)
    assert code is None and "release run failed" in str(err)
    assert len(f.ran("gh pr merge")) == 1


def test_release_with_no_new_kit_sha_is_a_clean_finish():
    f = scripted()
    f.on("gh run view 9", (0, "kit repo already matches this tree: nothing to publish"))
    code, result, _ = go(f)
    assert code == 0 and any("published nothing" in n for n in result.notes)
    assert len(f.ran("gh pr merge")) == 1


@pytest.mark.parametrize(
    "bad",
    [
        pr_json(author="someone-else"),
        pr_json(author="RyanJHamby"),
        pr_json(head="feature/x"),
        pr_json(head="autopilot/kit-bump-abcdef0"),
        pr_json(state="CLOSED"),
    ],
)
def test_unexpected_bump_prs_are_never_merged(bad):
    f = scripted(bumps={"stencil": bad})
    code, result, _ = go(f)
    assert code == 1 and len(result.left_open) == 1
    assert not any(c[3] == "82" for c in f.ran("gh pr merge"))
    assert len(f.ran("gh pr merge")) == 3  # kit PR plus the two good bumps


def test_red_bump_is_left_open_and_the_others_still_ship():
    f = scripted()
    f.on(f"gh pr checks 60 --repo {OWNER}/drillpad-workspace", checks("pass", "fail"))
    code, result, lines = go(f)
    assert code == 1 and "drillpad-workspace" in result.left_open[0]
    assert not any(c[3] == "60" for c in f.ran("gh pr merge"))
    assert len(f.ran("gh pr merge")) == 3
    assert any("OPEN:" in ln for ln in lines)


def test_a_bump_the_repos_own_automerge_already_merged_is_not_merged_again():
    f = scripted(bumps={"stencil": pr_json(state="MERGED")})
    code, result, _ = go(f)
    assert code == 0 and not any(c[3] == "82" for c in f.ran("gh pr merge"))
    assert any("own automerge" in s for s in result.shipped)


def test_bump_that_changes_while_waiting_is_left_alone():
    f = scripted()
    f.on(
        f"gh pr view 82 --repo {OWNER}/stencil --json state,author",
        [pr_json(), pr_json(head="somebody/else")],
    )
    code, result, _ = go(f)
    assert code == 1 and any("changed while waiting" in s for s in result.left_open)
    assert not any(c[3] == "82" for c in f.ran("gh pr merge"))


def test_a_bump_in_someone_elses_repo_is_refused():
    f = scripted()
    f.on("gh run view 9", (0, f"kit_sha={KIT}\nother/repo: https://github.com/other/repo/pull/5"))
    code, result, _ = go(f)
    assert code == 1 and "not in RyanJHamby's repos" in result.left_open[0]
    assert len(f.ran("gh pr merge")) == 1


def test_superseded_bump_prs_are_reported_never_closed():
    f = scripted()
    f.on(
        f"gh pr list --repo {OWNER}/stencil",
        (
            0,
            json.dumps(
                [
                    {
                        "number": 81,
                        "headRefName": "autopilot/kit-bump-86d07ad",
                        "url": "https://github.com/RyanJHamby/stencil/pull/81",
                    }
                ]
            ),
        ),
    )
    code, result, _ = go(f)
    assert code == 0 and any("pull/81" in n and "gh pr close 81" in n for n in result.notes)
    assert not f.ran("gh pr close")


def test_main_returns_nonzero_on_stop(monkeypatch, capsys):
    monkeypatch.setattr(ship, "sh", lambda cmd: (0, "main\n") if cmd[:3] == ["git", "branch", "--show-current"] else (0, ""))
    assert ship.main(["--yes"]) == 1
    assert "STOPPED" in capsys.readouterr().out
