"""Keeps docs/apx-compromise.md honest: everything it names in the repo must still exist, so the runbook cannot rot silently.

Checked: env vars, repo file paths (scripts, plists, docs, modules), `python -m` modules, launchd labels, and host paths
(/Users/..., /etc/..., /Library/...) that the deploy scripts or source also name. It cannot check that the commands work on the host.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOC = ROOT / "docs" / "apx-compromise.md"
SKIP_DIRS = {"node_modules", ".next", "__pycache__", ".git", ".venv"}


def _corpus() -> str:
    """Text of the files the runbook is derived from (never the runbook itself)."""
    files = [p for d in ("src", "deploy", "apps", "policy") for p in (ROOT / d).rglob("*") if p.is_file()]
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
    assert DOC.is_file(), "docs/apx-compromise.md is missing"
    text = DOC.read_text()
    assert len(text) > 2000
    return text


def test_doc_has_every_required_section_and_marks_admin_and_unverified():
    t = _doc()
    for heading in (
        "## 1. Stop apx",
        "## 2. Triage",
        "## 3. Rotation",
        "## 4. What to check on GitHub",
        "## 5. Resume safely",
        "## 6. Drill",
    ):
        assert heading in t, heading
    for marker in ("[RYAN-SUDO]", "[RYAN-ADMIN]", "unverified"):
        assert marker in t, marker
    for account in ("`apx`", "`apx-ci`", "`apx-agent`"):
        assert account in t, account


def test_env_vars_named_in_the_doc_exist_in_the_repo():
    t, corpus = _doc(), _corpus()
    names = set(re.findall(r"\b(?:APX|AUTOPILOT)_[A-Z][A-Z_]*[A-Z]\b", t))
    assert {"APX_LIVE", "AUTOPILOT_PAUSED", "APX_KEY_PATH", "APX_CUTOVER", "APX_AUTHORITATIVE", "APX_AGENT_USER"} <= names
    missing = sorted(n for n in names if n not in corpus)
    assert not missing, f"env vars not found in src/deploy/apps: {missing}"


def test_repo_paths_named_in_the_doc_exist():
    t = _doc()
    paths = set(re.findall(r"\b((?:deploy|docs|src|policy|tests|apps|scripts)/[A-Za-z0-9_./-]*[A-Za-z0-9_])", t))
    assert {"deploy/apx-ci-account.sh", "deploy/apx-agent-account.sh", "deploy/apx-install-mac.sh"} <= paths
    assert "deploy/launchd/com.autopilot.apx.daemon.plist" in paths
    assert "src/autopilot/apx/status.py" in paths
    missing = sorted(p for p in paths if not (ROOT / p).exists())
    assert not missing, f"paths named in the doc do not exist: {missing}"


def test_python_modules_named_in_the_doc_exist():
    t = _doc()
    mods = set(re.findall(r"-m (autopilot(?:\.\w+)+)", t))
    assert {"autopilot.apx.daemon", "autopilot.apx.status", "autopilot.apx.pin"} <= mods
    for m in mods:
        base = ROOT / "src" / Path(*m.split("."))
        assert base.with_suffix(".py").is_file() or (base / "__init__.py").is_file(), m


def test_launchd_labels_named_in_the_doc_match_a_plist():
    t = _doc()
    labels = set(re.findall(r"system/(com\.autopilot[\w.]*)", t))
    assert "com.autopilot.apx" in labels
    plist_text = "\n".join(p.read_text() for p in (ROOT / "deploy" / "launchd").glob("*.plist"))
    for label in labels:
        assert f"<string>{label}</string>" in plist_text, label


def test_host_paths_named_in_the_doc_are_named_by_the_scripts_or_source():
    t, corpus = _doc(), _corpus()
    host = set(re.findall(r"(/(?:Users|etc|Library)/[A-Za-z0-9_./-]*[A-Za-z0-9_])", t))
    host = {h for h in host if not re.search(r"/[A-Z][A-Z-]{3,}", h)}  # drop placeholders like PLIST-FILE
    assert "/Users/apx/.apx/app.pem" in host and "/Users/apx-agent/.apx/claude-oauth" in host
    bad = []
    for h in sorted(host):
        parts = h.split("/")  # '', 'Users', name, rest...
        if parts[1] == "Users" and parts[2] != "Shared":
            tail = "/".join(parts[3:])
            ok = h in corpus or bool(tail and f"/{tail}" in corpus)
            # the account itself must be one the deploy scripts create
            ok = ok and (parts[2] in corpus)
        else:
            ok = h in corpus or h.rstrip("/") in corpus
        if not ok:
            bad.append(h)
    assert not bad, f"host paths not found in deploy/src/apx docs: {bad}"
