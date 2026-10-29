import copy

from autopilot.apx import pin

REPO = "RyanJHamby/drillpad-workspace"
RULESET = {
    "id": 25100209,
    "name": "autopilot-main",
    "target": "branch",
    "enforcement": "active",
    "created_at": "2026-10-16T00:00:00Z",
    "source": "x",
    "bypass_actors": [{"actor_id": 5, "actor_type": "RepositoryRole", "bypass_mode": "pull_request"}],
    "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
    "rules": [
        {"type": "deletion"},
        {"type": "required_signatures"},
        {"type": "pull_request", "parameters": {"required_approving_review_count": 0, "require_code_owner_review": True}},
        {
            "type": "required_status_checks",
            "parameters": {
                "strict_required_status_checks_policy": False,
                "required_status_checks": [{"context": "guard / guard"}, {"context": "test"}, {"context": "lint-other"}],
            },
        },
    ],
}


class FakeGh:
    def __init__(self, ruleset=RULESET, apx_posted=("guard / guard", "test"), rulesets=None):
        self.ruleset = ruleset
        self.apx_posted = set(apx_posted)
        self.rulesets = rulesets if rulesets is not None else [{"id": ruleset["id"], "name": "autopilot-main"}]
        self.puts = []

    def __call__(self, path, method="GET", body=None):
        if method == "PUT":
            self.puts.append((path, body))
            return {}
        if path.endswith("/rulesets"):
            return self.rulesets
        if "/rulesets/" in path:
            return copy.deepcopy(self.ruleset)
        if "/pulls?" in path:
            return [{"head": {"sha": "s1"}}, {"head": {"sha": "s2"}}]
        if "/check-runs" in path:
            runs = [{"name": n, "conclusion": "success", "app": {"slug": "autopilot-apx"}} for n in self.apx_posted]
            runs.append({"name": "lint-other", "conclusion": "success", "app": {"slug": "github-actions"}})  # not apx: no credit
            runs.append({"name": "guard / guard", "conclusion": "failure", "app": {"slug": "autopilot-apx"}})
            return {"check_runs": runs}
        raise AssertionError(path)


def checks_of(body):
    r = next(r for r in body["rules"] if r["type"] == "required_status_checks")
    return {c["context"]: c.get("integration_id") for c in r["parameters"]["required_status_checks"]}


def test_pin_sets_integration_id_only_on_the_named_checks_and_keeps_everything_else():
    body, changes = pin.pin_rules(RULESET, 5512558, {"guard / guard", "test"})
    assert checks_of(body) == {"guard / guard": 5512558, "test": 5512558, "lint-other": None}
    assert len(changes) == 2 and all("any -> 5512558" in c for c in changes)
    assert body["bypass_actors"] == RULESET["bypass_actors"] and body["conditions"] == RULESET["conditions"]
    assert [r["type"] for r in body["rules"]] == ["deletion", "required_signatures", "pull_request", "required_status_checks"]
    assert body["rules"][2] == RULESET["rules"][2]  # code-owner review rule untouched
    assert set(body) <= set(pin.PUT_FIELDS) and "id" not in body and "created_at" not in body
    assert checks_of(RULESET) == {"guard / guard": None, "test": None, "lint-other": None}  # the input was not mutated


def test_pinning_twice_changes_nothing_and_undo_restores_any_app():
    body, _ = pin.pin_rules(RULESET, 5512558, {"guard / guard", "test"})
    again, changes = pin.pin_rules({**RULESET, **body}, 5512558, {"guard / guard", "test"})
    assert changes == [] and checks_of(again) == checks_of(body)
    undone, ch = pin.pin_rules({**RULESET, **body}, 5512558, {"guard / guard", "test"}, undo=True)
    assert len(ch) == 2 and checks_of(undone) == {"guard / guard": None, "test": None, "lint-other": None}


def test_evidence_counts_only_successful_checks_posted_by_the_apx_app():
    gh = FakeGh(apx_posted=("guard / guard",))
    assert pin.missing_evidence(gh, REPO, {"guard / guard", "test"}) == ["test"]  # apx never posted `test`
    assert pin.missing_evidence(gh, REPO, {"lint-other"}) == ["lint-other"]  # a github-actions success earns no credit
    assert pin.missing_evidence(FakeGh(), REPO, {"guard / guard", "test"}) == []


def test_dry_run_writes_nothing_and_apply_writes_exactly_once_with_the_pinned_body(capsys):
    gh = FakeGh()
    assert pin.run(REPO, apply=False, undo=False, force=False, gh=gh) == 0 and gh.puts == []
    assert "WOULD change guard / guard" in capsys.readouterr().out
    assert pin.run(REPO, apply=True, undo=False, force=False, gh=gh) == 0
    assert len(gh.puts) == 1
    path, body = gh.puts[0]
    assert path == f"repos/{REPO}/rulesets/25100209" and checks_of(body)["test"] == 5512558
    assert checks_of(body)["lint-other"] is None  # a required check apx does not post keeps whatever app posts it


def test_it_refuses_to_pin_when_apx_has_not_been_posting_those_checks(capsys):
    gh = FakeGh(apx_posted=("guard / guard",))  # never posted `test`: pinning would stop every merge
    assert pin.run(REPO, apply=True, undo=False, force=False, gh=gh) == 3
    assert gh.puts == [] and "REFUSING" in capsys.readouterr().err
    assert pin.run(REPO, apply=True, undo=False, force=True, gh=gh) == 0 and len(gh.puts) == 1  # explicit override only


def test_undo_never_needs_evidence_and_scope_and_ruleset_shape_are_enforced(capsys):
    pinned, _ = pin.pin_rules(RULESET, 5512558, {"guard / guard", "test"})
    gh = FakeGh(ruleset={**RULESET, **pinned}, apx_posted=())
    assert pin.run(REPO, apply=True, undo=True, force=False, gh=gh) == 0 and len(gh.puts) == 1
    assert pin.run("RyanJHamby/resume", apply=True, undo=False, force=False, gh=FakeGh()) == 2
    assert pin.run(REPO, apply=True, undo=False, force=False, gh=FakeGh(rulesets=[])) == 2
    two = [{"id": 1, "name": "autopilot-main"}, {"id": 2, "name": "autopilot-main"}]
    assert pin.run(REPO, apply=True, undo=False, force=False, gh=FakeGh(rulesets=two)) == 2
    assert pin.run(REPO, apply=False, undo=False, force=False, gh=FakeGh(ruleset={**RULESET, **pinned})) == 0
    assert "nothing to change" in capsys.readouterr().out
