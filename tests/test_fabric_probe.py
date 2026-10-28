import subprocess
from pathlib import Path

PROBE = Path(__file__).parent.parent / "src/autopilot/fabric/redteam_probe.sh"


def test_probe_is_valid_bash():
    assert subprocess.run(["bash", "-n", str(PROBE)]).returncode == 0


def test_probe_covers_every_attack_class_in_the_plan():
    t = PROBE.read_text()
    for needle in ("169.254.169.254", "192.168.0.1", "100.100.100.100", "853", "ipv6", "docker.sock", "gh credentials",
                   "pids.max", "api.anthropic.com", "registry.npmjs.org", "attacker-example.com", "CLAUDE_CODE_OAUTH_TOKEN"):
        assert needle in t, needle


def test_probe_refuses_to_run_without_a_lane():
    r = subprocess.run(["bash", str(PROBE)], env={"PATH": "/usr/bin:/bin"}, capture_output=True, text=True)
    assert r.returncode != 0 and "LANE" in r.stderr


def test_probe_never_prints_secret_values():
    assert "echo \"$CLAUDE" not in PROBE.read_text() and "echo $CLAUDE" not in PROBE.read_text()
