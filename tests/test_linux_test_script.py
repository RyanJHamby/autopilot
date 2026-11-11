"""scripts/linux-test.sh runs code on a real Linux kernel in a container, so its safety properties are pinned: a later edit that mounts the
home folder or goes privileged would turn a verification tool into a risk."""

import re
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "linux-test.sh"
TEXT = SCRIPT.read_text(encoding="utf-8")
CODE = "\n".join(line for line in TEXT.splitlines() if not line.lstrip().startswith("#"))


def test_it_is_valid_bash_and_executable():
    assert subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True).returncode == 0
    assert SCRIPT.stat().st_mode & 0o111


@pytest.mark.skipif(shutil.which("shellcheck") is None, reason="shellcheck is not installed")
def test_shellcheck_is_clean():
    r = subprocess.run(["shellcheck", str(SCRIPT)], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout


def test_only_committed_files_go_in_so_untracked_files_never_reach_the_container():
    assert "git -C \"$here\" archive HEAD" in CODE


def test_the_export_is_mounted_read_only():
    assert re.search(r'-v "\$tmp:/src:ro"', CODE)


@pytest.mark.parametrize("danger", ["--privileged", "$HOME", "~/", "/Users/", "--network host", "--pid host", "docker.sock", "--cap-add"])
def test_nothing_dangerous_is_requested(danger):
    assert danger not in CODE, danger


def test_the_container_and_the_export_are_removed_on_exit():
    assert "--rm" in CODE and re.search(r"trap 'rm -rf \"\$tmp\"' EXIT", CODE)


def test_the_export_directory_comes_from_mktemp_not_a_fixed_path():
    assert 'tmp="$(mktemp -d)"' in CODE
