"""Drills: plant a known defect in a throwaway project and check that the standard's machinery catches it.

A control that has never been seen to fail proves nothing. Each drill builds a small fixture project in a temp directory
(never a real checkout, so nothing here can touch your repos), shows the clean fixture passes, plants one defect, and
reports one of:

  green          the clean baseline passed (the baseline-green drill)
  caught         the defect was detected, as it should be
  missed         the defect got through: a control is broken. Exits 1.
  baseline-failed the clean fixture didn't pass, so the drill proves nothing. Exits 1.
  limit          a defect the machinery can't see, recorded on purpose and expected to stay uncaught. If it ever
                 starts being caught, the drill reports `limit-fixed` and exits 1 so the documentation gets updated.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from autopilot import trace
from autopilot.standard import engine

KIT_RUNTIME = Path(__file__).resolve().parents[2] / "kit" / "runtime"
GOOD_WORKFLOW = (
    "name: ci\non: push\npermissions:\n  contents: read\njobs:\n  t:\n    steps:\n      - uses: actions/checkout@"
    + "a" * 40
    + "\n"
)
OWNERS = "/.github/ @o\n/.autopilot/ @o\n/.claude/ @o\n/AGENTS.md @o\n/CLAUDE.md @o\n/.mcp.json @o\n/CODEOWNERS @o\n/policy/ @o\n"
SPEC = "---\nid: demo\nacceptance:\n  - python -m pytest -q tests/test_feature.py\n  - ruff check .\n---\nbody\n"
FILES = {
    ".github/workflows/ci.yml": GOOD_WORKFLOW,
    "CODEOWNERS": OWNERS,
    "CLAUDE.md": "@AGENTS.md\n",
    "AGENTS.md": "rules\n",
    "Makefile": "check:\n\ttrue\n",
    "specs/demo.md": SPEC,
    "tests/test_feature.py": "def test_adds():\n    assert 1 + 1 == 2\n",
}


@dataclass
class DrillResult:
    id: str
    outcome: str
    detail: str


def build(root: Path, files: dict[str, str] | None = None) -> Path:
    for rel, text in {**FILES, **(files or {})}.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    for args in (
        ["init", "-q", "-b", "main"],
        ["add", "."],
        ["-c", "user.email=d@d", "-c", "user.name=drill", "commit", "-qm", "fixture"],
    ):
        subprocess.run(["git", "-c", "commit.gpgsign=false", *args], cwd=root, check=True, capture_output=True)
    return root


def run_acceptance(root: Path) -> tuple[int, list[trace.Case]]:
    """Run the fixture's pytest acceptance command and read back its JUnit results."""
    junit = root / "junit.xml"
    cmd = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", f"--junitxml={junit}", "tests/test_feature.py"]
    r = subprocess.run(cmd, cwd=root, capture_output=True, text=True)
    return r.returncode, trace.read_junit(junit) if junit.is_file() else []


def spec_status(root: Path, cases: list[trace.Case]) -> str:
    rows = trace.trace((root / "specs/demo.md").read_text(), cases)
    return next(r.status for r in rows if r.status != "not-traceable")


def baseline_green(tmp: Path) -> list[DrillResult]:
    root = build(tmp)
    code, cases = run_acceptance(root)
    problems = []
    if code != 0:
        problems.append(f"acceptance exited {code}")
    if (status := spec_status(root, cases)) != "green":
        problems.append(f"trace says {status}")
    if engine.exit_code(engine.run(engine.Repo(root)), strict=True) != 0:
        problems.append("the standard engine fails the clean fixture")
    if guard_violations(clean_diff(), agent=True):
        problems.append("the guard flags a clean diff")
    ok = not problems
    return [
        DrillResult("baseline-green", "green" if ok else "baseline-failed", "clean fixture passes" if ok else "; ".join(problems))
    ]


