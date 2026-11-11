"""An item can ask for a file mode, so a git hook is written executable. Git ignores a hook that is not."""

import os
import stat

from autopilot.scaffold import core

CTX = core.Ctx(name="demo", owner="o", public=False)


def item(path="hooks/run", mode=None, content="#!/bin/sh\n"):
    return core.Item(path, None, lambda c: content, lambda c: None, mode=mode)


def executable(p):
    return bool(os.stat(p).st_mode & stat.S_IXUSR)


def test_plan_carries_the_requested_mode_onto_the_action(tmp_path):
    (a,) = core.plan(tmp_path, CTX, items=[item(mode=0o755)])
    assert a.mode == 0o755


def test_write_makes_a_requested_executable_executable(tmp_path):
    actions = core.plan(tmp_path, CTX, items=[item(mode=0o755)])
    assert core.write(tmp_path, actions) == ["hooks/run"]
    assert executable(tmp_path / "hooks/run")


def test_an_item_with_no_mode_is_not_made_executable(tmp_path):
    core.write(tmp_path, core.plan(tmp_path, CTX, items=[item()]))
    assert not executable(tmp_path / "hooks/run")


def test_an_existing_file_is_never_chmodded(tmp_path):
    (tmp_path / "hooks").mkdir()
    (tmp_path / "hooks/run").write_text("mine\n")
    actions = core.plan(tmp_path, CTX, items=[item(mode=0o755)])
    assert actions[0].status == "exists"
    core.write(tmp_path, actions)
    assert not executable(tmp_path / "hooks/run")
    assert (tmp_path / "hooks/run").read_text() == "mine\n"


def test_a_skeleton_path_keeps_its_mode_when_the_placeholder_is_filled(tmp_path):
    it = core.Item("src/@pkg@/run", None, lambda c: "x\n", lambda c: None, mode=0o755)
    assert core._resolve(it, core.Ctx(name="demo", owner="o", public=False, kind="library")).mode == 0o755
