"""The doctor checks, as the sandbox account and on the sandbox job's PATH, that every host tool each enrolled repo's CI needs is there and
good enough. On the first Linux host, drillpad-workspace's tests failed for a missing clang++ and rustc, and admin's for an apt gitleaks
without the `gitleaks git` subcommand; nothing had checked either in advance. The declarations and the capability probes are DATA
(src/autopilot/apx/host_tools.json, plus the "tools" lists in repo_ci.json), never code per repo."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest
from test_apx_daemon import env
from test_apx_doctor import factory

from autopilot.apx import daemon as dm
from autopilot.apx import doctor as dr
from autopilot.apx import host_tools, repo_ci, sandbox, toolchains
from autopilot.apx.runas import Launcher

DRILL, STENCIL, AUTO, ADMIN, CONTROL, PAWL = (
    f"RyanJHamby/{r}" for r in ("drillpad-workspace", "stencil", "autopilot", "admin", "control", "pawl")
)


def make_settings(tmp_path, inst, private=""):
    e = env(tmp_path, APX_INSTALLATIONS=",".join(f"{r}={i}" for i, r in enumerate(inst, 11)), APX_CI_USER="apx-ci")
    if private:
        e["APX_PRIVATE_CI"] = private
    e["APX_SHARED"] = str(tmp_path / "shared")
    return dm.Settings.from_env(e)


def fake(bindir: Path, name: str, body: str = "exit 0") -> None:
    bindir.mkdir(parents=True, exist_ok=True)
    p = bindir / name
    p.write_text("#!/bin/sh\n" + body + "\n")
    p.chmod(0o755)


# a clang++ that writes a runnable program to its -o target, as a real one would
CLANG_OK = 'for a; do [ "$prev" = -o ] && out=$a; prev=$a; done; /bin/cat >/dev/null; printf "#!/bin/sh\\nexit 0\\n" >"$out"; /bin/chmod +x "$out"'
CLANG_NO_UBSAN = '/bin/cat >/dev/null; echo "clang: error: unsupported option -fsanitize=undefined" >&2; exit 1'
RUSTC_OK = "/bin/cat >/dev/null; exit 0"
RUSTC_OLD = '/bin/cat >/dev/null; echo "error: argument for --edition must be one of: 2015|2018" >&2; exit 1'
GITLEAKS_OLD = 'echo "Usage:\n  gitleaks [command]\n\nAvailable Commands:\n  detect"'  # cobra falls back to the root help
GITLEAKS_NEW = 'echo "Usage:\n  gitleaks git [flags] [repo]"'


def checks(s, bindir: Path, launcher=None, extra=""):
    out = dr.repo_tool_checks(s, launcher or Launcher(), path_for=lambda repo: str(bindir) + extra)
    return {c.name: c for c in out}


def test_drillpad_missing_clang_and_rustc_fail_one_line_each_with_the_install_hint(tmp_path):
    s = make_settings(tmp_path, [DRILL])
    b = tmp_path / "bin"
    for t in ("git", "uv"):
        fake(b, t)
    out = checks(s, b)
    clang, rust = out[f"{DRILL}: host tool clang++"], out[f"{DRILL}: host tool rustc"]
    assert not clang.ok and "apt-get install clang" in clang.detail and "missing" in clang.detail
    assert not rust.ok and "apt-get install rustc" in rust.detail
    assert out[f"{DRILL}: host tool git"].ok and out[f"{DRILL}: host tool uv"].ok
    text, ok = dr.render(list(out.values()))
    assert not ok
    fails = [ln for ln in text.splitlines() if ln.startswith("FAIL")]
    assert len(fails) == 2 and all(DRILL in ln for ln in fails)


def test_a_clang_that_cannot_link_ubsan_fails_and_one_that_can_passes(tmp_path):
    s = make_settings(tmp_path, [DRILL])
    b = tmp_path / "bin"
    for t in ("git", "uv"):
        fake(b, t)
    fake(b, "rustc", RUSTC_OK)
    fake(b, "clang++", CLANG_NO_UBSAN)
    c = checks(s, b)[f"{DRILL}: host tool clang++"]
    assert not c.ok and "fsanitize=undefined" in c.detail and "apt-get install clang" in c.detail
    fake(b, "clang++", CLANG_OK)
    out = checks(s, b)
    assert all(c.ok for c in out.values()), {n: c.detail for n, c in out.items() if not c.ok}


def test_a_rustc_without_edition_2021_fails(tmp_path):
    s = make_settings(tmp_path, [DRILL])
    b = tmp_path / "bin"
    for t in ("git", "uv"):
        fake(b, t)
    fake(b, "clang++", CLANG_OK)
    fake(b, "rustc", RUSTC_OLD)
    c = checks(s, b)[f"{DRILL}: host tool rustc"]
    assert not c.ok and "2021" in c.detail and "apt-get install rustc" in c.detail


def test_apt_gitleaks_without_the_git_subcommand_fails_even_when_it_exits_zero(tmp_path):
    s = make_settings(tmp_path, [ADMIN], private=ADMIN)
    b = tmp_path / "bin"
    for t in ("git", "python3", "bash"):
        fake(b, t)
    fake(b, "gitleaks", GITLEAKS_OLD)
    c = checks(s, b)[f"{ADMIN}: host tool gitleaks"]
    assert not c.ok and "gitleaks git" in c.detail and "/usr/local/bin" in c.detail and "checksum" in c.detail
    fake(b, "gitleaks", GITLEAKS_NEW)
    assert checks(s, b)[f"{ADMIN}: host tool gitleaks"].ok


def test_private_repo_minimum_versions_are_checked_as_the_sandbox_account(tmp_path):
    s = make_settings(tmp_path, [CONTROL], private=CONTROL)
    b = tmp_path / "bin"
    fake(b, "git")
    fake(b, "pawl")
    fake(b, "python3", 'echo "Python 3.10.12"')
    c = checks(s, b)[f"{CONTROL}: host tool python3"]
    assert not c.ok and "3.10.12" in c.detail and "3.11" in c.detail
    fake(b, "python3", 'echo "Python 3.12.3"')
    assert checks(s, b)[f"{CONTROL}: host tool python3"].ok


NO_YAML = 'case "$1" in --version) echo "Python 3.12.3" ;; *) echo "ModuleNotFoundError: No module named \'yaml\'" >&2; exit 1 ;; esac'
WITH_YAML = 'case "$1" in --version) echo "Python 3.12.3" ;; *) echo 6.0.2 ;; esac'


def test_controls_python3_must_import_yaml_but_pawls_need_not(tmp_path):
    """control's plan-coverage scripts import yaml; on the first try with pawl installed they failed with ModuleNotFoundError. The probe is
    scoped to that repo ("repo_probes" in host_tools.json), because pawl's own CI, on the same python3, needs no PyYAML."""
    s = make_settings(tmp_path, [CONTROL, PAWL], private=f"{CONTROL},{PAWL}")
    b = tmp_path / "bin"
    for t in ("git", "pawl", "make"):
        fake(b, t)
    fake(b, "python3", NO_YAML)
    out = checks(s, b)
    c = out[f"{CONTROL}: host tool python3"]
    assert not c.ok and "PyYAML" in c.detail and "pawl-" in c.detail  # the hint points at the pawl toolchain venv
    assert out[f"{PAWL}: host tool python3"].ok
    fake(b, "python3", WITH_YAML)
    assert checks(s, b)[f"{CONTROL}: host tool python3"].ok


