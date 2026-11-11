"""The day-0 layer a brand-new repo gets: a hook that blocks a bad commit, a Makefile that runs the same checks as CI, and the
conventions. Behaviour is tested with real `make` and real git, because a Makefile that only looks right proves nothing."""

import os
import shutil
import stat
import subprocess

import pytest
import yaml

from autopilot.scaffold import core
from autopilot.scaffold import templates as t

DAY_ZERO = {
    ".githooks/pre-commit",
    ".editorconfig",
    ".gitattributes",
    "docs/decisions/README.md",
    "docs/runbooks/README.md",
    "docs/postmortems/TEMPLATE.md",
}
NEEDS = pytest.mark.skipif(shutil.which("make") is None, reason="make is not installed")
GITLEAKS = pytest.mark.skipif(shutil.which("gitleaks") is None, reason="gitleaks is not installed")
# A made-up, high-entropy value in a keyed assignment: what gitleaks's generic rule looks for. It is not a credential for anything.
FAKE_SECRET = 'api_key = "x7Kq9Zp2Lm4Rv8Tn3Wb6Yc1Hd5Fg0Js"\n'
GIT_ID = ["-c", "commit.gpgsign=false", "-c", "user.email=t@t", "-c", "user.name=t"]


def new_repo(tmp_path, kind="app", ecosystems=None, name="proj"):
    root = tmp_path / name
    root.mkdir()
    ctx = core.Ctx(name=name, owner="o", public=False, kind=kind, ecosystems=ecosystems or [], empty=True, has_workflows=True)
    core.write(root, core.plan(root, ctx))
    return root


def sh(root, *cmd, env=None, check=True):
    e = {**os.environ, **(env or {})}
    for var in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"):
        e.pop(var, None)
    return subprocess.run(list(cmd), cwd=root, capture_output=True, text=True, env=e, check=check)


def git_init(root):
    sh(root, "git", "init", "-q", "-b", "main")


def executable(p):
    return bool(os.stat(p).st_mode & stat.S_IXUSR)


# --- what a new repo gets, and what an existing one does not ------------------------------------------------------------


@pytest.mark.parametrize("kind,eco", [("app", []), ("notes", []), ("library", ["uv"]), ("cli", ["uv"])])
def test_every_kind_of_new_repo_gets_the_day_zero_files(tmp_path, kind, eco):
    root = new_repo(tmp_path, kind, eco)
    for rel in DAY_ZERO:
        assert (root / rel).is_file(), rel
    assert executable(root / ".githooks/pre-commit")
    mk = (root / "Makefile").read_text()
    for target in ("setup:", "quick:", "check:", "audit:", "standard:", "standard-report:"):
        assert target in mk, target


def test_an_existing_repo_gets_none_of_them(tmp_path):
    root = tmp_path / "old"
    root.mkdir()
    (root / "pyproject.toml").write_text("")
    ctx = core.Ctx(name="old", owner="o", public=False, kind="library", ecosystems=["uv"], has_workflows=True)
    skipped = {a.path: a.status for a in core.plan(root, ctx) if a.path in DAY_ZERO}
    assert set(skipped) == DAY_ZERO and set(skipped.values()) == {"skip"}


def test_a_uv_repo_gets_lint_tests_and_a_dependency_audit_in_the_right_targets(tmp_path):
    mk = (new_repo(tmp_path, "library", ["uv"]) / "Makefile").read_text()
    quick = mk.split("\nquick:")[1].split("\n\n")[0]
    check = mk.split("\ncheck:")[1].split("\n\n")[0]
    audit = mk.split("\naudit:")[1].split("\n\n")[0]
    assert "uv run ruff check ." in quick and "pytest" not in quick  # the hook stays fast: no test suite
    assert "uv run pytest -q" in check
    assert "uv audit" in audit


# --- real make --------------------------------------------------------------------------------------------------------


