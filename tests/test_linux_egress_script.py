"""scripts/linux-egress-test.sh and deploy/linux/egress-selftest.sh run network-changing code, so their safety properties are pinned: the one
permission added is NET_ADMIN, nothing from the host is mounted writable, and the self-test cannot replace a live ruleset."""

import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts" / "linux-egress-test.sh"
SELFTEST = ROOT / "deploy" / "linux" / "egress-selftest.sh"


def code(path: Path) -> str:
    return "\n".join(ln for ln in path.read_text(encoding="utf-8").splitlines() if not ln.lstrip().startswith("#"))


@pytest.mark.parametrize("script", [RUNNER, SELFTEST], ids=["runner", "selftest"])
def test_valid_bash_and_executable(script):
    assert subprocess.run(["bash", "-n", str(script)], capture_output=True).returncode == 0
    assert script.stat().st_mode & 0o111


@pytest.mark.skipif(shutil.which("shellcheck") is None, reason="shellcheck is not installed")
@pytest.mark.parametrize("script", [RUNNER, SELFTEST], ids=["runner", "selftest"])
def test_shellcheck_is_clean(script):
    r = subprocess.run(["shellcheck", str(script)], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout


def test_only_committed_files_go_in_and_read_only():
    c = code(RUNNER)
    assert 'git -C "$here" archive HEAD' in c
    assert re.search(r'-v "\$tmp:/src:ro"', c)


def test_the_only_added_capability_is_net_admin():
    c = code(RUNNER)
    assert re.findall(r"--cap-add\s+(\S+)", c) == ["NET_ADMIN"]
    for danger in (
        "--privileged",
        "$HOME",
        "~/",
        "/Users/",
        "--network host",
        "--net host",
        "--pid host",
        "docker.sock",
        "--cap-add ALL",
        "SYS_ADMIN",
    ):
        assert danger not in c, danger


def test_the_container_and_export_are_removed_on_exit():
    c = code(RUNNER)
    assert "--rm" in c and re.search(r"trap 'rm -rf \"\$tmp\"' EXIT", c) and 'tmp="$(mktemp -d)"' in c


def test_the_selftest_refuses_to_replace_a_live_ruleset_and_to_run_unprivileged():
    c = code(SELFTEST)
    assert "nft list table inet apx" in c and "refusing to replace a live ruleset" in c
    assert '"$(id -u)" = 0' in c


def test_every_blocked_case_is_paired_with_a_control_so_a_missing_listener_cannot_pass_it():
    c = code(SELFTEST)
    body = c[c.index("blocked() {") :].split("}\n", 1)[0]
    assert '"$CONTROL"' in body and "proves nothing" in body


def test_the_selftest_exits_nonzero_if_anything_failed():
    assert code(SELFTEST).rstrip().endswith('[ "$fails" = 0 ]')