def test_the_shipped_repo_probe_for_control_imports_yaml():
    data = host_tools.load()
    p = data.probe_for(CONTROL, "python3")
    assert p is not None and p.argv[0] == "python3" and "import yaml" in " ".join(p.argv)
    assert data.probe_for(PAWL, "python3") is None and data.probe_for(CONTROL, "git") is None
    assert data.hint_for(CONTROL, "python3") != data.hint("python3")
    assert data.hint_for(PAWL, "python3") == data.hint("python3")
    assert data.probe_for(DRILL, "clang++") is data.probes["clang++"]  # unscoped probes still apply to every repo


def test_the_real_yaml_probe_passes_on_a_python_that_has_it(tmp_path):
    """The probe's own argv against a real interpreter, so a typo in the data cannot pass unnoticed. Skipped without PyYAML here."""
    import sys

    probe = subprocess.run([sys.executable, "-c", "import yaml"], capture_output=True)
    if probe.returncode != 0:
        pytest.skip("no PyYAML in this interpreter")
    s = make_settings(tmp_path, [CONTROL], private=CONTROL)
    b = tmp_path / "bin"
    for t in ("git", "pawl"):
        fake(b, t)
    (b / "python3").symlink_to(sys.executable)
    c = checks(s, b)[f"{CONTROL}: host tool python3"]
    assert c.ok, c.detail


