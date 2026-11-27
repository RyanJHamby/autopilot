"""The five Rev 2 required checks, run on apx's trusted side from GitHub API data (no PR code is executed).

Contexts posted on each trusted open PR head, under apx's own App identity:
    rev2 / handoff, rev2 / gated-paths, rev2 / denylist, rev2 / work-hours, rev2 / bench-claims

A PR is re-checked whenever its fingerprint changes: head sha, body, title, labels and the lane's own settings. So adding the
`human-ok` label or filling the handoff re-runs the checks on the next pass without a new push. The fingerprint is stored as the
check runs' external_id; a run whose external_id matches is the answer for that state.

Owner settings come from the host environment only, never from a repo:
    APX_REV2           comma list of OWNER/REPO to check (empty = lane off)
    APX_REV2_DENYLIST  comma list of names to keep out (unset = the denylist check fails closed); never posted or logged
    APX_REV2_WINDOW    work-hours window, default "Mon-Fri 08:30-18:30 America/New_York"
The daemon skips the whole pass inside the work-hours freeze, so this lane does too.
"""

from __future__ import annotations

import hashlib
from typing import Callable

from .. import freeze
from . import rev2_rules as rules
from .checks import post_check
from .planner import APX_APP_SLUG, _trusted_pr

CONTEXTS = ("rev2 / handoff", "rev2 / gated-paths", "rev2 / denylist", "rev2 / work-hours", "rev2 / bench-claims")
Api = Callable[..., object]


def settings(env: dict) -> dict:
    return {
        "repos": [r.strip() for r in (env.get("APX_REV2") or "").split(",") if r.strip()],
        "terms": rules.denylist_terms(env.get("APX_REV2_DENYLIST")),
        "window": env.get("APX_REV2_WINDOW") or rules.DEFAULT_WINDOW,
        "lifts": lift_dates(),
    }


def lift_dates() -> frozenset:
    """ET dates lifted in policy/time.yaml (the same file the freeze reads). Unreadable file: no lifts, so the check stays strict."""
    try:
        return freeze.load(freeze.DEFAULT_FILE).lift_dates
    except Exception:  # noqa: BLE001 - a broken policy file must never loosen a check
        return frozenset()


def fingerprint(pr: dict, labels: list[str], terms: list[str], window: str, lifts: frozenset = frozenset()) -> str:
    """Changes whenever an input to any of the five checks changes. Terms enter only as a hash, never in clear."""
    terms_hash = hashlib.sha256("\n".join(sorted(t.lower() for t in terms)).encode()).hexdigest()
    lifted = ",".join(sorted(d.isoformat() for d in lifts))
    parts = [pr["head"]["sha"], pr.get("title") or "", pr.get("body") or "", ",".join(sorted(labels)), window, terms_hash, lifted]
    return hashlib.sha256("\x1f".join(parts).encode()).hexdigest()[:40]


def diff_text(files: list[dict]) -> str:
    """A unified-diff-shaped text from the PR files API (enough for the line-based checks)."""
    out = []
    for f in files:
        out.append(f"+++ b/{f['filename']}")
        out.append(f.get("patch") or "")
    return "\n".join(out)


def evaluate(
    pr: dict,
    labels: list[str],
    files: list[dict],
    commits: list[dict],
    terms: list[str],
    window: str,
    lifts: frozenset = frozenset(),
) -> dict:
    """{context: (ok, summary)}. Pure: everything comes from the arguments."""
    diff = diff_text(files)
    messages = "\n".join((c.get("commit") or {}).get("message") or "" for c in commits)
    text = "\n".join([pr.get("title") or "", pr.get("body") or "", messages, diff])
    rows = [
        (
            c["sha"],
            ((c.get("commit") or {}).get("author") or {}).get("date") or "",
            ((c.get("commit") or {}).get("committer") or {}).get("date") or "",
        )
        for c in commits
    ]
    rows = [r for r in rows if not _lifted(r, window, lifts)]
    results = {
        "rev2 / handoff": rules.check_handoff(pr.get("body") or ""),
        "rev2 / gated-paths": rules.check_gated([f["filename"] for f in files], labels),
        "rev2 / denylist": rules.check_denylist(text, terms),
        "rev2 / work-hours": rules.check_work_hours(rows, window),
        "rev2 / bench-claims": rules.check_bench_claims(diff),
    }
    return {ctx: (not errs, "\n".join(f"- {e}" for e in errs) if errs else "pass") for ctx, errs in results.items()}


def _lifted(row: tuple, window: str, lifts: frozenset) -> bool:
    """A commit whose author and committer times both fall on a lifted day (in the window's timezone) is not a work-hours commit."""
    if not lifts:
        return False
    tz = rules.parse_window(window)[3]
    days = set()
    for ts in row[1:]:
        if ts:
            days.add(rules.datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(tz).date())
    return bool(days) and days <= lifts


def already_answered(runs: list[dict], fp: str) -> bool:
    ours = {c["name"]: c for c in runs if (c.get("app") or {}).get("slug", APX_APP_SLUG) == APX_APP_SLUG}
    return all(ctx in ours and ours[ctx].get("external_id") == fp and ours[ctx].get("status") == "completed" for ctx in CONTEXTS)


def post(api: Api, repo: str, sha: str, ctx: str, ok: bool, summary: str, fp: str) -> None:
    run = post_check(api, repo, sha, ctx, ok, summary)
    if isinstance(run, dict) and run.get("id"):
        api("PATCH", f"/repos/{repo}/check-runs/{run['id']}", {"external_id": fp})


def run_pass(api: Api, owner: str, env: dict) -> list[str]:
    cfg = settings(env)
    log = []
    for repo in cfg["repos"]:
        try:
            pulls = api("GET", f"/repos/{repo}/pulls?state=open&per_page=100")
        except Exception as e:  # noqa: BLE001 - one unreadable repo must not stop the others
            log.append(f"rev2 {repo}: could not list PRs ({type(e).__name__})")
            continue
        for pr in pulls:  # type: ignore[union-attr]
            if not _trusted_pr(pr, repo, owner):
                continue
            n, sha = pr["number"], pr["head"]["sha"]
            try:
                labels = [lb["name"] for lb in pr.get("labels") or []]
                fp = fingerprint(pr, labels, cfg["terms"], cfg["window"], cfg["lifts"])
                runs = api("GET", f"/repos/{repo}/commits/{sha}/check-runs?per_page=100")["check_runs"]  # type: ignore[index]
                if already_answered(runs, fp):
                    continue
                files = api("GET", f"/repos/{repo}/pulls/{n}/files?per_page=100")
                commits = api("GET", f"/repos/{repo}/pulls/{n}/commits?per_page=100")
                results = evaluate(pr, labels, files, commits, cfg["terms"], cfg["window"], cfg["lifts"])  # type: ignore[arg-type]
                for ctx in CONTEXTS:
                    ok, summary = results[ctx]
                    post(api, repo, sha, ctx, ok, summary, fp)
                failed = [c.split(" / ")[1] for c in CONTEXTS if not results[c][0]]
                log.append(f"rev2 {repo}#{n} {sha[:7]}: " + ("all pass" if not failed else "fail " + ",".join(failed)))
            except Exception as e:  # noqa: BLE001 - the next pass retries this PR
                log.append(f"rev2 {repo}#{n}: failed ({type(e).__name__})")
    return log
