"""apx resolves append-only journal conflicts itself, through the Git Data API only, and only when both sides purely appended."""

import base64
import datetime as dt
import hashlib
import json
import re
import urllib.parse

import pytest

from autopilot.apx import doctor, executor, journal, planner
from autopilot.apx.daemon import Settings, plan_repos
from autopilot.apx.github import GitHubError
from autopilot.apx.ledger import Ledger
from autopilot.apx.planner import Action

REPO = "RyanJHamby/stencil"
NOW = dt.datetime(2026, 11, 15, 12, 0, tzinfo=dt.timezone.utc)
J = "docs/journal.md"
LT, GT, EQ = "<" * 7, ">" * 7, "=" * 7
BASE = b"# Journal\n\n## 1\nfirst\n"
MAIN_ENTRY = b"\n## 2 (main)\nfrom main\n"
PR_ENTRY = b"\n## 3 (pr)\nfrom the pr\n"


class FakeGH:
    """An in-memory GitHub: blobs, flat trees, commits and refs, plus the few REST routes the planner and resolver call."""

    def __init__(self):
        self.blobs, self.trees, self.commits, self.refs = {}, {}, {}, {}
        self.prs: dict[int, dict] = {}
        self.writes: list[tuple[str, str, dict | None]] = []
        self.before_ref_update = None  # hook: lets a test move the branch between read and write

    def _id(self, kind, payload):
        return hashlib.sha1(f"{kind}:{payload!r}".encode()).hexdigest()

    def commit(self, files: dict[str, bytes], parents=(), modes=None):
        tree = {}
        for p, data in files.items():
            sha = self._id("blob", data)
            self.blobs[sha] = data
            tree[p] = ((modes or {}).get(p, "100644"), "blob", sha)
        tsha = self._id("tree", sorted(tree.items()))
        self.trees[tsha] = tree
        csha = self._id("commit", (tsha, tuple(parents), len(self.commits)))
        self.commits[csha] = {"tree": tsha, "parents": list(parents), "message": ""}
        return csha

    def files_at(self, sha):
        return {p: self.blobs[e[2]] for p, e in self.trees[self.commits[sha]["tree"]].items()}

    def ancestors(self, sha):
        seen, todo = [], [sha]
        while todo:
            s = todo.pop(0)
            if s not in seen:
                seen.append(s)
                todo += self.commits[s]["parents"]
        return seen

    def merge_base(self, a, b):
        anc = set(self.ancestors(a))
        return next(s for s in self.ancestors(b) if s in anc)

    def diff(self, a, b):
        ta, tb = self.trees[self.commits[a]["tree"]], self.trees[self.commits[b]["tree"]]
        out = []
        for p in sorted(set(ta) | set(tb)):
            if ta.get(p) != tb.get(p):
                status = "added" if p not in ta else "removed" if p not in tb else "modified"
                out.append({"filename": p, "status": status, "sha": tb[p][2] if p in tb else None})
        return out

    def pr(self, n, branch, state="dirty", repo=REPO, base="main"):
        self.prs[n] = {"branch": branch, "state": state, "repo": repo, "base": base}

    def brief(self, n):
        p = self.prs[n]
        return {
            "number": n,
            "state": "open",
            "head": {"ref": p["branch"], "sha": self.refs[p["branch"]], "repo": {"full_name": p["repo"]}},
            "base": {"ref": p["base"]},
            "user": {"login": "RyanJHamby"},
            "labels": [],
        }

    def __call__(self, method, path, body=None):
        if method != "GET":
            self.writes.append((method, path, body))
        path, _, query = path.partition("?")
        assert path.startswith(f"/repos/{REPO}/"), path
        rest = path[len(f"/repos/{REPO}/") :]
        if method == "GET":
            if rest.startswith("actions/variables/"):
                if rest.endswith("AUTOPILOT_ENABLED"):
                    return {"value": "true"}
                raise GitHubError(404, path, "nf")
            if rest == "commits/main":
                return {"commit": {"committer": {"date": "2026-11-01T00:00:00Z"}}}
            if rest == "pulls":
                return [self.brief(n) for n in self.prs] if "state=open" in query else []
            if m := re.fullmatch(r"pulls/(\d+)", rest):
                return {**self.brief(int(m.group(1))), "mergeable_state": self.prs[int(m.group(1))]["state"]}
            if m := re.fullmatch(r"pulls/(\d+)/files", rest):
                n = int(m.group(1))
                head = self.refs[self.prs[n]["branch"]]
                return self.diff(self.merge_base(self.refs["main"], head), head)
            if m := re.fullmatch(r"commits/([0-9a-f]+)/check-runs", rest):
                return {"check_runs": []}
            if rest == "issues" and "apx-control" in query:
                return []
            if m := re.fullmatch(r"git/ref/heads/(.+)", rest):
                return {"object": {"sha": self.refs[urllib.parse.unquote(m.group(1))]}}
            if m := re.fullmatch(r"compare/([0-9a-f]+)\.\.\.([0-9a-f]+)", rest):
                a, b = m.groups()
                mb = self.merge_base(a, b)
                return {"merge_base_commit": {"sha": mb}, "files": self.diff(mb, b)}
            if m := re.fullmatch(r"contents/(.+)", rest):
                p, ref = urllib.parse.unquote(m.group(1)), urllib.parse.parse_qs(query)["ref"][0]
                files = self.files_at(ref)
                if p not in files:
                    raise GitHubError(404, path, "nf")
                return {"type": "file", "encoding": "base64", "content": base64.b64encode(files[p]).decode()}
            if m := re.fullmatch(r"git/commits/([0-9a-f]+)", rest):
                c = self.commits[m.group(1)]
                return {"sha": m.group(1), "tree": {"sha": c["tree"]}, "parents": [{"sha": s} for s in c["parents"]]}
            if m := re.fullmatch(r"git/trees/([0-9a-f]+)", rest):
                t = self.trees[m.group(1)]
                return {"truncated": False, "tree": [{"path": p, "mode": e[0], "type": e[1], "sha": e[2]} for p, e in t.items()]}
        if method == "POST" and rest == "git/blobs":
            assert body["encoding"] == "base64"
            data = base64.b64decode(body["content"])
            sha = self._id("blob", data)
            self.blobs[sha] = data
            return {"sha": sha}
        if method == "POST" and rest == "git/trees":
            tree = dict(self.trees[body["base_tree"]])
            for e in body["tree"]:
                if e["sha"] is None:
                    del tree[e["path"]]
                else:
                    tree[e["path"]] = (e["mode"], e["type"], e["sha"])
            tsha = self._id("tree", sorted(tree.items()))
            self.trees[tsha] = tree
            return {"sha": tsha}
        if method == "POST" and rest == "git/commits":
            assert "author" not in body and "committer" not in body  # GitHub signs App commits only with its own identity
            csha = self._id("commit", (body["tree"], tuple(body["parents"]), len(self.commits)))
            self.commits[csha] = {"tree": body["tree"], "parents": list(body["parents"]), "message": body["message"]}
            return {"sha": csha}
        if method == "PATCH" and (m := re.fullmatch(r"git/refs/heads/(.+)", rest)):
            branch = urllib.parse.unquote(m.group(1))
            if self.before_ref_update:
                self.before_ref_update()
            if body.get("force") is not False:
                raise AssertionError("ref updates must never force")
            if self.refs[branch] not in self.ancestors(body["sha"]):
                raise GitHubError(422, path, "Update is not a fast forward")
            self.refs[branch] = body["sha"]
            return {"object": {"sha": body["sha"]}}
        raise AssertionError(f"unexpected {method} {path}")