def test_a_repo_that_declares_nothing_says_so_and_passes(tmp_path, monkeypatch):
    s = make_settings(tmp_path, [AUTO])
    data = host_tools.load()
    monkeypatch.setattr(host_tools, "load", lambda path=None: host_tools.HostTools({}, data.probes, data.hints))
    out = checks(s, tmp_path / "empty")
    assert list(out) == [f"{AUTO}: host tools"] and out[f"{AUTO}: host tools"].ok


def test_the_default_path_is_the_sandbox_jobs_path_with_the_repos_toolchain_first(tmp_path):
    s = make_settings(tmp_path, [STENCIL])
    seen = []

    class Rec:
        def run(self, argv, **kw):
            seen.append(kw["env"]["PATH"])
            return subprocess.CompletedProcess(argv, 1, "", "")

    dr.repo_tool_checks(s, Rec())
    want = sandbox.job_path(s.ci_home(), toolchains.bin_dirs(STENCIL, Path(s.shared_dir) / "toolchains"))
    assert seen and set(seen) == {want}
    assert want.startswith(str(Path(s.shared_dir) / "toolchains" / "node-20" / "bin") + ":")
    assert sandbox.job_path("/home/apx-ci") == "/opt/homebrew/bin:/usr/local/bin:/home/apx-ci/.local/bin:/usr/bin:/bin"


def test_the_doctor_runs_the_host_tool_checks_through_the_sandbox_launcher(tmp_path):
    s = make_settings(tmp_path, [DRILL])
    seen = []

    class Rec:
        def run(self, argv, **kw):
            seen.append(argv)
            return subprocess.CompletedProcess(argv, 1, "", "")

    names = [
        c.name
        for c in dr.run_doctor(  # no network and no real claude: the GitHub and floor parts are faked as in test_apx_doctor
            s,
            launcher=Rec(),
            which=lambda t: f"/usr/bin/{t}",
            approved=lambda r: [],
            api_factory=factory(),
            claude_probe=lambda binary: "2.1.323 (Claude Code)\n",
        )
    ]
    assert f"{DRILL}: host tool clang++" in names
    assert any(a[:2] == ["/bin/sh", "-c"] and a[-1] == "clang++" for a in seen)


def test_a_launcher_that_crashes_fails_the_checks_and_never_the_doctor(tmp_path):
    s = make_settings(tmp_path, [DRILL])

    class Dead:
        def run(self, argv, **kw):
            raise RuntimeError("sudo failed")

    out = checks(s, tmp_path, launcher=Dead())
    assert out and not any(c.ok for c in out.values())


def test_every_enrolled_autopilot_repo_declares_its_host_tools():
    data = host_tools.load()
    assert set(data.repos) == set(dm.REQUIRED_CONTEXTS)
    assert {"clang++", "rustc"} <= set(data.repos[DRILL])
    for repo, entries in data.repos.items():
        for e in entries:
            repo_ci.parse_tool(e)  # same entry syntax as repo_ci.json
    for tool in ("gitleaks", "clang++", "rustc"):
        assert tool in data.probes and tool in data.hints
    specs = repo_ci.load_specs()
    assert not set(data.repos) & set(specs)  # one source per repo: private repos keep theirs in repo_ci.json
    assert "<" not in "".join(data.hints.values())  # no placeholder or version-specific checksum in the hints


