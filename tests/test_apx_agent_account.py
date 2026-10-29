import re
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "deploy" / "apx-agent-account.sh"


def text():
    return SCRIPT.read_text()


def test_dry_run_previews_everything_and_changes_nothing():
    r = subprocess.run(["bash", str(SCRIPT)], env={"DRY_RUN": "1", "PATH": "/usr/bin:/bin"}, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    for expected in (
        "sysadminctl -addUser apx-agent",
        "install -d -m 700 -o apx-agent",  # its home is private
        "install -m 600 -o apx-agent -g staff /Users/apx/.apx/claude-oauth /Users/apx-agent/.apx/claude-oauth",  # token goes in at 0600
        "visudo -cf",
        "APX_AGENT_USER=apx-agent",
    ):
        assert expected in r.stdout, expected
    assert all(line.startswith(("DRY-RUN", " ", "Next", "Refresh")) or not line for line in r.stdout.splitlines())


def test_the_sudoers_rule_lets_apx_act_as_apx_agent_and_nothing_wider():
    s = text()
    assert 'SUDOERS_LINE="$ORCH ALL=($AGENT) NOPASSWD:SETENV: ALL"' in s
    assert "ALL=(ALL)" not in s and "ALL=(root)" not in s
    check = 'visudo -cf "$TMP" >/dev/null || { say "sudoers syntax check failed; nothing installed"; exit 1; }'
    assert check in s and s.index(check) < s.index('install -m 440 -o root -g wheel "$TMP" "$SUDOERS_FILE"')


def test_it_proves_the_separation_from_every_side_and_aborts_on_any_leak():
    s = text()
    for proof in (
        'sudo -u "$AGENT" /bin/cat "/Users/$ORCH/.apx/app.pem"',  # the model's account cannot read the write key
        'sudo -u "$AGENT" /bin/ls "/Users/$ORCH/.apx"',  # nor the orchestrator's home
        'sudo -u "$CI" /bin/cat "$NEW_TOKEN"',  # the account that runs PR code cannot read the model's token
        'sudo -u "$AGENT" /bin/test -r "$NEW_TOKEN"',  # the model's account can read its own
        "--version",  # and run the CLI
    ):
        assert proof in s, proof
    assert s.count("fail ") >= 6 and "must NOT be an admin" in s


def test_the_token_is_installed_into_the_agent_home_at_mode_0600_by_the_real_command_not_just_the_preview():
    s = text()
    assert '  install -m 600 -o "$AGENT" -g staff "$OLD_TOKEN" "$NEW_TOKEN"\n' in s  # the executed line, not the DRY-RUN echo
    assert 'install -d -m 700 -o "$AGENT" -g staff "$AGENT_HOME"' in s


def test_the_only_deletion_is_the_old_copy_of_the_token_and_only_after_the_agent_proved_it_can_read_its_own():
    s = text()
    removals = re.findall(r"\brm -\w+ [^\n]*", s)
    assert len(removals) == 2, removals  # exactly: the old token copy, and the script's own temp file
    assert sorted(removals) == sorted(['rm -f "$OLD_TOKEN"', 'rm -f "$TMP"\' EXIT']), (
        removals
    )  # whole lines, nothing appended to them
    assert 'rm -f "$OLD_TOKEN"' in s
    own = s.index('sudo -u "$AGENT" /bin/test -r "$NEW_TOKEN"')
    claude = s.index("--version >/dev/null 2>&1 || fail")
    rm = s.index('rm -f "$OLD_TOKEN"')
    assert own < rm and claude < rm  # removed only after the proofs
    assert 'KEEP_OLD_TOKEN" != 1' in s  # and the owner can opt out
    banned = ("rm " + "-r", "chmod " + "-R 777", "chmod " + "777", "dscl . " + "-delete", "sysadminctl " + "-deleteUser")
    assert not any(b in s for b in banned)
    assert "set -euo pipefail" in s and 'DRY_RUN="${DRY_RUN:-0}"' in s


def test_it_refuses_to_run_before_the_ci_account_exists():
    s = text()
    assert 'id "$CI" >/dev/null 2>&1 || { say "run deploy/apx-ci-account.sh first' in s