def world(main_journal=BASE + MAIN_ENTRY, pr_journal=BASE + PR_ENTRY, branch="agent/journal-x", main_extra=None, pr_extra=None):
    """base -> main (main_journal + main_extra) and base -> PR branch (pr_journal + pr_extra), PR #7 dirty."""
    f = FakeGH()
    base_files = {J: BASE, "src/a.py": b"a = 1\n", "src/old.py": b"old\n"}
    b = f.commit(base_files)
    keep = lambda d: {k: v for k, v in d.items() if v is not None}  # noqa: E731 - None deletes a file on that side
    f.refs["main"] = f.commit(keep({**base_files, J: main_journal, **(main_extra or {})}), [b])
    f.refs[branch] = f.commit(keep({**base_files, J: pr_journal, **(pr_extra or {})}), [b])
    f.pr(7, branch)
    return f


def plan_one(f, meta=None):
    meta = {"contexts": ["guard / guard", "build"], "loop": True, "journal": True, **(meta or {})}
    return planner.plan(f, Ledger(), {REPO: meta}, now=NOW)[REPO]


def resolve_actions(r):
    return [a for a in r["actions"] if a.kind == journal.KIND]


def run(f, actions, gate=None):
    return executor.execute(f, Ledger(), None, actions, contexts={}, head_refs={}, dry_run=False, gate=gate)  # type: ignore[arg-type]