@NEEDS
def test_setup_links_the_hook_into_git_and_refuses_to_clobber_a_real_file(tmp_path):
    root = new_repo(tmp_path)
    git_init(root)
    sh(root, "make", "setup")
    link = root / ".git/hooks/pre-commit"
    assert link.is_symlink() and link.resolve() == (root / ".githooks/pre-commit").resolve()
    sh(root, "make", "setup")  # idempotent
    link.unlink()
    link.write_text("#!/bin/sh\necho mine\n")
    r = sh(root, "make", "setup", check=False)
    assert r.returncode != 0 and "left alone" in r.stdout
    assert link.read_text().startswith("#!/bin/sh\necho mine")


@NEEDS
def test_check_passes_on_a_clean_new_repo_and_fails_on_a_tracked_env_file(tmp_path):
    root = new_repo(tmp_path)
    git_init(root)
    sh(root, "git", "add", ".")
    assert sh(root, "make", "check", check=False).returncode == 0
    (root / ".env").write_text("TOKEN=x\n")
    sh(root, "git", "add", "-f", ".env")
    r = sh(root, "make", "check", check=False)
    assert r.returncode != 0 and ".env" in r.stdout


def fake_tool(directory, name, code):
    directory.mkdir(exist_ok=True)
    p = directory / name
    p.write_text(f"#!/bin/sh\nexit {code}\n")
    p.chmod(0o755)
    return str(directory)


def path_without_linters(tmp_path):
    """A PATH holding make, git and the shell tools but no linter, so a missing tool is really missing."""
    keep = tmp_path / "keep"
    keep.mkdir(exist_ok=True)
    for exe in ("make", "git", "sh", "grep", "ls", "bash", "env", "cat"):
        found = shutil.which(exe)
        if found and not (keep / exe).exists():
            (keep / exe).symlink_to(found)
    return str(keep)


@NEEDS
def test_a_missing_workflow_linter_warns_but_does_not_fail(tmp_path):
    root = new_repo(tmp_path)
    git_init(root)
    r = sh(root, "make", "workflow-lint", env={"PATH": path_without_linters(tmp_path)})
    assert "actionlint is not installed" in r.stdout and "zizmor is not installed" in r.stdout


@NEEDS
def test_a_workflow_linter_that_runs_and_fails_fails_the_check(tmp_path):
    # `a && b || warn` would swallow this: the tool ran, found a problem, and the build must go red.
    root = new_repo(tmp_path)
    git_init(root)
    base = path_without_linters(tmp_path)
    bad = fake_tool(tmp_path / "bad", "actionlint", 1)
    assert sh(root, "make", "workflow-lint", env={"PATH": f"{bad}:{base}"}, check=False).returncode != 0
    good = fake_tool(tmp_path / "good", "actionlint", 0)
    assert sh(root, "make", "workflow-lint", env={"PATH": f"{good}:{base}"}, check=False).returncode == 0


@NEEDS
@GITLEAKS
def test_the_hook_blocks_a_commit_that_stages_a_secret_and_allows_a_clean_one(tmp_path):
    root = new_repo(tmp_path)
    git_init(root)
    sh(root, "make", "setup")
    (root / "config.txt").write_text(FAKE_SECRET)
    sh(root, "git", "add", "config.txt")
    blocked = sh(root, "git", *GIT_ID, "commit", "-qm", "oops", check=False)
    assert blocked.returncode != 0, "a staged secret was committed"
    sh(root, "git", "rm", "-q", "--cached", "config.txt")
    (root / "config.txt").unlink()
    (root / "notes.txt").write_text("hello\n")
    sh(root, "git", "add", "notes.txt")
    ok = sh(root, "git", *GIT_ID, "commit", "-qm", "fine", check=False)
    assert ok.returncode == 0, ok.stdout + ok.stderr


# --- dependabot and the templates -------------------------------------------------------------------------------------


