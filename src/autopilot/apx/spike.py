"""Spike checker: read-only. After the one throwaway-PR spike, turns the open questions into PASS/FAIL lines.

  1. are the PR's commits GitHub-verified (signed)?            -> App-made git-data commits show Verified
  2. did apx post its check runs on the PR head, completed?   -> check runs can be posted from owner hardware
  3. were they posted by the apx App, not some other actor?   -> so the ruleset can later pin integration_id to it
  4. is the PR head branch an agent/* branch and not main?    -> only agent/* branches are ever pushed
Nothing here writes to GitHub.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Result:
    name: str
    ok: bool
    detail: str


def check_spike(api, repo: str, pr: int, *, app_slug: str, expect_contexts: list[str]) -> list[Result]:
    out: list[Result] = []
    p = api("GET", f"/repos/{repo}/pulls/{pr}")
    head_ref, sha = p["head"]["ref"], p["head"]["sha"]  # type: ignore[index]
    out.append(Result("head branch is agent/*", head_ref.startswith("agent/"), head_ref))
    commits = api("GET", f"/repos/{repo}/pulls/{pr}/commits?per_page=100")
    unverified = [
        c["sha"][:7] + ":" + (c["commit"].get("verification") or {}).get("reason", "?")
        for c in commits
        if not (c["commit"].get("verification") or {}).get("verified")
    ]  # type: ignore[union-attr]
    out.append(
        Result(
            "every commit is Verified",
            bool(commits) and not unverified,
            "ok" if not unverified else "unverified " + ", ".join(unverified),
        )
    )
    runs = api("GET", f"/repos/{repo}/commits/{sha}/check-runs?per_page=100")["check_runs"]  # type: ignore[index]
    by_name = {r["name"]: r for r in runs}
    for ctx in expect_contexts:
        r = by_name.get(ctx)
        out.append(
            Result(
                f"check run '{ctx}' posted and completed",
                bool(r) and r.get("status") == "completed",
                "missing" if not r else f"{r.get('status')}/{r.get('conclusion')}",
            )
        )
        if r:
            slug = (r.get("app") or {}).get("slug")
            out.append(Result(f"'{ctx}' was posted by the apx App", slug == app_slug, f"posted by {slug}"))
    return out


def render(results: list[Result]) -> tuple[str, bool]:
    lines = [f"{'PASS' if r.ok else 'FAIL'}  {r.name}: {r.detail}" for r in results]
    ok = all(r.ok for r in results)
    lines += [
        "",
        "spike: all unknowns confirmed"
        if ok
        else f"spike: {sum(not r.ok for r in results)} unknown(s) NOT confirmed; paste this back",
    ]
    return "\n".join(lines), ok
