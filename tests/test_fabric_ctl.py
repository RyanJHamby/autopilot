from autopilot.fabric import ctl


def job(repo, jid, *labels):
    return ctl.Job(repo, jid * 10, jid, ("self-hosted", *labels))


A, D, S = "RyanJHamby/autopilot", "RyanJHamby/drillpad-workspace", "RyanJHamby/stencil"


def test_lane_of_accepts_exactly_one_known_lane():
    assert ctl.lane_of(["self-hosted", "lane-ci"]) == "ci"
    assert ctl.lane_of(["self-hosted"]) is None
    assert ctl.lane_of(["lane-ci", "lane-exec"]) is None  # a job cannot ask for two trust levels
    assert ctl.lane_of(["lane-root"]) is None


def test_out_of_scope_repos_are_never_served():
    assert ctl.plan([job("RyanJHamby/other", 1, "lane-ci")], []) == []


def test_jobs_without_self_hosted_label_are_ignored():
    j = ctl.Job(A, 10, 1, ("ubuntu-latest", "lane-ci"))
    assert ctl.plan([j], []) == []


def test_lane_cap_is_enforced_including_running_sandboxes():
    running = [ctl.Spawn(A, 99, "exec", "ap-exec-99", ())]
    assert ctl.plan([job(S, 1, "lane-exec")], running) == []  # exec cap is 1
    assert [s.lane for s in ctl.plan([job(S, 1, "lane-ci")], running)] == ["ci"]


def test_repo_cap_and_fair_share():
    queued = [job(S, i, "lane-ci") for i in (1, 2, 3)] + [job(D, 4, "lane-ci")]
    got = ctl.plan(queued, [], lane_caps={"ci": 3}, repo_cap=2)
    assert {s.repo for s in got} == {S, D}  # stencil cannot take every slot
    assert len(got) == 3


def test_already_running_job_is_not_started_twice():
    running = [ctl.Spawn(S, 1, "ci", "ap-ci-1", ())]
    assert ctl.plan([job(S, 1, "lane-ci")], running) == []


def test_spawned_runner_gets_only_its_own_lane_labels_and_is_named_per_job():
    (s,) = ctl.plan([job(S, 7, "lane-trusted")], [])
    assert s.labels == ("self-hosted", "lane-trusted") and s.runner_name == "ap-trusted-7"
    body = ctl.jit_body(s)
    assert body["labels"] == ["self-hosted", "lane-trusted"] and body["name"] == "ap-trusted-7"


def test_queued_jobs_reads_rest_only():
    def gh(path):
        if "actions/runs?status=queued" in path:
            return {"workflow_runs": [{"id": 5}]} if path.startswith("repos/RyanJHamby/stencil") else {"workflow_runs": []}
        if path.endswith("/actions/runs/5/jobs?per_page=50"):
            return {"jobs": [{"id": 9, "status": "queued", "labels": ["self-hosted", "lane-ci"]},
                             {"id": 8, "status": "in_progress", "labels": ["self-hosted", "lane-ci"]},
                             {"id": 7, "status": "queued", "labels": ["ubuntu-latest"]}]}
        raise AssertionError(path)

    got = ctl.queued_jobs(gh)
    assert [(j.repo, j.job_id) for j in got] == [(S, 9)]
