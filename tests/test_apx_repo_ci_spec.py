"""The per-repo CI spec for the private repos (admin, control, pawl, agent-kit) and the host checks that go with it: the spec is DATA
(src/autopilot/apx/repo_ci.json), validated by repo_ci.py, and both preflights fail when a configured repo's tools are missing or too old.
Wiring the spec into the daemon is a separate change (test_apx_repo_ci.py)."""

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from autopilot.apx import cilane, repo_ci

ADMIN, CONTROL, PAWL, KIT = (f"RyanJHamby/{r}" for r in ("admin", "control", "pawl", "agent-kit"))
ROOT = Path(__file__).resolve().parent.parent

def specs():
    return repo_ci.load_specs()


def test_each_private_repo_has_its_required_context_names_and_commands():
    s = specs()
    assert set(s) == {ADMIN, CONTROL, PAWL, KIT}
    assert [c.context for c in s[ADMIN].checks] == ["ci"]  # classic protection on admin requires exactly `ci`
    assert [c.context for c in s[CONTROL].checks] == ["check", "plan-coverage"]
    assert [c.context for c in s[PAWL].checks] == ["test"]  # the ruleset requires `test` only, not the matrix legs
    assert [c.context for c in s[ADMIN].checks][0] == "ci"
    admin_cmds = [cmd for cmd, _ in s[ADMIN].checks[0].steps]
    assert admin_cmds == ["gitleaks detect --source . --no-banner --redact", "scripts/ci-test.sh"]
    assert [cmd for cmd, _ in s[PAWL].checks[0].steps] == ["make check"]
    assert "pawl check --base origin/main" in [cmd for cmd, _ in s[CONTROL].checks[0].steps]
    assert [cmd for cmd, _ in s[KIT].checks[0].steps] == ["make check"]
    assert {"gitleaks"} <= set(s[ADMIN].tools) and "pawl" in s[CONTROL].tools and "shellcheck" in s[KIT].tools


def test_every_step_passes_the_same_safety_filter_as_repo_yaml_ci_steps():
    for spec in specs().values():
        for chk in spec.checks:
            cilane.parse_ci_steps({"ci": [{"run": c, "dir": d} for c, d in chk.steps]})  # raises on anything unsafe


def test_a_bad_spec_is_refused(tmp_path):
    p = tmp_path / "s.json"
    p.write_text(json.dumps({"o/r": {"tools": [], "checks": [{"context": "ci", "steps": ["rm -rf / ; ls"]}]}}))
    with pytest.raises(ValueError):
        repo_ci.load_specs(p)
    p.write_text(json.dumps({"o/r": {"tools": ["a b"], "checks": [{"context": "ci", "steps": ["make check"]}]}}))
    with pytest.raises(ValueError):
        repo_ci.load_specs(p)
    p.write_text(json.dumps({"o/r": {"tools": [], "checks": []}}))
    with pytest.raises(ValueError):  # a repo that checks nothing must not look green
        repo_ci.load_specs(p)


def test_unconfigured_repo_gets_nothing():
    assert repo_ci.spec_for("RyanJHamby/stencil") is None
    assert repo_ci.spec_for("RyanJHamby/autopilot") is None


def fake_bin(dirpath, names):
    for n in names:
        f = dirpath / n
        f.write_text("#!/bin/sh\n")
        f.chmod(f.stat().st_mode | stat.S_IXUSR)


def tools_cli(path, repos, *extra):
    return subprocess.run(
        [sys.executable, "-m", "autopilot.apx.repo_ci", "check-tools", repos, "--path", str(path), *extra],
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
    )


def test_missing_tool_is_a_preflight_fail(tmp_path):
    fake_bin(tmp_path, ["git", "python3", "bash", "make"])  # no gitleaks
    r = tools_cli(tmp_path, ADMIN)
    assert r.returncode == 1
    assert any(line.startswith("FAIL") and "gitleaks" in line and "admin" in line for line in r.stdout.splitlines())


def test_all_tools_present_passes_and_nothing_configured_passes(tmp_path):
    needed = {repo_ci.parse_tool(t)[0] for r in (ADMIN, PAWL) for t in specs()[r].tools}
    fake_bin(tmp_path, sorted(needed - {"python3"}))
    fake_tool(tmp_path, "python3", "Python 3.12.3")
    r = tools_cli(tmp_path, f"{ADMIN},{PAWL}")
    assert r.returncode == 0 and "FAIL" not in r.stdout and "PASS" in r.stdout
    empty = tools_cli(tmp_path / "nothing", "")
    assert empty.returncode == 0 and "FAIL" not in empty.stdout


def test_unknown_repo_in_the_list_is_a_fail(tmp_path):
    r = tools_cli(tmp_path, "RyanJHamby/stencil")
    assert r.returncode == 1 and "FAIL" in r.stdout


@pytest.mark.parametrize("script", ["deploy/linux/preflight.sh", "deploy/apx-host-preflight.sh"])
def test_both_preflights_call_the_tool_check_for_configured_repos(script):
    text = (ROOT / script).read_text()
    assert "APX_PRIVATE_CI" in text and "autopilot.apx.repo_ci" in text and "check-tools" in text
    assert subprocess.run(["bash", "-n", str(ROOT / script)]).returncode == 0


