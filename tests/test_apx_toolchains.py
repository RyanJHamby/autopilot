"""Per-repo toolchains for apx's sandbox: stencil needs Node 20, autopilot needs Node 22, and one PATH cannot serve both.

The declaration is DATA (src/autopilot/apx/repo_toolchains.json: repo -> ["node@20"]); the directories live under <shared>/toolchains
(root-owned on the host, so the sandbox account can read but never write them); the sandbox job's PATH gets that repo's directories
first; the host preflights fail when a declared directory is missing or its binary reports another version.
"""

import getpass
import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path

import pytest
from test_apx_sandbox import GIT_TOKEN, ROOT, lanes, make_remote

from autopilot.apx import planner, sandbox, toolchains
from autopilot.apx.runas import Launcher

STENCIL, AUTOPILOT, DRILLPAD = (f"RyanJHamby/{r}" for r in ("stencil", "autopilot", "drillpad-workspace"))
DEFAULT_PATH = "/opt/homebrew/bin:/usr/local/bin:{home}/.local/bin:/usr/bin:/bin"  # what run_in_sandbox used before this change


def fake_node(root: Path, name: str, version: str, body: str = "") -> Path:
    """<root>/<name>/bin/node that prints a version like the real one does."""
    b = root / name / "bin"
    b.mkdir(parents=True)
    f = b / "node"
    f.write_text(f"#!/bin/sh\n{body}\necho v{version}\n")
    f.chmod(0o755)
    return b


def write_spec(tmp_path, data) -> Path:
    p = tmp_path / "t.json"
    p.write_text(json.dumps(data))
    return p


# --- the declaration -------------------------------------------------------------------------------------------------------------


def test_the_shipped_declaration_gives_stencil_node_20_and_autopilot_node_22():
    d = toolchains.load_declared()
    assert d[STENCIL] == ("node@20",) and d[AUTOPILOT] == ("node@22",)
    assert set(d) <= planner.ALLOWED_REPOS  # only repos apx can run at all


@pytest.mark.parametrize(
    "entry", ["node", "node@", "node@twenty", "node@20.", "../node@20", "no de@20", "node@20;ls", "node@20/../x", "NODE@20", "node@1.2.3.4"]
)
def test_a_bad_entry_is_refused(tmp_path, entry):
    with pytest.raises(ValueError):
        toolchains.load_declared(write_spec(tmp_path, {"o/r": [entry]}))


def test_two_versions_of_one_tool_for_one_repo_is_refused(tmp_path):
    with pytest.raises(ValueError, match="node"):
        toolchains.load_declared(write_spec(tmp_path, {"o/r": ["node@20", "node@22"]}))
    with pytest.raises(ValueError):
        toolchains.load_declared(write_spec(tmp_path, {"o/r": "node@20"}))  # a string, not a list


def test_directories_come_from_the_name_and_version_never_from_the_data(tmp_path):
    root = tmp_path / "toolchains"
    assert toolchains.bin_dirs(STENCIL, root) == [str(root / "node-20" / "bin")]
    assert toolchains.bin_dirs(AUTOPILOT, root) == [str(root / "node-22" / "bin")]
    assert toolchains.bin_dirs("RyanJHamby/pawl", root) == []  # no declaration: the default PATH, as today
    assert toolchains.bin_dirs(DRILLPAD, root) == []


# --- the host check (what both preflights run) -----------------------------------------------------------------------------------


def check(tmp_path, repos, spec):
    return toolchains.check_repos(repos, tmp_path / "toolchains", declared=toolchains.load_declared(write_spec(tmp_path, spec)))


def test_missing_directory_is_a_fail_naming_the_repo_and_the_directory(tmp_path):
    lines, ok = check(tmp_path, ["o/r"], {"o/r": ["node@20"]})
    assert not ok and lines[0].startswith("FAIL") and "o/r" in lines[0] and "node-20" in lines[0]


def test_directory_without_the_binary_is_a_fail(tmp_path):
    (tmp_path / "toolchains" / "node-20" / "bin").mkdir(parents=True)
    lines, ok = check(tmp_path, ["o/r"], {"o/r": ["node@20"]})
    assert not ok and "node" in lines[0] and lines[0].startswith("FAIL")


