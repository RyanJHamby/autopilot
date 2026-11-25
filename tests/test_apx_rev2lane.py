from autopilot.apx import rev2lane

REPO = "RyanJHamby/pawl"
HANDOFF = "\n".join(f"## {s}\nx" for s in ("Done", "State", "Decision needed", "Next (agent)", "Next (you)", "Risks", "Tokens"))
EVENING = "2026-11-25T02:00:00Z"  # Tue 21:00 ET


def pr(body=HANDOFF, labels=(), sha="a" * 40, ref="agent/x", user="RyanJHamby"):
    return {
        "number": 7,
        "title": "t",
        "body": body,
        "labels": [{"name": n} for n in labels],
        "user": {"login": user},
        "head": {"sha": sha, "ref": ref, "repo": {"full_name": REPO}},
    }


def commit(date=EVENING, msg="m"):
    return {"sha": "c" * 40, "commit": {"message": msg, "author": {"date": date}, "committer": {"date": date}}}


class Fake:
    def __init__(self, pulls, files=(), commits=(commit(),), runs=()):
        self.pulls, self.files, self.commits, self.runs = pulls, list(files), list(commits), list(runs)
        self.posted = []

    def __call__(self, method, path, body=None):
        if method == "GET" and "/pulls?" in path:
            return self.pulls
        if method == "GET" and "/check-runs" in path:
            return {"check_runs": self.runs}
        if method == "GET" and path.endswith("/files?per_page=100"):
            return self.files
        if method == "GET" and path.endswith("/commits?per_page=100"):
            return self.commits
        if method == "POST" and path.endswith("/check-runs"):
            run = {
                "id": len(self.posted) + 1,
                "name": body["name"],
                "conclusion": body["conclusion"],
                "status": "completed",
                "app": {"slug": "autopilot-apx"},
            }
            self.posted.append(run)
            return run
        if method == "PATCH":
            rid = int(path.rsplit("/", 1)[1])
            self.posted[rid - 1]["external_id"] = body["external_id"]
            return {}
        raise AssertionError(f"unexpected {method} {path}")


ENV = {"APX_REV2": REPO, "APX_REV2_DENYLIST": "acmecorp"}


def results(fake):
    return {r["name"]: r["conclusion"] for r in fake.posted}


def test_clean_pr_passes_all_five():
    fake = Fake([pr()], files=[{"filename": "src/a.py", "patch": "+x = 1"}])
    log = rev2lane.run_pass(fake, "RyanJHamby", ENV)
    assert results(fake) == {c: "success" for c in rev2lane.CONTEXTS}
    assert "all pass" in log[0]


def test_gated_path_needs_label_and_label_rechecks_without_push():
    files = [{"filename": ".claude/settings.json", "patch": "+{}"}]
    fake = Fake([pr()], files=files)
    rev2lane.run_pass(fake, "RyanJHamby", ENV)
    assert results(fake)["rev2 / gated-paths"] == "failure"
    labelled = Fake([pr(labels=["human-ok"])], files=files, runs=fake.posted)
    rev2lane.run_pass(labelled, "RyanJHamby", ENV)
    assert results(labelled)["rev2 / gated-paths"] == "success"


def test_same_state_is_not_rechecked():
    fake = Fake([pr()], files=[{"filename": "src/a.py", "patch": "+x"}])
    rev2lane.run_pass(fake, "RyanJHamby", ENV)
    again = Fake([pr()], files=fake.files, runs=fake.posted)
    assert rev2lane.run_pass(again, "RyanJHamby", ENV) == [] and again.posted == []


def test_denylist_unset_fails_closed_and_never_echoes_terms():
    fake = Fake([pr(body=HANDOFF + "\nnotes on AcmeCorp")])
    rev2lane.run_pass(fake, "RyanJHamby", {"APX_REV2": REPO})
    assert results(fake)["rev2 / denylist"] == "failure"
    hit = Fake([pr(body=HANDOFF + "\nnotes on AcmeCorp")])
    rev2lane.run_pass(hit, "RyanJHamby", ENV)
    assert results(hit)["rev2 / denylist"] == "failure"


def test_work_hours_commit_fails():
    fake = Fake([pr()], commits=[commit(date="2026-11-24T15:00:00Z")])  # Tue 10:00 ET
    rev2lane.run_pass(fake, "RyanJHamby", ENV)
    assert results(fake)["rev2 / work-hours"] == "failure"


def test_missing_handoff_and_bench_claim_fail():
    fake = Fake([pr(body="no sections")], files=[{"filename": "README.md", "patch": "+p99 is 3 ms"}])
    rev2lane.run_pass(fake, "RyanJHamby", ENV)
    r = results(fake)
    assert r["rev2 / handoff"] == "failure" and r["rev2 / bench-claims"] == "failure"


def test_fork_and_untrusted_prs_are_skipped():
    fork = pr()
    fork["head"]["repo"] = {"full_name": "someone/pawl"}
    stranger = pr(ref="feature/x", user="someone")
    fake = Fake([fork, stranger])
    assert rev2lane.run_pass(fake, "RyanJHamby", ENV) == [] and fake.posted == []


def test_lane_off_without_repos():
    assert rev2lane.run_pass(Fake([pr()]), "RyanJHamby", {}) == []


def test_fingerprint_hides_terms():
    fp = rev2lane.fingerprint(pr(), [], ["acmecorp"], "w")
    assert "acmecorp" not in fp and len(fp) == 40