@pytest.mark.parametrize(
    "bad",
    [
        {"repos": {DRILL: "clang++"}, "probes": {}, "hints": {}},
        {"repos": {DRILL: ["clang++ ; rm"]}, "probes": {}, "hints": {}},
        {"repos": {}, "probes": {"clang++": {"argv": [], "needs": "x"}}, "hints": {}},
        {"repos": {}, "probes": {"clang++": {"argv": ["sh", "-c", "true"], "needs": "x"}}, "hints": {}},  # relative, not the tool
        {"repos": {}, "probes": {"clang++": {"argv": ["clang++"]}}, "hints": {}},  # says nothing about what it proves
        {"repos": {}, "probes": {"gitleaks": {"argv": ["gitleaks"], "needs": "x", "expect": "("}}, "hints": {}},
        {"repos": {}, "probes": {}, "hints": {}, "repo_probes": {CONTROL: "python3"}},
        {"repos": {}, "probes": {}, "hints": {}, "repo_probes": {CONTROL: {"python3": {"argv": ["sh"], "needs": "x"}}}},
        {"repos": {}, "probes": {}, "hints": {}, "repo_probes": {CONTROL: {"python3": {"argv": ["python3"], "needs": "x", "hint": 3}}}},
        {"repos": {}, "probes": {}, "hints": {}, "repo_probes": {"not a repo": {"python3": {"argv": ["python3"], "needs": "x"}}}},
    ],
)
def test_malformed_data_is_refused(tmp_path, bad):
    import json

    p = tmp_path / "h.json"
    p.write_text(json.dumps(bad))
    with pytest.raises(ValueError):
        host_tools.load(p)


@pytest.mark.parametrize("tool", ["clang++", "rustc"])
def test_the_real_probe_passes_with_a_real_compiler_when_one_is_here(tmp_path, tool):
    """The probe scripts themselves, against a real compiler, so a typo in the data cannot pass unnoticed. Skipped where it is absent."""
    found = shutil.which(tool)
    if not found:
        pytest.skip(f"no {tool} in this environment")
    if tool == "rustc":  # a rustup proxy needs the caller's HOME; link the real compiler instead
        p = subprocess.run([found, "--print", "sysroot"], capture_output=True, text=True)
        if p.returncode != 0:
            pytest.skip(f"this environment's rustc does not run: {p.stderr.strip()[:80]}")
        found = str(Path(p.stdout.strip()) / "bin" / "rustc")
    s = make_settings(tmp_path, [DRILL])
    b = tmp_path / "bin"
    for t in ("git", "uv"):
        fake(b, t)
    others = {"clang++": ("rustc", RUSTC_OK), "rustc": ("clang++", CLANG_OK)}
    fake(b, *others[tool])
    (b / tool).symlink_to(found)
    c = checks(s, b, extra=":/usr/bin:/bin")[f"{DRILL}: host tool {tool}"]  # the compiler driver finds its linker there
    if not c.ok and tool == "clang++" and "fsanitize" in c.detail:
        pytest.skip(f"this environment's clang++ cannot link UBSan: {c.detail}")
    assert c.ok, c.detail


def test_the_doctor_fails_when_the_daemon_account_could_swap_a_toolchain(tmp_path, monkeypatch):
    """The compromise runbook relies on the doctor to say whether the toolchains can be trusted; /srv/apx is apx-owned by design."""
    s = make_settings(tmp_path, [STENCIL])
    b = toolchains.bin_dirs(STENCIL, toolchains.default_root(s.shared_dir))[0]
    fake(Path(b), "node")
    apx_owned = str(Path(s.shared_dir))
    monkeypatch.setattr(
        toolchains, "_lstat", lambda p: os.stat_result((0o40755, 0, 0, 2, 1001 if str(p) == apx_owned else 0, 0, 0, 0, 0, 0))
    )
    c = checks(s, tmp_path / "bin")[f"{STENCIL}: toolchain node@20 is root-owned up to /"]
    assert not c.ok and apx_owned in c.detail and "APX_TOOLCHAINS_ROOT" in c.detail
    monkeypatch.setattr(toolchains, "_lstat", lambda p: os.stat_result((0o40755, 0, 0, 2, 0, 0, 0, 0, 0, 0)))
    assert checks(s, tmp_path / "bin")[f"{STENCIL}: toolchain node@20 is root-owned up to /"].ok