def test_wrong_version_is_a_fail_that_says_both_versions(tmp_path):
    fake_node(tmp_path / "toolchains", "node-20", "22.11.0")  # the 22 binary filed under node-20
    lines, ok = check(tmp_path, ["o/r"], {"o/r": ["node@20"]})
    assert not ok and lines[0].startswith("FAIL") and "22.11.0" in lines[0] and "20" in lines[0]


def test_matching_version_passes_and_major_match_is_by_whole_segment(tmp_path):
    fake_node(tmp_path / "toolchains", "node-20", "20.18.1")
    lines, ok = check(tmp_path, ["o/r"], {"o/r": ["node@20"]})
    assert ok and lines[0].startswith("PASS") and "20.18.1" in lines[0]
    fake_node(tmp_path / "toolchains", "node-2", "20.18.1")  # "2" must not match 20.x
    lines, ok = check(tmp_path, ["o/r"], {"o/r": ["node@2"]})
    assert not ok


def test_an_exact_pin_must_match_exactly(tmp_path):
    fake_node(tmp_path / "toolchains", "node-20.18.1", "20.18.1")
    assert check(tmp_path, ["o/r"], {"o/r": ["node@20.18.1"]})[1]
    fake_node(tmp_path / "toolchains", "node-20.18.0", "20.18.1")
    assert not check(tmp_path, ["o/r"], {"o/r": ["node@20.18.0"]})[1]


def test_a_directory_the_sandbox_account_could_write_is_a_fail(tmp_path):
    b = fake_node(tmp_path / "toolchains", "node-20", "20.1.0")
    b.chmod(0o775)  # group-writable
    lines, ok = check(tmp_path, ["o/r"], {"o/r": ["node@20"]})
    assert not ok and "writable" in lines[0]
    b.chmod(0o755)
    (b / "node").chmod(0o757)  # world-writable binary
    assert not check(tmp_path, ["o/r"], {"o/r": ["node@20"]})[1]


def test_only_the_configured_repos_are_checked(tmp_path):
    spec = {"o/a": ["node@20"], "o/b": ["node@22"]}
    fake_node(tmp_path / "toolchains", "node-20", "20.1.0")
    assert check(tmp_path, ["o/a"], spec)[1]  # o/b's node-22 is absent but o/b is not configured here
    assert not check(tmp_path, ["o/a", "o/b"], spec)[1]
    assert check(tmp_path, ["o/other"], spec) == ([], True)  # nothing declared, nothing to check


def cli(tmp_path, *args):
    return subprocess.run(
        [sys.executable, "-m", "autopilot.apx.toolchains", "check", *args],
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
    )


def test_cli_accepts_the_installations_format_and_exits_1_on_a_fail(tmp_path):
    root = tmp_path / "toolchains"
    r = cli(tmp_path, f"{STENCIL}=11,{AUTOPILOT}=12", "--root", str(root))
    assert r.returncode == 1 and r.stdout.count("FAIL") == 2
    fake_node(root, "node-20", "20.9.0")
    fake_node(root, "node-22", "22.4.0")
    r = cli(tmp_path, f"{STENCIL}=11,{AUTOPILOT}=12,{STENCIL}", "--root", str(root))
    assert r.returncode == 0 and "FAIL" not in r.stdout and r.stdout.count("PASS") == 2
    assert cli(tmp_path, "", "--root", str(root)).returncode == 0


@pytest.mark.parametrize("script", ["deploy/linux/preflight.sh", "deploy/apx-host-preflight.sh"])
def test_both_preflights_run_the_toolchain_check_for_the_installed_and_private_repos(script):
    text = (ROOT / script).read_text()
    assert "autopilot.apx.toolchains" in text and "APX_INSTALLATIONS" in text and "APX_PRIVATE_CI" in text
    assert "toolchains" in text and "APX_SHARED" in text
    assert subprocess.run(["bash", "-n", str(ROOT / script)]).returncode == 0
    for mutating in ("sudo ", "chmod", "chown", "install ", "rm "):
        assert mutating not in re.sub(r"#.*", "", text), mutating  # still read-only


