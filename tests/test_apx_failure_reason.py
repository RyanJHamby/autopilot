"""A failed agent run keeps its reason: in the ledger, in one issue comment, and in the executor log line (incident 2026-11-15:
stencil #22 failed and only `run-agent ... failure` plus a needs-human label were left)."""

import sqlite3

from autopilot.apx import executor as ex
from autopilot.apx.ledger import NOTE_MAX, Ledger
from autopilot.apx.planner import Action
from autopilot.apx.redact import MARK

REPO = "RyanJHamby/stencil"
HEAD = "a" * 40


class Api:
    def __init__(self, *, fail_comments=False, pr=None):
        self.calls, self.fail_comments, self.pr = [], fail_comments, pr

    def __call__(self, method, path, body=None):
        self.calls.append((method, path, body))
        if self.fail_comments and method == "POST" and path.endswith("/comments"):
            raise OSError("comment post failed")
        if method == "GET" and self.pr is not None and "/pulls/" in path:
            return self.pr
        return {}

    def comments(self):
        return [c for c in self.calls if c[0] == "POST" and c[1].endswith("/comments")]

    def labels(self):
        return [c for c in self.calls if c[1].endswith("/labels")]


def deps(result=None, err=None):
    def work(repo, issue, run_id):
        if err:
            raise err
        return result

    return ex.Deps(None, None, None, work, fix_ci=lambda *a: result)  # type: ignore[arg-type]


def agent(detail="model=sonnet turns=40"):
    return Action("run-agent", REPO, "22", detail)


def note(led, run_id=1):
    return led.db.execute("select note from runs where id=?", (run_id,)).fetchone()["note"]


FAILED = ex.IssueResult(False, "model says: here is what I tried", problems="protected-path: .github/x.yml", turns=12, model="sonnet",
                        cost_usd=1.234)


def run(api, led, d, action, private=frozenset()):
    return ex.execute(api, led, d, [action], contexts={}, head_refs={}, dry_run=False, private_repos=private)


def test_a_failed_run_stores_its_reason_in_the_ledger():
    led = Ledger()
    run(Api(), led, deps(FAILED), agent())
    assert "protected-path: .github/x.yml" in note(led)


def test_the_reason_is_truncated_and_secrets_are_redacted():
    led = Ledger()
    secret = "ghp_" + "A" * 36
    r = ex.IssueResult(False, problems=f"leaked {secret} " + "x" * 5000)
    run(Api(), led, deps(r), agent())
    n = note(led)
    assert secret not in n and MARK in n and len(n) <= NOTE_MAX


def test_an_old_ledger_file_gains_the_note_column(tmp_path):
    p = tmp_path / "old.sqlite"
    db = sqlite3.connect(p)
    db.execute("create table runs (id integer primary key autoincrement, repo text not null, issue integer not null, hard integer not null "
               "default 0, created_at text not null, finished_at text, status text not null default 'in_progress', conclusion text, "
               "model text, turns integer)")
    db.execute("insert into runs (repo, issue, created_at) values ('r', 1, '2026-01-01T00:00:00Z')")
    db.commit()
    db.close()
    led = Ledger(str(p))
    assert "note" in {r["name"] for r in led.db.execute("pragma table_info(runs)")}
    led.finish(1, "failure", note="why")
    assert note(led) == "why"


def test_a_failure_posts_exactly_one_comment_with_turns_cost_reason_and_run_id():
    api, led = Api(), Ledger()
    run(api, led, deps(FAILED), agent())
    (c,) = api.comments()
    body = c[2]["body"]
    assert c[1] == f"/repos/{REPO}/issues/22/comments"
    assert body.startswith("apx agent run failed: ")
    assert "protected-path: .github/x.yml" in body
    assert "Turns: 12 of 40." in body and "Estimated cost: $1.23 (API-equivalent)." in body
    assert "Run id: 1." in body and "Remove `needs-human` to retry." in body
    assert len(api.labels()) == 1


def test_a_public_repo_never_gets_the_model_output_in_the_comment_or_the_ledger():
    api, led = Api(), Ledger()
    r = ex.IssueResult(False, "model says: secret plan", problems="tests failed\n```\nraw tail of a command\n```", turns=1)
    run(api, led, deps(r), agent())
    body = api.comments()[0][2]["body"]
    for text in (body, note(led)):
        assert "model says" not in text and "raw tail" not in text and "tests failed" in text and "withheld" in text


def test_a_private_repo_keeps_the_redacted_model_summary():
    api, led = Api(), Ledger()
    run(api, led, deps(FAILED), agent(), private=frozenset({REPO}))
    assert "here is what I tried" in api.comments()[0][2]["body"] and "here is what I tried" in note(led)


def test_a_failing_comment_post_does_not_crash_the_pass():
    api, led = Api(fail_comments=True), Ledger()
    log = run(api, led, deps(FAILED), agent())
    assert log[0].startswith(f"run-agent {REPO} #22 failure") and "crashed" not in log[0]
    assert led.runs(REPO)[0]["conclusion"] == "failure" and len(api.labels()) == 1


def test_success_posts_no_comment_and_stores_no_note():
    api, led = Api(), Ledger()
    log = run(api, led, deps(ex.IssueResult(True, "done", pr_number=5, turns=3)), agent())
    assert api.comments() == [] and note(led) is None and log == [f"run-agent {REPO} #22 success"]


def test_the_log_line_carries_the_first_200_chars_of_the_reason():
    r = ex.IssueResult(False, problems="first reason " + "y" * 400)
    log = run(Api(), Ledger(), deps(r), agent())
    assert log[0].startswith(f"run-agent {REPO} #22 failure: first reason yyy")
    assert len(log[0]) <= len(f"run-agent {REPO} #22 failure: ") + 200


def test_a_crashed_run_still_records_a_reason_and_comments_once():
    api, led = Api(), Ledger()
    log = run(api, led, deps(err=RuntimeError("boom")), agent())
    assert "crashed: RuntimeError" in log[0]
    assert "RuntimeError" in note(led) and len(api.comments()) == 1


def test_unknown_turns_and_cost_say_so():
    api = Api()
    run(api, Ledger(), deps(ex.IssueResult(False, problems="no")), agent(detail=""))
    body = api.comments()[0][2]["body"]
    assert "Turns: unknown of 25." in body and "Estimated cost: not reported." in body


def test_a_failed_fix_stores_its_reason_and_comments_on_the_pr():
    pr = {"state": "open", "head": {"sha": HEAD, "ref": "agent/22-1"}}
    api, led = Api(pr=pr), Ledger()
    r = ex.IssueResult(False, problems="the model made no change", turns=4)
    log = run(api, led, deps(r), Action("fix-ci", REPO, f"7:{HEAD}", "fix attempt 1 model=sonnet turns=30"))
    assert log[0].endswith("failure: the model made no change")
    assert note(led) == "the model made no change"
    (c,) = api.comments()
    assert c[1] == f"/repos/{REPO}/issues/7/comments" and c[2]["body"].startswith("apx CI fix run failed: the model made no change")
    assert "Turns: 4 of 30." in c[2]["body"]


def test_recent_runs_with_reasons_for_the_cli():
    led = Ledger()
    run(Api(), led, deps(FAILED), agent())
    (r,) = led.recent(5)
    assert r["repo"] == REPO and r["issue"] == 22 and r["conclusion"] == "failure" and "protected-path" in r["note"]
