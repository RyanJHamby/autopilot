"""Deploy docs and script headers must give commands that work as written (pure file reads)."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DAEMON_PLIST_PATH = "/Library/LaunchDaemons/com.autopilot.apx.plist"


def _doc_files() -> list[Path]:
    files = [*ROOT.glob("docs/**/*.md"), *ROOT.glob("deploy/*.sh"), *ROOT.glob("deploy/launchd/*.plist")]
    assert files
    return sorted(files)


def test_no_assignment_before_sudo():
    # sudo resets the environment, so `VAR=1 sudo cmd` runs cmd without VAR.
    pattern = re.compile(r"\b[A-Z_][A-Z0-9_]*=\S*\s+sudo\b")
    bad = [
        f"{p.relative_to(ROOT)}:{n}: {line.strip()}"
        for p in _doc_files()
        for n, line in enumerate(p.read_text().splitlines(), 1)
        if pattern.search(line)
    ]
    assert not bad, "VAR=value before sudo is dropped; use `sudo VAR=value ...`:\n" + "\n".join(bad)


def test_plist_header_cp_names_label_target():
    cp = re.compile(r"\bcp\s+\S+\s+(/Library/LaunchDaemons/\S*)")
    checked = 0
    for plist in ROOT.glob("deploy/launchd/*.plist"):
        text = plist.read_text()
        label = re.search(r"<key>Label</key>\s*<string>([^<]+)</string>", text).group(1)
        for line in text.splitlines():
            m = cp.search(line)
            if m:
                checked += 1
                assert m.group(1) == f"/Library/LaunchDaemons/{label}.plist", f"{plist.name}: {line.strip()}"
    assert checked


def test_host_move_installs_daemon_plist_before_switch():
    text = (ROOT / "docs/apx-host-move.md").read_text()
    start = text.index("## 4.")
    end = text.find("\n## 5.", start)
    section = text[start : end if end != -1 else None]
    assert DAEMON_PLIST_PATH in section
    assert "apx-switch-to-current.sh" in section
    assert section.index(DAEMON_PLIST_PATH) < section.index("apx-switch-to-current.sh")