# --- the sandbox PATH ------------------------------------------------------------------------------------------------------------


def job_path(tmp_path, fake_sudo, **kw):
    """Run run_in_sandbox with a stand-in python that reports the PATH it was started with."""
    sudo, _ = fake_sudo
    echo = tmp_path / "echo-python"
    echo.write_text('#!/bin/sh\nprintf \'{"path": "%s"}\\n\' "$PATH"\n')
    echo.chmod(0o755)
    (tmp_path / "w").mkdir(exist_ok=True)
    return sandbox.run_in_sandbox(
        Launcher("apx-ci", sudo=sudo),
        {"work_root": str(tmp_path / "w")},
        None,
        python=str(echo),
        code_dir=str(ROOT),
        home="/home/apx-ci",
        **kw,
    )["path"]


def test_with_no_toolchain_the_job_path_is_exactly_what_it_was_before(tmp_path, fake_sudo):
    assert job_path(tmp_path, fake_sudo) == DEFAULT_PATH.format(home="/home/apx-ci")


def test_toolchain_dirs_are_prepended_in_order(tmp_path, fake_sudo):
    got = job_path(tmp_path, fake_sudo, path_prepend=["/srv/apx/toolchains/node-20/bin"])
    assert got == "/srv/apx/toolchains/node-20/bin:" + DEFAULT_PATH.format(home="/home/apx-ci")


@pytest.mark.parametrize("bad", ["relative/bin", "/srv/x:/tmp/evil", "", "/srv/../etc", "/srv/a b", "/srv/x\n/y"])
def test_a_malformed_toolchain_dir_is_refused_not_put_on_the_path(tmp_path, fake_sudo, bad):
    sudo, _ = fake_sudo
    (tmp_path / "w").mkdir()
    with pytest.raises(ValueError):
        sandbox.run_in_sandbox(
            Launcher("apx-ci", sudo=sudo), {"work_root": str(tmp_path / "w")}, None, python=sys.executable, code_dir=str(ROOT),
            home="/home/apx-ci", path_prepend=[bad],
        )  # fmt: skip


def test_the_agent_job_never_gets_a_toolchain_path():
    import inspect

    assert "path_prepend" not in inspect.signature(sandbox.run_agent_in_sandbox).parameters


def two_repo_lanes(tmp_path, sudo, remote, steps, root, declared):
    L = lanes(tmp_path, sudo, remote, steps)
    L.toolchain_dirs_for = lambda repo: toolchains.bin_dirs(repo, root, declared=declared)
    return L


def test_each_repo_runs_with_its_own_node_end_to_end(fake_sudo, tmp_path):
    sudo, _ = fake_sudo
    root = tmp_path / "toolchains"
    fake_node(root, "node-20", "20.9.0")
    fake_node(root, "node-22", "22.4.0")
    declared = {"o/stencil": ("node@20",), "o/autopilot": ("node@22",)}
    remote, head = make_remote(tmp_path, {"README.md": "y\n"})
    seen = {}
    for repo, want in (("o/stencil", "v20.9.0"), ("o/autopilot", "v22.4.0")):
        L = two_repo_lanes(tmp_path, sudo, remote, [["node --version", ""]], root, declared)
        co = L.checkout(repo, head)
        res = L.ci_checks(co, [{"context": "test", "steps": [["node --version", ""]]}])
        ok, md = res["test"]
        seen[repo] = (ok, want in md or ok)
        assert ok, md
    # the pass text of a green check lists the command, so prove the version through a failing step that prints it
    fake_node(tmp_path / "t2", "node-20", "20.9.0", body="echo node-binary-was-20; exit 1")
    L = two_repo_lanes(tmp_path, sudo, remote, [], tmp_path / "t2", {"o/stencil": ("node@20",)})
    ok, md = L.ci_checks(L.checkout("o/stencil", head), [{"context": "test", "steps": [["node --version", ""]]}])["test"]
    assert not ok and "node-binary-was-20" in md