# --- the merge rule itself ---------------------------------------------------------------------------------------------------


def test_both_sides_appended_keeps_main_first_then_the_pr_entry_exactly():
    assert journal.merge_appended(BASE, BASE + MAIN_ENTRY, BASE + PR_ENTRY) == BASE + MAIN_ENTRY + PR_ENTRY


def test_main_without_a_final_newline_gets_exactly_one():
    assert journal.merge_appended(BASE, BASE + b"\n## 2\nmain", BASE + PR_ENTRY) == BASE + b"\n## 2\nmain\n" + PR_ENTRY


def test_a_blank_line_on_both_sides_of_the_seam_is_not_doubled():
    main = BASE + b"\n## 2\nmain\n\n"
    assert journal.merge_appended(BASE, main, BASE + PR_ENTRY) == main + PR_ENTRY[1:]


def test_main_edited_or_pr_edited_is_refused():
    assert journal.merge_appended(BASE, BASE.replace(b"first", b"FIRST") + MAIN_ENTRY, BASE + PR_ENTRY) is None
    assert journal.merge_appended(BASE, BASE + MAIN_ENTRY, BASE.replace(b"first", b"1st") + PR_ENTRY) is None


def test_a_base_that_ends_mid_line_is_refused_because_an_append_could_extend_its_last_line():
    assert journal.merge_appended(b"# J\nlast", b"# J\nlast\nmain\n", b"# J\nlast line extended\n") is None


def test_marker_detection_is_whole_line_only():
    assert journal.has_markers(f"a\n{LT} HEAD\n".encode()) and journal.has_markers(f"{EQ}\n".encode())
    assert journal.has_markers(f"x\n{GT} main".encode())
    assert not journal.has_markers(f"a {LT} b\n{EQ}=\n `{GT} `\n".encode())


# --- allowlist data ----------------------------------------------------------------------------------------------------------


def test_allowlist_file_ships_the_default_journals():
    assert journal.journal_files(REPO) == ("docs/journal.md", "JOURNAL.md", "journal.md")


def test_allowlist_per_repo_override(tmp_path):
    p = tmp_path / "j.json"
    p.write_text(json.dumps({"default": ["docs/journal.md"], "repos": {REPO: ["notes/log.md"]}}))
    allow = journal.load_allowlist(p)
    assert journal.journal_files(REPO, allow) == ("notes/log.md",)
    assert journal.journal_files("RyanJHamby/autopilot", allow) == ("docs/journal.md",)


@pytest.mark.parametrize(
    "data",
    [
        [],
        {"default": "docs/journal.md"},
        {"default": [""]},
        {"default": ["/etc/passwd"]},
        {"default": ["../x.md"]},
        {"default": ["docs/*.md"]},
        {"default": ["a.md"], "repos": {"not-a-repo": ["a.md"]}},
        {"default": ["a.md"], "extra": 1},
    ],
)
def test_a_malformed_allowlist_is_refused(tmp_path, data):
    p = tmp_path / "j.json"
    p.write_text(json.dumps(data))
    with pytest.raises(journal.AllowlistError):
        journal.load_allowlist(p)


# --- planner -----------------------------------------------------------------------------------------------------------------


def test_journal_only_conflict_is_planned_with_head_and_base_and_noted():
    f = world()
    r = plan_one(f)
    [a] = resolve_actions(r)
    assert a.ref == f"7:{f.refs['agent/journal-x']}:main" and J in a.detail
    assert "will resolve journal conflict on #7" in r["note"] and f.writes == []


