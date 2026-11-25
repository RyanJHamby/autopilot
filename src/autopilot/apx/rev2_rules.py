"""Rev 2 required checks (vendored from RyanJHamby/ci checks/rev2_checks.py at v1; keep the two in step). Pure functions plus a small CLI so any CI runner can call them.

  python3 rev2_checks.py handoff      --body-file PR_BODY.md
  python3 rev2_checks.py gated-paths  --files changed.txt --labels "a,b"
  python3 rev2_checks.py denylist     --text-file all_text.txt          (terms from $REV2_DENYLIST, comma or newline separated)
  python3 rev2_checks.py work-hours   --commits commits.tsv             (lines: sha<TAB>author_iso<TAB>committer_iso)
  python3 rev2_checks.py bench-claims --diff-file pr.diff

Exit 0 = pass, 1 = fail (reasons on stdout). Stdlib only.
"""

from __future__ import annotations

import argparse
import fnmatch
import os
import re
import sys
from datetime import datetime, time
from zoneinfo import ZoneInfo

HANDOFF_SECTIONS = ["Done", "State", "Decision needed", "Next (agent)", "Next (you)", "Risks", "Tokens"]
MUST_FILL = ["Done", "Next (you)", "Tokens"]

GATED = [
    "CODEOWNERS",
    ".github/*",
    ".claude/*",
    ".mcp.json",
    "CLAUDE.md",
    "AGENTS.md",
    "scripts/ci/*",
    "guardrails/*",
    "README*",
    "*/README*",
    "package.json",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "pyproject.toml",
    "requirements*.txt",
    "uv.lock",
    "poetry.lock",
    "Cargo.toml",
    "Cargo.lock",
    "go.mod",
    "go.sum",
    "Podfile.lock",
    "*.gradle",
    "*.gradle.kts",
    "*/billing/*",
    "billing/*",
    "*/payments/*",
    "payments/*",
    "*/auth/*",
    "auth/*",
]

DAYS = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4, "Sat": 5, "Sun": 6}
DEFAULT_WINDOW = "Mon-Fri 08:30-18:30 America/New_York"

BENCH = re.compile(r"\b\d[\d,.]*\s?(ns|us|µs|ms|s|sec|GB/s|MB/s|Gbps|ops/s|req/s|qps|rps|tok/s|tokens/s|x|%)(?![A-Za-z])")


def _strip_comments(text: str) -> str:
    return re.sub(r"<!--.*?-->", "", text, flags=re.S)


def check_handoff(body: str) -> list[str]:
    body = _strip_comments(body or "")
    parts = re.split(r"^##\s+(.+?)\s*$", body, flags=re.M)
    found = {parts[i].strip(): parts[i + 1].strip() for i in range(1, len(parts) - 1, 2)}
    errors = [f"missing section: ## {s}" for s in HANDOFF_SECTIONS if s not in found]
    errors += [f"empty section: ## {s}" for s in MUST_FILL if s in found and not found[s]]
    return errors


def is_gated(path: str) -> bool:
    while path.startswith("./"):
        path = path[2:]
    path = path.lstrip("/")
    return any(fnmatch.fnmatch(path, p) or path == p for p in GATED)


def check_gated(files: list[str], labels: list[str]) -> list[str]:
    hits = [f for f in files if f and is_gated(f)]
    if hits and "human-ok" not in labels:
        return [f"gated path needs the human-ok label: {f}" for f in hits]
    return []


def denylist_terms(raw: str | None) -> list[str]:
    return [t.strip() for t in re.split(r"[,\n]", raw or "") if t.strip()]


def check_denylist(text: str, terms: list[str]) -> list[str]:
    if not terms:
        return ["denylist not configured (set REV2_DENYLIST); failing closed"]
    low = text.lower()
    # Never echo the term itself into public CI logs: report only its index.
    return [f"denylisted term #{i + 1} found" for i, t in enumerate(terms) if t.lower() in low]


def parse_window(spec: str):
    days, hours, tz = spec.split()
    d0, d1 = days.split("-")
    h0, h1 = hours.split("-")
    return (set(range(DAYS[d0], DAYS[d1] + 1)), time.fromisoformat(h0), time.fromisoformat(h1), ZoneInfo(tz))


def in_window(ts: str, spec: str = DEFAULT_WINDOW) -> bool:
    days, start, end, tz = parse_window(spec)
    local = datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(tz)
    return local.weekday() in days and start <= local.time() < end


def check_work_hours(commits: list[tuple[str, str, str]], spec: str = DEFAULT_WINDOW) -> list[str]:
    errors = []
    for sha, authored, committed in commits:
        for kind, ts in (("authored", authored), ("committed", committed)):
            if ts and in_window(ts, spec):
                errors.append(f"{sha[:10]} {kind} inside the work-hours window ({spec})")
    return errors


def check_bench_claims(diff: str) -> list[str]:
    errors, current = [], ""
    for line in diff.splitlines():
        if line.startswith("+++ "):
            current = line[6:] if line.startswith("+++ b/") else line[4:]
            continue
        name = os.path.basename(current)
        if not name.upper().startswith("README") or not line.startswith("+") or line.startswith("+++"):
            continue
        if BENCH.search(line) and "results/" not in line:
            errors.append(f"{current}: number without a results/ link: {line[1:].strip()[:80]}")
    return errors


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("handoff").add_argument("--body-file", required=True)
    g = sub.add_parser("gated-paths")
    g.add_argument("--files", required=True)
    g.add_argument("--labels", default="")
    sub.add_parser("denylist").add_argument("--text-file", required=True)
    w = sub.add_parser("work-hours")
    w.add_argument("--commits", required=True)
    w.add_argument("--window", default=os.environ.get("REV2_WINDOW", DEFAULT_WINDOW))
    sub.add_parser("bench-claims").add_argument("--diff-file", required=True)
    a = ap.parse_args(argv)

    if a.cmd == "handoff":
        errors = check_handoff(_read(a.body_file))
    elif a.cmd == "gated-paths":
        errors = check_gated(_read(a.files).splitlines(), [x.strip() for x in a.labels.split(",") if x.strip()])
    elif a.cmd == "denylist":
        errors = check_denylist(_read(a.text_file), denylist_terms(os.environ.get("REV2_DENYLIST")))
    elif a.cmd == "work-hours":
        rows = [tuple((x.split("\t") + ["", ""])[:3]) for x in _read(a.commits).splitlines() if x.strip()]
        errors = check_work_hours(rows, a.window)
    else:
        errors = check_bench_claims(_read(a.diff_file))

    for e in errors:
        print(e)
    print("PASS" if not errors else f"FAIL ({len(errors)})")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
