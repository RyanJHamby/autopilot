"""Runner controller: decides which sandbox to start for which queued GitHub job. Pure decision logic plus a dry-run poller.

Security shape (see the secure compute fabric plan):
  * only in-scope repos are ever served; a job whose labels name no known lane, or two lanes, is ignored
  * one JIT runner per job (single use, ephemeral); the registration credential never enters a sandbox
  * per-lane and per-repo concurrency caps; a repo cannot starve the others
  * the controller itself runs OUTSIDE the sandbox and holds the only credential able to register runners
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass

IN_SCOPE = ("RyanJHamby/autopilot", "RyanJHamby/drillpad-workspace", "RyanJHamby/stencil")
LANE_PREFIX = "lane-"
LANES = ("trusted", "ci", "exec")
DEFAULT_LANE_CAPS = {"trusted": 2, "ci": 2, "exec": 1}
DEFAULT_REPO_CAP = 2


@dataclass(frozen=True)
class Job:
    repo: str
    run_id: int
    job_id: int
    labels: tuple[str, ...]


@dataclass(frozen=True)
class Spawn:
    repo: str
    job_id: int
    lane: str
    runner_name: str
    labels: tuple[str, ...]


def lane_of(labels: tuple[str, ...] | list[str]) -> str | None:
    """The single lane a job asks for, or None if it asks for none, several, or an unknown one."""
    wanted = {lb[len(LANE_PREFIX):] for lb in labels if lb.startswith(LANE_PREFIX)}
    if len(wanted) != 1:
        return None
    lane = next(iter(wanted))
    return lane if lane in LANES else None


def plan(
    queued: list[Job],
    running: list[Spawn],
    *,
    lane_caps: dict[str, int] | None = None,
    repo_cap: int = DEFAULT_REPO_CAP,
    in_scope: tuple[str, ...] = IN_SCOPE,
) -> list[Spawn]:
    """Spawns to start now. Oldest-first within a repo, repos served round-robin so none starves the rest."""
    caps = {**DEFAULT_LANE_CAPS, **(lane_caps or {})}
    lane_n = {lane: sum(1 for r in running if r.lane == lane) for lane in LANES}
    repo_n: dict[str, int] = {}
    for r in running:
        repo_n[r.repo] = repo_n.get(r.repo, 0) + 1
    started = {r.job_id for r in running}

    per_repo: dict[str, list[Job]] = {}
    for j in sorted(queued, key=lambda j: j.job_id):
        if j.repo in in_scope and j.job_id not in started and "self-hosted" in j.labels:
            per_repo.setdefault(j.repo, []).append(j)

    out: list[Spawn] = []
    while any(per_repo.values()):
        progressed = False
        for repo in sorted(per_repo):
            if not per_repo[repo]:
                continue
            j = per_repo[repo].pop(0)
            lane = lane_of(j.labels)
            if lane is None or lane_n[lane] >= caps[lane] or repo_n.get(repo, 0) >= repo_cap:
                continue
            lane_n[lane] += 1
            repo_n[repo] = repo_n.get(repo, 0) + 1
            out.append(Spawn(repo, j.job_id, lane, f"ap-{lane}-{j.job_id}", ("self-hosted", f"{LANE_PREFIX}{lane}")))
            progressed = True
        if not progressed and not any(per_repo.values()):
            break
    return out


def jit_body(spawn: Spawn, runner_group_id: int = 1) -> dict:
    """Body for POST /repos/{repo}/actions/runners/generate-jitconfig. JIT runners are single-use by construction."""
    return {"name": spawn.runner_name, "runner_group_id": runner_group_id, "labels": list(spawn.labels), "work_folder": "_work"}


Gh = Callable[[str], object]


def queued_jobs(gh: Gh, repos: tuple[str, ...] = IN_SCOPE) -> list[Job]:
    """Queued jobs that asked for a self-hosted runner. `gh(path)` returns parsed JSON (REST only, no GraphQL)."""
    jobs: list[Job] = []
    for repo in repos:
        runs = gh(f"repos/{repo}/actions/runs?status=queued&per_page=50")
        for run in (runs or {}).get("workflow_runs", []):  # type: ignore[union-attr]
            data = gh(f"repos/{repo}/actions/runs/{run['id']}/jobs?per_page=50")
            for j in (data or {}).get("jobs", []):  # type: ignore[union-attr]
                if j.get("status") == "queued" and "self-hosted" in j.get("labels", []):
                    jobs.append(Job(repo, run["id"], j["id"], tuple(j["labels"])))
    return jobs


def _gh(path: str) -> object:
    out = subprocess.run(["gh", "api", path], capture_output=True, text=True, check=True).stdout
    return json.loads(out or "{}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true", default=True, help="print the plan; starting sandboxes is not implemented yet")
    ns = ap.parse_args(argv)
    spawns = plan(queued_jobs(_gh), [])
    for s in spawns:
        print(f"WOULD START {s.runner_name} for {s.repo} job {s.job_id} (lane {s.lane})")
    if not spawns:
        print("nothing queued for a self-hosted runner")
    return 0 if ns.dry_run else 2


if __name__ == "__main__":
    sys.exit(main())