def test_main_edited_journal_means_no_action_and_a_human_note():
    f = world(main_journal=BASE.replace(b"first", b"FIRST") + MAIN_ENTRY)
    r = plan_one(f)
    assert resolve_actions(r) == [] and "journal edited not appended" in r["note"] and "#7" in r["note"]


def test_pr_edited_journal_means_no_action():
    f = world(pr_journal=BASE.replace(b"first", b"1st") + PR_ENTRY)
    r = plan_one(f)
    assert resolve_actions(r) == [] and "journal edited not appended" in r["note"]


def test_a_non_journal_file_changed_on_both_sides_means_no_action():
    f = world(main_extra={"src/a.py": b"a = 2\n"}, pr_extra={"src/a.py": b"a = 1\nb = 2\n"})
    r = plan_one(f)
    assert resolve_actions(r) == [] and "src/a.py" in r["note"] and "left for a human" in r["note"]


def test_main_already_carrying_conflict_markers_is_refused():
    f = world(main_journal=BASE + f"\n{LT} HEAD\nx\n{EQ}\ny\n{GT} main\n".encode())
    r = plan_one(f)
    assert resolve_actions(r) == [] and "conflict markers" in r["note"]


def test_untrusted_or_fork_branches_get_nothing():
    for branch, repo in (("feature/x", REPO), ("agent/x", "someone/stencil")):
        f = world(branch=branch)
        f.prs[7]["repo"] = repo
        r = plan_one(f)
        assert resolve_actions(r) == [] and "#7" not in r["note"]


def test_a_clean_or_behind_pr_is_not_touched():
    for state in ("clean", "behind", "blocked", "unknown"):
        f = world()
        f.prs[7]["state"] = state
        assert resolve_actions(plan_one(f)) == []


def test_shadow_mode_only_logs_what_it_would_do():
    f = world()
    r = plan_one(f, {"loop": False})
    assert resolve_actions(r) == [] and "would resolve journal conflict on #7" in r["note"] and f.writes == []


def test_switched_off_means_no_compare_calls_and_no_action():
    f = world()
    calls = []
    orig = f.__call__

    def spy(method, path, body=None):
        calls.append(path)
        return orig(method, path, body)

    r = planner.plan(spy, Ledger(), {REPO: {"contexts": ["guard / guard"], "loop": True}}, now=NOW)[REPO]
    assert resolve_actions(r) == [] and not any("/compare/" in c for c in calls)


def test_a_conflicted_agent_pr_with_a_journal_only_conflict_is_not_also_re_run():
    f = world(branch="agent/5-journal")
    handled = {7}
    assert [a.kind for a in planner.plan_rebases(f, REPO, "RyanJHamby", Ledger(), NOW)] == ["rebase-agent"]  # control
    assert planner.plan_rebases(f, REPO, "RyanJHamby", Ledger(), NOW, skip=handled) == []


def test_daemon_turns_it_on_by_default_and_off_with_the_setting():
    s = Settings(owner="o", app_id="1", key_path=None, installations={REPO: 1}, oauth_file="", kit_repo="", kit_ref="")  # type: ignore[arg-type]
    assert plan_repos(s)[REPO]["journal"] is True
    s.journal_autoresolve = False
    assert plan_repos(s)[REPO]["journal"] is False


# --- executor: the write ------------------------------------------------------------------------------------------------------


def test_resolution_writes_a_two_parent_merge_commit_main_second_and_moves_the_branch():
    f = world(main_extra={"src/new.py": b"new\n", "src/old.py": None}, pr_extra={"src/pr.py": b"pr\n"})
    head, main = f.refs["agent/journal-x"], f.refs["main"]
    [a] = resolve_actions(plan_one(f))
    log = run(f, [a])
    new = f.refs["agent/journal-x"]
    assert new != head and f"journal conflict resolved on #7: {new[:7]}" in log[0]
    c = f.commits[new]
    assert c["parents"] == [head, main]
    assert c["message"].startswith("Merge main into agent/journal-x: keep both journal entries (main first)")
    assert "apx" in c["message"]
    files = f.files_at(new)
    assert files[J] == BASE + MAIN_ENTRY + PR_ENTRY
    assert (
        files["src/new.py"] == b"new\n" and "src/old.py" not in files and files["src/pr.py"] == b"pr\n"
    )  # both sides' other work kept
    assert [w[0] for w in f.writes] == ["POST", "POST", "POST", "PATCH"]  # blob, tree, commit, ref: nothing else


