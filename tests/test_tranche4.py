"""Tranche 4: the day-0 `.gitattributes` and postmortem template, and the `install-scripts-off` rule (tip 190: a package that installs
cannot run its own code on the machine that installs it)."""

import pytest
from test_pack_rules import tree

from autopilot.scaffold import core
from autopilot.scaffold import templates as t
from autopilot.standard import engine, load_checks


def run(root, rule="install-scripts-off"):
    (r,) = engine.run(engine.Repo(root), only=[rule])
    return r


# --- scaffold templates ---------------------------------------------------------------------------------------------------------


def test_gitattributes_normalises_line_endings_and_marks_binaries_and_lockfiles():
    text = t.GITATTRIBUTES
    assert "* text=auto eol=lf" in text
    for binary in ("*.png binary", "*.jpg binary", "*.pdf binary"):
        assert binary in text, binary
    for lock in ("package-lock.json", "uv.lock"):
        assert f"{lock} -diff linguist-generated" in text, lock


def test_the_postmortem_template_has_the_fields_that_make_a_postmortem_worth_writing():
    text = t.POSTMORTEM_TEMPLATE.lower()
    for field in ("what happened", "impact", "timeline", "cause", "what worked", "what we change"):
        assert field in text, field
    assert "15 minutes" in text and "blame" in text  # the time box, and that it is about the system


def test_a_new_repo_gets_both_files_and_an_existing_repo_gets_neither(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    ctx = core.Ctx(name="proj", owner="o", public=False, kind="app", ecosystems=[], empty=True, has_workflows=True)
    core.write(root, core.plan(root, ctx))
    assert (root / ".gitattributes").read_text() == t.GITATTRIBUTES
    assert (root / "docs/postmortems/TEMPLATE.md").read_text() == t.POSTMORTEM_TEMPLATE

    old = tmp_path / "old"
    old.mkdir()
    (old / "pyproject.toml").write_text("")
    octx = core.Ctx(name="old", owner="o", public=False, kind="library", ecosystems=["uv"], has_workflows=True)
    status = {a.path: a.status for a in core.plan(old, octx)}
    assert status[".gitattributes"] == "skip" and status["docs/postmortems/TEMPLATE.md"] == "skip"


def test_an_existing_gitattributes_is_never_overwritten(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    (root / ".gitattributes").write_text("*.svg binary\n")
    ctx = core.Ctx(name="proj", owner="o", public=False, kind="app", ecosystems=[], empty=True, has_workflows=True)
    core.write(root, core.plan(root, ctx))
    assert (root / ".gitattributes").read_text() == "*.svg binary\n"


# --- the install-scripts-off rule -----------------------------------------------------------------------------------------------

NODE = {"package.json": '{"dependencies": {"next": "16"}}'}


def test_a_repo_with_no_package_json_is_skipped(tmp_path):
    tree(tmp_path, {"README.md": "x\n"})
    assert run(tmp_path).result == "skip"


def test_a_node_repo_with_ignore_scripts_in_npmrc_passes(tmp_path):
    tree(tmp_path, {**NODE, ".npmrc": "ignore-scripts=true\n"})
    assert run(tmp_path).result == "pass"


@pytest.mark.parametrize("line", ["ignore-scripts=true", "ignore-scripts = true", "  ignore-scripts=TRUE  ", "ignore-scripts=true ; no hooks"])
def test_spacing_and_case_do_not_matter(tmp_path, line):
    tree(tmp_path, {**NODE, ".npmrc": f"registry=https://registry.npmjs.org/\n{line}\n"})
    assert run(tmp_path).result == "pass"


def test_a_node_repo_with_no_npmrc_fails_and_says_what_to_add(tmp_path):
    tree(tmp_path, NODE)
    r = run(tmp_path)
    assert r.result == "fail" and any("ignore-scripts=true" in f for f in r.findings), r.findings


@pytest.mark.parametrize("npmrc", ["ignore-scripts=false\n", "# ignore-scripts=true\n", "; ignore-scripts=true\n", "registry=x\n", ""])
def test_false_commented_out_or_missing_setting_does_not_count(tmp_path, npmrc):
    tree(tmp_path, {**NODE, ".npmrc": npmrc})
    assert run(tmp_path).result == "fail"


def test_a_later_false_overrides_an_earlier_true(tmp_path):
    tree(tmp_path, {**NODE, ".npmrc": "ignore-scripts=true\nignore-scripts=false\n"})
    assert run(tmp_path).result == "fail"


def test_yarn_berry_with_scripts_disabled_passes(tmp_path):
    tree(tmp_path, {**NODE, ".yarnrc.yml": "enableScripts: false\n"})
    assert run(tmp_path).result == "pass"


def test_yarn_with_scripts_enabled_fails(tmp_path):
    tree(tmp_path, {**NODE, ".yarnrc.yml": "enableScripts: true\n"})
    assert run(tmp_path).result == "fail"


def test_LIMIT_only_the_repo_root_is_read(tmp_path):
    # A package.json in a subdirectory (a monorepo workspace) is not looked at, and neither is a user-level ~/.npmrc. Recorded, not caught.
    tree(tmp_path, {"web/package.json": '{"dependencies": {"next": "16"}}'})
    assert run(tmp_path).result == "skip"


def test_the_rule_is_declared_as_a_warning_with_a_reason_and_a_fix():
    r = {c["id"]: c for c in load_checks()["checks"]}["install-scripts-off"]
    assert r["level"] == "warn" and r["label"] == "audited"
    assert "ignore-scripts" in r["fix"] and r["why"]