def hollow_link(tmp: Path) -> list[DrillResult]:
    """Two ways an acceptance test can be hollow. A skipped test is seen by trace; a test with no assertion is not."""
    out = []
    for drill, body, expect_caught in (
        ("hollow-link-skipped", "import pytest\n\ndef test_adds():\n    pytest.skip('later')\n", True),
        ("hollow-link-no-assertion", "def test_adds():\n    pass\n", False),
    ):
        root = build(tmp / drill, {"tests/test_feature.py": body})
        code, cases = run_acceptance(root)
        status = spec_status(root, cases)
        if code != 0:
            out.append(
                DrillResult(drill, "baseline-failed", f"expected the acceptance command to exit 0 (that is the trap), got {code}")
            )
        elif expect_caught:
            out.append(
                DrillResult(drill, "caught" if status != "green" else "missed", f"acceptance exits 0; trace says {status}")
            )
        else:
            out.append(
                DrillResult(
                    drill,
                    "limit" if status == "green" else "limit-fixed",
                    f"acceptance exits 0; trace says {status} (no assertion is invisible to it)",
                )
            )
    return out


def clean_diff() -> str:
    return "diff --git a/src/x.py b/src/x.py\n--- a/src/x.py\n+++ b/src/x.py\n@@ -1 +1,2 @@\n a = 1\n+b = 2\n"


def guard_violations(diff: str, agent: bool) -> list:
    sys.path.insert(0, str(KIT_RUNTIME))
    try:
        import guard  # the real guard, the same code the workflow runs
    finally:
        sys.path.remove(str(KIT_RUNTIME))
    return guard.analyze(guard.parse_diff(diff), agent=agent, protected=guard.DEFAULT_PROTECTED + ["policy/**"])


def guard_on_diff(tmp: Path) -> list[DrillResult]:
    """Feed the real guard synthetic diffs. A diff is all it needs, so no PR, git or network is involved."""
    out = []
    protected = (
        "diff --git a/.github/workflows/x.yml b/.github/workflows/x.yml\n--- a/.github/workflows/x.yml\n+++ b/.github/workflows/x.yml\n@@ -1 +1,2 @@\n a\n+b\n"
        "diff --git a/policy/waivers.yaml b/policy/waivers.yaml\n--- a/policy/waivers.yaml\n+++ b/policy/waivers.yaml\n@@ -1 +1,2 @@\n a\n+b\n"
    )
    hit = {v.path for v in guard_violations(protected, agent=True) if v.check == "protected-path"}
    want = {".github/workflows/x.yml", "policy/waivers.yaml"}
    out.append(DrillResult("guard-protected-paths", "caught" if hit == want else "missed", f"flagged {sorted(hit)}"))
    human = [v for v in guard_violations(protected, agent=False) if v.check == "protected-path"]
    out.append(
        DrillResult("guard-ignores-humans", "caught" if not human else "missed", "the same diff from a human is not blocked")
    )
    deleted = "diff --git a/tests/test_a.py b/tests/test_a.py\ndeleted file mode 100644\n--- a/tests/test_a.py\n+++ /dev/null\n@@ -1 +0,0 @@\n-def test_a(): assert 1\n"
    seen = {v.check for v in guard_violations(deleted, agent=True)}
    out.append(DrillResult("guard-test-deletion", "caught" if "test-deletion" in seen else "missed", f"flagged {sorted(seen)}"))
    return out


DRILLS: dict[str, Callable[[Path], list[DrillResult]]] = {
    "baseline-green": baseline_green,
    "hollow-link": hollow_link,
    "guard-on-diff": guard_on_diff,
}
BAD = {"missed", "baseline-failed", "limit-fixed"}


def run_all(only: list[str] | None = None) -> list[DrillResult]:
    out: list[DrillResult] = []
    for name, fn in DRILLS.items():
        if only and name not in only:
            continue
        with tempfile.TemporaryDirectory(prefix="ap-drill-") as td:
            try:
                out += fn(Path(td))
            except Exception as e:  # a drill that crashes proves nothing, so it must not look like a pass
                out.append(DrillResult(name, "baseline-failed", f"drill crashed: {type(e).__name__}: {e}"))
    return out


def cmd_drill(ns) -> int:
    unknown = [n for n in ns.drills if n not in DRILLS]
    if unknown:
        print(f"ERROR unknown drill {', '.join(unknown)}; known: {', '.join(DRILLS)}")
        return 2
    results = run_all(ns.drills)
    for r in results:
        print(f"  {r.outcome:15} {r.id}  {r.detail}")
    return 1 if any(r.outcome in BAD for r in results) else 0