def test_the_merged_tree_equals_what_a_clean_three_way_merge_would_give():
    f = world(main_extra={"src/m.py": b"m\n"}, pr_extra={"src/a.py": b"a = 9\n"})
    [a] = resolve_actions(plan_one(f))
    run(f, [a])
    files = f.files_at(f.refs["agent/journal-x"])
    assert files == {J: BASE + MAIN_ENTRY + PR_ENTRY, "src/a.py": b"a = 9\n", "src/old.py": b"old\n", "src/m.py": b"m\n"}


def test_branch_moved_between_read_and_write_fails_the_update_without_crashing_and_is_retried():
    f = world()
    [a] = resolve_actions(plan_one(f))

    def move():
        f.refs["agent/journal-x"] = f.commit({J: BASE + PR_ENTRY + b"more\n"}, [f.refs["agent/journal-x"]])
        f.before_ref_update = None

    f.before_ref_update = move
    moved_to = None
    log = run(f, [a])
    moved_to = f.refs["agent/journal-x"]
    assert "branch moved" in log[0] and "next pass" in log[0]
    assert f.files_at(moved_to)[J] == BASE + PR_ENTRY + b"more\n"  # the newer push survives
    assert resolve_actions(plan_one(f))  # the next pass offers it again


def test_a_pr_that_changed_since_planning_is_skipped_without_writes():
    f = world()
    [a] = resolve_actions(plan_one(f))
    f.refs["agent/journal-x"] = f.commit({J: BASE + PR_ENTRY + b"x\n"}, [f.refs["agent/journal-x"]])
    log = run(f, [a])
    assert "changed since it was planned" in log[0] and f.writes == []


def test_the_freeze_holds_it_and_nothing_is_written():
    f = world()
    [a] = resolve_actions(plan_one(f))
    log = run(f, [a], gate=lambda kind: "freeze: work hours")
    assert log == [f"held {journal.KIND} {REPO} {a.ref[:12]}: freeze: work hours"] and f.writes == []


def test_dry_run_writes_nothing():
    f = world()
    acts = resolve_actions(plan_one(f))
    log = executor.execute(f, Ledger(), None, acts, contexts={}, head_refs={})  # type: ignore[arg-type]
    assert log[0].startswith("DRY-RUN resolve-journal") and f.writes == []


def test_a_resolution_never_writes_conflict_markers(monkeypatch):
    f = world()
    [a] = resolve_actions(plan_one(f))
    monkeypatch.setattr(journal, "merge_appended", lambda b, m, h: m + f"{LT} HEAD\n".encode() + h)
    log = run(f, [a])
    assert "conflict markers" in log[0] and f.writes == []


def test_the_app_needs_no_new_permission():
    for perm, level in journal.NEEDS.items():
        assert doctor.RANK[doctor.REQUIRED[perm]] >= doctor.RANK[level], perm


def test_an_api_error_while_resolving_is_logged_not_raised():
    f = world()
    [a] = resolve_actions(plan_one(f))

    def broken(method, path, body=None):
        if method == "POST":
            raise GitHubError(500, path, "x")
        return f(method, path, body)

    log = run(broken, [a])
    assert "failed: GitHubError" in log[0]


def test_action_kind_is_a_branch_write_so_the_freeze_gate_holds_it():
    from autopilot.apx import freeze_gate

    assert journal.KIND not in freeze_gate.CHECK_KINDS
    assert Action(journal.KIND, REPO, "7:x:main").kind == "resolve-journal"


def test_a_broken_allowlist_turns_the_feature_off_but_never_the_checks(monkeypatch, tmp_path):
    bad = tmp_path / "j.json"
    bad.write_text("{not json")
    monkeypatch.setattr(journal, "ALLOWLIST_FILE", bad)
    monkeypatch.setattr(journal.load_allowlist, "__defaults__", (bad,))
    f = world()
    r = plan_one(f)
    assert resolve_actions(r) == [] and "allowlist unreadable" in r["note"]
    assert any(a.kind == "check-pr" for a in r["actions"])  # the repo's checks are still planned
