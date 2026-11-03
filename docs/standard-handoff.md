# Standard v0: what's built, and what only you can do

Written 2026-11-03 on branch `feat/standard-v0`. Nothing here is pushed. I did not edit any protected path.

## What exists (all tested, 1034 tests pass; captures in `results/2026-11-03-06*`)
- `STANDARD.md` + `src/autopilot/standard/checks.yaml`: 14 rules, each labeled `enforced` / `audited` / `advisory`.
- `ap standard check`: runs all 14 (`engine.py`), `--portfolio` finds clones by origin name, base-ref waivers (`waivers.py`).
- `ap doctor` delegates pin, secret-exposure and CLAUDE.md checks to the engine; it now flags `@v4.2.2` and non-autopilot workflows.
- `ap trace`: reads pytest JUnit XML; reports each acceptance command as green / failing / skipped / not-run.
- `ap drill`: 6 drill results in a throwaway fixture. One is a recorded limit: a test with no assertion passes everything.

## Nothing is `enforced` yet
No CI step runs the engine, so nothing blocks a merge. `test_nothing_claims_enforcement_before_ci_runs_the_engine` says so.

## Your list (one session; every item is a protected path or needs your account)
1. `.autopilot/repo.yaml`: add to `guard.extra_protected`: `src/autopilot/standard/**`, `src/autopilot/trace.py`, `src/autopilot/drill.py`, `policy/waivers.yaml`. Add `uv run ap standard check . --offline` to `ci:`. (No `drills/` directory exists; the drills are in `drill.py`.)
2. `.github/workflows/ci.yml`: the same step. Then in the same change delete the "nothing claims enforcement" test and set the labels you now enforce to `enforced` with an `enforced_by`.
3. Create `policy/waivers.yaml` (`waivers: []`) and add `/CODEOWNERS @RyanJHamby` and `/src/autopilot/standard/` to CODEOWNERS.
4. Fix `.github/workflows/redteam-secrets.yml`: line 30 is not valid YAML (`run: echo "LEAK: ..."` has an unquoted `: `), so the probe can't run. Quote the whole `run:` value.
5. Clone `stencil` and `launch-scratch` if you want `--portfolio` to exit 0 (both are enabled in `portfolio.yaml`).
6. Run `gh api user --jq .plan.name` and `gh api repos/RyanJHamby/autopilot/rulesets`, then re-run `ap standard check --portfolio` without `--offline`. Until then `ruleset-present` is unknown, and rulesets on a private repo may not bind on your plan.
7. Decide tier numbering: `specs/_TEMPLATE.md` says 1/2/3, `kit/runtime/tier.py` uses 0/1/2.
8. Say yes to a batched push and PR (signed commits, no squash). `docs/journal.md` will conflict with `docs/permissions-log-2026-11-02`, which is a trivial merge.

## Findings the standard made on real repos (offline run)
- `drillpad-workspace`: unpinned `actions/checkout@v4`; no top-level `permissions`; CODEOWNERS doesn't own itself; no Dependabot/Renovate.
- `autopilot`: unparseable `redteam-secrets.yml`; CODEOWNERS doesn't own itself; no Dependabot/Renovate.
I changed neither repo.

## Not verified
- That any of this improves agent success. Nothing here measures it.
- Anything on GitHub Actions or against the live ruleset API.
- CODEOWNERS matching is a path-prefix test, not GitHub's matcher; mid-path wildcards are not understood.
- `ap trace` can't see a test that asserts nothing.

## Not built
Pawl control-repo bet, `stage` applicability, scorecard UI, kit-workflow wiring, tier reconciliation, KB carve-out.
