import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "deploy" / "apx-ci-account.sh"


def text():
    return SCRIPT.read_text()


def dry_run():
    return subprocess.run(["bash", str(SCRIPT)], env={"DRY_RUN": "1", "PATH": "/usr/bin:/bin"}, capture_output=True, text=True)


def test_dry_run_previews_everything_and_changes_nothing():
    r = dry_run()
    assert r.returncode == 0, r.stderr
    out = r.stdout
    for expected in (
        "sysadminctl -addUser apx-ci",
        "install -d -m 700 -o apx-ci",  # its home is private
        "/Users/Shared/apx/venv",  # python with PyYAML for the guard
        "visudo -cf",  # the sudoers rule is checked before install
        "APX_CI_USER=apx-ci",
    ):
        assert expected in out, expected
    assert all(line.startswith(("DRY-RUN", " ", "Add ", "Whenever")) or not line for line in out.splitlines())  # nothing executed


def test_the_sudoers_rule_lets_apx_act_as_apx_ci_and_nothing_wider():
    s = text()
    assert 'SUDOERS_LINE="$ORCH ALL=($CI) NOPASSWD:SETENV: ALL"' in s  # target user is pinned to apx-ci, never root or ALL
    assert "ALL=(ALL)" not in s and "ALL=(root)" not in s
    check = 'visudo -cf "$TMP" >/dev/null || { say "sudoers syntax check failed; nothing installed"; exit 1; }'
    assert check in s  # the real command, not the mention in a comment, and a failure aborts the install
    assert s.index(check) < s.index('install -m 440 -o root -g wheel "$TMP" "$SUDOERS_FILE"')  # validated first
    assert ">> /etc/sudoers" not in s and "> /etc/sudoers " not in s  # only a drop-in file, never the main sudoers


def test_the_script_proves_the_split_from_the_sandbox_side_and_fails_if_it_leaks():
    s = text()
    assert "/bin/cat" in s and "app.pem" in s
    assert "the split is NOT in place" in s and "exit 1" in s
    assert "must NOT be an admin" in s


def test_it_is_conservative_about_what_it_touches():
    s = text()
    assert "set -euo pipefail" in s and 'DRY_RUN="${DRY_RUN:-0}"' in s
    removers = (
        "rm " + "-r",
        "rm " + "-f /",
        "chmod " + "-R 777",
        "chmod " + "777",
        "dscl . " + "-delete",
        "sysadminctl " + "-deleteUser",
    )
    for banned in removers:
        assert banned not in s, banned
    assert s.count("chmod -R go+rX") == 1 and 'chmod -R go+rX "$SHARED"' in s  # world-readable only for the shared code area
