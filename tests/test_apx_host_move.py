"""Static checks on the host-move kit (docs/apx-host-move.md). The scripts need macOS and sudo, so tests read them instead of running them."""

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PREFLIGHT = ROOT / "deploy" / "apx-host-preflight.sh"
RETIRE = ROOT / "deploy" / "apx-retire-host.sh"
DOC = ROOT / "docs" / "apx-host-move.md"


def code_lines(path):
    """The script's lines minus comments."""
    return [ln for ln in path.read_text().splitlines() if ln.strip() and not ln.lstrip().startswith("#")]


def test_both_scripts_are_valid_bash():
    for p in (PREFLIGHT, RETIRE):
        r = subprocess.run(["bash", "-n", str(p)], capture_output=True, text=True)
        assert r.returncode == 0, (p, r.stderr)


def test_preflight_is_read_only_and_never_runs_sudo():
    text = "\n".join(code_lines(PREFLIGHT))
    for forbidden in (
        r"\brm\b",
        r"\bmv\b",
        r"\bchmod\b",
        r"\bchown\b",
        r"\binstall\b -",
        r"launchctl (bootstrap|bootout|load|unload)",
        r"\bdscl\b",
        r"sysadminctl",
        r"\btee\b",
    ):
        assert not re.search(forbidden, text), forbidden
    for ln in code_lines(PREFLIGHT):
        unquoted = re.sub(r'"[^"]*"', "", ln)  # sudo may be printed as advice, never run
        assert not re.search(r"\bsudo\b", unquoted), ln
    assert "id -u" in text  # refuses to run as root


def test_retire_previews_by_default_and_only_ever_stops_jobs():
    text = RETIRE.read_text()
    assert 'DO="${DO:-0}"' in text
    code = "\n".join(code_lines(RETIRE))
    for forbidden in (
        r"\brm\b",
        r"\bsrm\b",
        r"\bdscl\b",
        r"sysadminctl",
        r"launchctl bootstrap",
        r"\bmv\b",
        r"\bsecurity delete",
    ):
        assert not re.search(forbidden, code), forbidden
    assert code.count("launchctl bootout") == 1
    assert code.index('if [ "$DO" = 1 ]') < code.index("launchctl bootout")  # the stop is inside the DO=1 branch
    assert "NOT touched" in text  # it lists the secrets it leaves alone


def test_runbook_names_every_script_it_uses_and_states_the_one_live_host_rule():
    doc = DOC.read_text()
    assert "never two live hosts" in doc.lower()
    for script in re.findall(r"deploy/[\w.-]+\.sh", doc):
        assert (ROOT / script).exists(), script
    for needed in ("apx-host-preflight.sh", "apx-retire-host.sh", "apx-switch-to-current.sh", "apx-updater-setup.sh"):
        assert needed in doc
    assert doc.index("apx-retire-host.sh") < doc.index(
        "sudo bash deploy/apx-switch-to-current.sh"
    )  # old host stops before the new one goes live