# --- follow-ups from the VPS cutover checklist ---------------------------------------------------------------------------------


def fake_tool(dirpath, name, version_line):
    f = dirpath / name
    f.write_text(f"#!/bin/sh\necho '{version_line}'\n")
    f.chmod(f.stat().st_mode | stat.S_IXUSR)


def test_a_tool_can_require_a_minimum_version(tmp_path):
    assert repo_ci.parse_tool("python3>=3.11") == ("python3", "3.11")
    assert repo_ci.parse_tool("gitleaks") == ("gitleaks", None)
    with pytest.raises(ValueError):
        repo_ci.parse_tool("node>=twenty")
    p = tmp_path / "s.json"
    p.write_text(json.dumps({"o/r": {"tools": ["node>=x"], "checks": [{"context": "ci", "steps": ["make check"]}]}}))
    with pytest.raises(ValueError):
        repo_ci.load_specs(p)
    lines, ok = repo_ci.check_tools_spec({"tools": ["python3>=3.11"]}, "o/r", str(tmp_path))
    assert not ok and "python3" in lines[0]  # missing
    fake_tool(tmp_path, "python3", "Python 3.9.18")
    lines, ok = repo_ci.check_tools_spec({"tools": ["python3>=3.11"]}, "o/r", str(tmp_path))
    assert not ok and lines[0].startswith("FAIL") and "3.9.18" in lines[0] and "3.11" in lines[0]
    fake_tool(tmp_path, "python3", "Python 3.12.1")
    lines, ok = repo_ci.check_tools_spec({"tools": ["python3>=3.11"]}, "o/r", str(tmp_path))
    assert ok and lines[0].startswith("PASS")
    fake_tool(tmp_path, "python3", "Python 3.100.0")  # numeric, not string, comparison
    assert repo_ci.check_tools_spec({"tools": ["python3>=3.11"]}, "o/r", str(tmp_path))[1]


def test_version_checked_through_the_cli_and_python_needs_3_11_for_control_and_pawl(tmp_path):
    for r in (CONTROL, PAWL):
        assert "python3>=3.11" in specs()[r].tools
    needed = {repo_ci.parse_tool(t)[0] for t in specs()[PAWL].tools}
    fake_bin(tmp_path, sorted(needed - {"python3"}))
    fake_tool(tmp_path, "python3", "Python 3.8.0")
    r = tools_cli(tmp_path, PAWL)
    assert r.returncode == 1 and "3.8.0" in r.stdout


def test_check_tools_searches_each_repos_own_toolchain_first(tmp_path):
    """control's pawl lives in its toolchain directory, not on the default PATH, so the preflight must look where the job will look:
    that repo's toolchain bin directories first (toolchains.bin_dirs), then the default. Another repo never sees control's directory."""
    root = tmp_path / "toolchains"
    tc = root / "pawl-0.1.0" / "bin"
    tc.mkdir(parents=True)
    fake_tool(tc, "pawl", "0.1.0")
    fake_tool(tc, "python3", "Python 3.12.3")
    base = tmp_path / "base"
    base.mkdir()
    fake_bin(base, ["git", "make"])
    assert tools_cli(base, CONTROL).returncode == 1  # without the root, pawl is missing, as before
    r = tools_cli(base, CONTROL, "--toolchains-root", str(root))
    assert r.returncode == 0 and "FAIL" not in r.stdout, r.stdout
    r = tools_cli(base, PAWL, "--toolchains-root", str(root))  # pawl's own repo declares no toolchain: no python3 for it here
    assert r.returncode == 1 and "python3" in r.stdout
    lines, ok = repo_ci.check_tools([CONTROL], str(base), toolchain_root=root)
    assert ok, lines


@pytest.mark.parametrize("script,shared", [("deploy/linux/preflight.sh", "/srv/apx"), ("deploy/apx-host-preflight.sh", "/Users/Shared/apx")])
def test_both_preflights_check_private_repo_tools_with_their_toolchains(script, shared):
    text = (ROOT / script).read_text()
    line = next(ln for ln in text.splitlines() if "autopilot.apx.repo_ci check-tools" in ln)
    assert f'--toolchains-root "${{APX_TOOLCHAINS_ROOT:-${{APX_SHARED:-{shared}}}/toolchains}}"' in line  # same root as the daemon


def test_memory_cap_leaves_headroom_on_the_planned_12_gb_box():
    unit = (ROOT / "deploy/linux/systemd/apx.service").read_text()
    gb = int(next(ln for ln in unit.splitlines() if ln.startswith("MemoryMax=")).split("=")[1].rstrip("G"))
    assert gb <= 8  # the static value is only a fallback; 12G was the whole box
    boot = (ROOT / "deploy/linux/bootstrap.sh").read_text()
    assert "MemTotal" in boot and "apx.service.d" in boot and "MemoryMax=" in boot