def test_every_dependabot_entry_has_a_cooldown_and_routine_bumps_are_grouped():
    doc = yaml.safe_load(t.dependabot(["uv", "npm"], has_workflows=True))
    assert len(doc["updates"]) == 3
    for u in doc["updates"]:
        assert u["cooldown"] == {"default-days": 7}, u["package-ecosystem"]
        assert ("groups" in u) == (u["package-ecosystem"] != "github-actions"), u["package-ecosystem"]
    npm = next(u for u in doc["updates"] if u["package-ecosystem"] == "npm")
    assert npm["groups"]["minor-and-patch"] == {"patterns": ["*"], "update-types": ["minor", "patch"]}


def test_the_generated_hook_runs_make_quick_and_nothing_slower():
    assert "make --quiet quick" in t.HOOK_PRE_COMMIT and "pytest" not in t.HOOK_PRE_COMMIT


def test_the_pr_template_asks_for_risk_and_rollback_and_for_untouched_tests():
    assert "Rollback" in t.PULL_REQUEST and "loosened" in t.PULL_REQUEST


# --- the tripwire: a repo that gains a capability is told by `make quick` and stopped by `make check` ----------------------------

AP = pytest.mark.skipif(shutil.which("ap") is None, reason="ap is not on PATH")
STRIPE = {"package.json": '{"dependencies": {"stripe": "^23"}}'}
COMPLETE_PAYMENTS = {
    **STRIPE,
    "src/app/api/stripe/webhook/route.ts": "const e = stripe.webhooks.constructEvent(raw, sig, secret);\n",
    # A decision record satisfies event-dedupe without a SQL migration, which would also make this a database repo that owes the DB pack.
    "docs/decisions/0002-webhook-idempotency.md": "# Webhook idempotency\n\n"
    + "\n".join(f"Line {i}: replaying an event is harmless because it only sets a flag." for i in range(8))
    + "\n",
    "docs/threat-model.md": "# Threat model\n\n"
    + "\n".join(f"Line {i} of real content about what could go wrong." for i in range(8))
    + "\n",
    "public/terms.html": "<h1>Terms and refund policy</h1>\n",
}
STRIPE_OWNER = (
    "/src/app/api/stripe/ @o\n"  # appended to the scaffolded CODEOWNERS, as a person would; replacing it drops the other cover
)


def add(root, files):
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)


@NEEDS
@AP
def test_a_fresh_repo_passes_make_check_including_the_standard(tmp_path):
    root = new_repo(tmp_path)
    git_init(root)
    sh(root, "git", "add", ".")
    r = sh(root, "make", "check", check=False)
    assert r.returncode == 0, r.stdout + r.stderr


@NEEDS
@AP
def test_adding_payments_makes_check_fail_naming_the_pack_and_quick_only_reports(tmp_path):
    root = new_repo(tmp_path)
    git_init(root)
    add(root, STRIPE)
    sh(root, "git", "add", ".")
    check = sh(root, "make", "check", check=False)
    assert check.returncode != 0 and "payments-pack" in check.stdout
    quick = sh(root, "make", "quick", check=False)
    assert quick.returncode == 0, "the hook must report, not block, so a work-in-progress commit is allowed"
    assert "payments-pack" in quick.stdout


@NEEDS
@AP
def test_a_complete_payments_pack_lets_check_pass_again(tmp_path):
    root = new_repo(tmp_path)
    git_init(root)
    add(root, COMPLETE_PAYMENTS)
    with open(root / ".github/CODEOWNERS", "a") as f:
        f.write(STRIPE_OWNER)
    sh(root, "git", "add", ".")
    r = sh(root, "make", "check", check=False)
    assert r.returncode == 0, r.stdout + r.stderr


@NEEDS
@AP
def test_quick_stays_quiet_when_nothing_is_wrong(tmp_path):
    root = new_repo(tmp_path)
    git_init(root)
    sh(root, "git", "add", ".")
    assert "standard:" not in sh(root, "make", "quick").stdout


@NEEDS
def test_a_missing_ap_warns_instead_of_failing(tmp_path):
    root = new_repo(tmp_path)
    git_init(root)
    r = sh(root, "make", "standard", env={"PATH": path_without_linters(tmp_path)})
    assert "ap is not on PATH" in r.stdout