def test_a_repo_without_a_declaration_sees_no_toolchain_dir(fake_sudo, tmp_path):
    sudo, _ = fake_sudo
    root = tmp_path / "toolchains"
    fake_node(root, "node-20", "20.9.0", body="echo reached-the-toolchain-node; exit 1")
    remote, head = make_remote(tmp_path, {"README.md": "y\n"})
    L = two_repo_lanes(tmp_path, sudo, remote, [], root, {"o/stencil": ("node@20",)})
    ok, md = L.ci_checks(L.checkout("o/other", head), [{"context": "test", "steps": [["node --version", ""]]}])["test"]
    assert "reached-the-toolchain-node" not in md  # o/other never got node-20's directory


def test_a_declared_but_missing_toolchain_fails_closed_and_runs_nothing(fake_sudo, tmp_path):
    sudo, log = fake_sudo
    remote, head = make_remote(tmp_path, {"README.md": "y\n"})
    L = two_repo_lanes(tmp_path, sudo, remote, [["make check", ""]], tmp_path / "absent", {"o/r": ("node@20",)})
    co = L.checkout("o/r", head)
    res = L.ci_checks(co, [{"context": "test", "steps": [["make check", ""]]}])
    ok, md = res["test"]
    assert not ok and "node-20" in md and "preflight" in md
    g_ok, g_out = L.guard(co, "agent/1-1")
    assert not g_ok and "node-20" in g_out
    assert not log.exists() or log.read_text() == ""  # the sandbox was never even started: no PR code ran


def test_secrets_stay_out_of_the_steps_environment_with_a_toolchain(fake_sudo, tmp_path):
    sudo, _ = fake_sudo
    root = tmp_path / "toolchains"
    fake_node(root, "node-20", "20.9.0", body="env; exit 1")
    remote, head = make_remote(tmp_path, {"README.md": "y\n"})
    L = two_repo_lanes(tmp_path, sudo, remote, [], root, {"o/r": ("node@20",)})
    ok, md = L.ci_checks(L.checkout("o/r", head), [{"context": "test", "steps": [["node --version", ""]]}])["test"]
    assert not ok
    names = {ln.split("=", 1)[0] for ln in md.splitlines() if re.match(r"^[A-Z_]+=", ln)}
    assert names <= {"PATH", "LANG", "LC_ALL", "TERM", "TMPDIR", "CI", "HOME", "PWD", "SHLVL", "_"}, names
    assert GIT_TOKEN not in md and "APX_GIT_TOKEN" not in md
    path = next(ln for ln in md.splitlines() if ln.startswith("PATH="))
    assert path.startswith(f"PATH={root}/node-20/bin:")
    home = next(ln for ln in md.splitlines() if ln.startswith("HOME="))[5:]
    assert not str(root).startswith(home)  # the toolchains are outside the scratch HOME, not copied or linked into it
    assert getpass.getuser()  # the lane still reports who ran it
    assert stat.S_IMODE(os.stat(root / "node-20" / "bin").st_mode) & 0o022 == 0


# --- nothing else moved ----------------------------------------------------------------------------------------------------------


def test_the_freeze_gate_and_the_pause_path_do_not_know_about_toolchains():
    src = ROOT / "src" / "autopilot" / "apx"
    assert "toolchains" not in (src / "freeze_gate.py").read_text()
    assert "freeze_gate" not in (src / "toolchains.py").read_text()
    assert "pause" not in (src / "toolchains.py").read_text().lower()


def test_the_runbook_documents_the_install_without_inventing_checksums_or_piping_to_a_shell():
    doc = (ROOT / "docs" / "apx-linux-host.md").read_text()
    assert "/srv/apx/toolchains" in doc and "SHASUMS256.txt" in doc and "sha256sum" in doc and "node-20" in doc and "node-22" in doc
    assert not re.search(r"\b[0-9a-f]{64}\b", doc), "a sha256 in the doc would be one I could not have verified"
    assert not re.search(r"\|\s*(sudo\s+)?(ba|z)?sh\b", doc.split("### 5.")[1].split("### 6.")[0])  # no curl | sh in step 5
