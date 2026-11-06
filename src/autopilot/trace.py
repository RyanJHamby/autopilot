"""Does a spec's acceptance actually run tests, and did they pass? Reads pytest's JUnit XML; never runs anything.

An acceptance command that exits 0 proves less than it looks like. `pytest tests/test_x.py` exits 0 when every test in
the file is skipped, and exits 0 for a test that asserts nothing. This reads the results and reports, per acceptance
command that names pytest targets:

  green         at least one matching test ran, and none failed, errored or skipped
  failing       a matching test failed or errored
  skipped       a matching test was skipped or xfailed (the command may still exit 0)
  not-run       no test in the results matches the target: the link is hollow
  not-traceable the command isn't pytest (ruff, npm, ...), so there is nothing to read

What it can't see: a test that runs and passes while asserting nothing. That is a documented limit, and `ap drill`
exercises it. It is warn-only unless `--strict`.
"""

from __future__ import annotations

import shlex
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass
class Case:
    classname: str
    name: str
    status: str  # passed | failed | skipped


@dataclass
class Row:
    command: str
    status: str
    detail: str


def acceptance(spec_text: str) -> list[str]:
    """The `acceptance:` commands from a spec's front matter. Strings only; anything else in the list is ignored."""
    parts = spec_text.split("---", 2)
    if len(parts) < 3:
        return []
    try:
        front = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        return []
    items = front.get("acceptance") if isinstance(front, dict) else None
    return [i for i in items if isinstance(i, str)] if isinstance(items, list) else []


def pytest_targets(command: str) -> list[str] | None:
    """Paths (and `::test` selectors) a pytest command names. [] means pytest with no path, so every test. None means the
    command isn't pytest. Option values (`-k expr`, `--junitxml f`) are not paths; the common ones are skipped."""
    try:
        tokens = shlex.split(command)
    except ValueError:
        return None
    for i, tok in enumerate(tokens):
        if tok == "pytest" or tok.endswith("/pytest") or (tok == "-m" and tokens[i + 1 : i + 2] == ["pytest"]):
            start = i + (2 if tok == "-m" else 1)
            break
    else:
        return None
    with_value = {"-k", "-m", "-c", "-p", "--junitxml", "--rootdir", "--tb", "-o", "--maxfail", "-n"}
    targets, skip = [], False
    for tok in tokens[start:]:
        if skip:
            skip = False
        elif tok in with_value:
            skip = True
        elif not tok.startswith("-"):
            targets.append(tok)
    return targets


def read_junit(path: Path) -> list[Case]:
    cases = []
    for tc in ET.parse(path).getroot().iter("testcase"):
        status = "passed"
        for child in tc:
            if child.tag in ("failure", "error"):
                status = "failed"
                break
            if child.tag == "skipped":
                status = "skipped"
        cases.append(Case(tc.get("classname", ""), tc.get("name", ""), status))
    return cases


def _matches(case: Case, target: str) -> bool:
    path, _, selector = target.removeprefix("./").partition("::")
    module = path.removesuffix(".py").strip("/").replace("/", ".")
    in_module = case.classname == module or case.classname.startswith(module + ".")
    return in_module and (not selector or case.name.split("[")[0] == selector.split("::")[-1])


def trace(spec_text: str, cases: list[Case]) -> list[Row]:
    rows = []
    for cmd in acceptance(spec_text):
        targets = pytest_targets(cmd)
        if targets is None:
            rows.append(Row(cmd, "not-traceable", "not a pytest command"))
            continue
        hit = [c for c in cases if not targets or any(_matches(c, t) for t in targets)]
        counts = {s: sum(c.status == s for c in hit) for s in ("passed", "failed", "skipped")}
        summary = f"{counts['passed']} passed, {counts['failed']} failed, {counts['skipped']} skipped"
        if not hit:
            rows.append(Row(cmd, "not-run", "no test in the results matches " + (", ".join(targets) or "this command")))
        elif counts["failed"]:
            rows.append(Row(cmd, "failing", summary))
        elif counts["skipped"]:
            rows.append(Row(cmd, "skipped", summary))
        else:
            rows.append(Row(cmd, "green", summary))
    return rows


def cmd_trace(ns) -> int:
    spec = Path(ns.spec).expanduser()
    junit = Path(ns.junit).expanduser()
    for p in (spec, junit):
        if not p.is_file():
            print(f"ERROR {p} not found")
            return 2
    rows = trace(spec.read_text(encoding="utf-8"), read_junit(junit))
    if not rows:
        print(f"WARN {spec.name} has no acceptance commands to trace")
    for r in rows:
        tag = "ok" if r.status == "green" else "--" if r.status == "not-traceable" else "WARN"
        print(f"  {tag:4} {r.status:13} {r.command}   ({r.detail})")
    unmet = [r for r in rows if r.status in ("failing", "skipped", "not-run")]
    return 1 if (ns.strict and unmet) else 0
