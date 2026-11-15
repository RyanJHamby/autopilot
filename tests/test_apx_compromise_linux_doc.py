"""Keeps docs/apx-compromise-linux.md honest, as tests/test_apx_compromise_doc.py does for the macOS runbook: everything it names in the
repo must still exist, so it cannot rot silently. It cannot check that the commands work on the host."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOC = ROOT / "docs" / "apx-compromise-linux.md"
SKIP_DIRS = {"node_modules", ".next", "__pycache__", ".git", ".venv"}


def _corpus() -> str:
    files = [p for d in ("src", "deploy") for p in (ROOT / d).rglob("*") if p.is_file()]
    files += [p for p in (ROOT / "docs").glob("apx-*.md") if p != DOC]
    out = []
    for p in files:
        if SKIP_DIRS & set(p.parts):
            continue
        try:
            out.append(p.read_text())
        except (UnicodeDecodeError, OSError):
            pass
    return "\n".join(out)


def _doc() -> str:
    assert DOC.is_file(), "docs/apx-compromise-linux.md is missing"
    return DOC.read_text()


def _code_lines(text: str) -> list[str]:
    lines, inside = [], False
    for line in text.splitlines():
        if line.startswith("```"):
            inside = not inside
            continue
        if inside:
            lines.append(line)
    return lines


def test_sections_in_order_and_markers():
    t = _doc()
    headings = [
        "## 1. Stop everything now",
        "## 2. Contain egress",
        "## 3. Revoke credentials",
        "## 4. Preserve evidence",
        "## 5. Find out what happened",
        "## 6. Rebuild and recover",
        "## 7. Back to normal",
        "## Rehearsal (dry run)",
    ]
    positions = [t.index(h) for h in headings]
    assert positions == sorted(positions)
    for marker in ("[RYAN-ADMIN]", "unverified", "not supported on Linux yet"):
        assert marker in t, marker
    assert len(t.splitlines()) < 800


def test_linked_from_the_macos_runbook_and_the_linux_host_page():
    for name in ("apx-compromise.md", "apx-linux-host.md"):
        assert "(apx-compromise-linux.md)" in (ROOT / "docs" / name).read_text(), name


def test_no_inline_comments_on_command_lines():
    bad = [line for line in _code_lines(_doc()) if re.search(r"\s#", line) and not line.lstrip().startswith("#")]
    assert not bad, bad


def test_env_vars_exist_in_the_repo():
    t, corpus = _doc(), _corpus()
    names = set(re.findall(r"\b(?:APX|AUTOPILOT)_[A-Z][A-Z_]*[A-Z]\b", t))
    assert {"APX_KEY_PATH", "APX_DB", "APX_SHADOW", "APX_SHA", "AUTOPILOT_PAUSED", "APX_AGENT_USER"} <= names
    missing = sorted(n for n in names if n not in corpus)
    assert not missing, missing


def test_repo_paths_and_modules_exist():
    t = _doc()
    paths = set(re.findall(r"\b((?:deploy|docs|src|tests|scripts)/[A-Za-z0-9_./-]*[A-Za-z0-9_])", t))
    assert {
        "deploy/linux/retire.sh",
        "deploy/linux/release.sh",
        "deploy/linux/bootstrap.sh",
        "deploy/linux/egress-probe.sh",
    } <= paths
    missing = sorted(p for p in paths if not (ROOT / p).exists())
    assert not missing, missing
    for m in set(re.findall(r"-m (autopilot(?:\.\w+)+)", t)):
        base = ROOT / "src" / Path(*m.split("."))
        assert base.with_suffix(".py").is_file() or (base / "__init__.py").is_file(), m


def test_systemd_units_named_exist():
    t = _doc()
    units = set(re.findall(r"\b(apx(?:-[a-z]+)?\.(?:service|timer))\b", t))
    assert {"apx.service", "apx.timer", "apx-updater.service", "apx-updater.timer", "apx-nft.service", "apx-dns.service"} <= units
    have = {p.name for p in (ROOT / "deploy" / "linux" / "systemd").iterdir()}
    assert units <= have, sorted(units - have)


def test_host_paths_are_named_by_the_scripts_or_source():
    t, corpus = _doc(), _corpus()
    host = set(
        re.findall(r"(/(?:home/apx[a-z-]*|srv/apx|etc/apx|etc/sudoers\.d|etc/systemd/system)[A-Za-z0-9_./-]*[A-Za-z0-9_])", t)
    )
    assert "/home/apx/.apx/app.pem" in host and "/home/apx-agent/.apx/claude-oauth" in host and "/srv/apx/swap.json" in host
    # status.json and update.json are built from the shared dir in status.py, swap.json and HOLD are documented in release.py
    derived = {"/srv/apx/status.json", "/srv/apx/update.json", "/srv/apx/swap.json", "/srv/apx/HOLD"}
    bad = sorted(h for h in host - derived if h not in corpus and h.rsplit("/", 1)[0] not in corpus)
    assert not bad, bad
    for name in ("status.json", "update.json", "swap.json", "HOLD"):
        assert name in corpus, name
