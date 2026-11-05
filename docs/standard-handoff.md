# Standard v0: what's built, and what only you can do

Written 2026-11-03 on branch `feat/standard-v0`, updated 2026-11-05. I did not edit any protected path; the owner edits were
applied by Ryan running a script I wrote.

## What exists (all tested, 1034 tests pass; captures in `results/2026-11-03-06*`)
- `STANDARD.md` + `src/autopilot/standard/checks.yaml`: 14 rules, each labeled `enforced` / `audited` / `advisory`.
- `ap standard check`: runs all 14 (`engine.py`), `--portfolio` finds clones by origin name, base-ref waivers (`waivers.py`).
- `ap doctor` delegates pin, secret-exposure and CLAUDE.md checks to the engine; it now flags `@v4.2.2` and non-autopilot workflows.
- `ap trace`: reads pytest JUnit XML; reports each acceptance command as green / failing / skipped / not-run.
- `ap drill`: 6 drill results in a throwaway fixture. One is a recorded limit: a test with no assertion passes everything.

## Six rules are `enforced` (2026-11-05)
The six `fail`-level rules are labeled `enforced`, by the `ci.yml` step `uv run ap standard check . --offline`.
`test_every_enforced_rule_names_a_ci_step_that_exists` fails if that step is removed. This is the design, not an
observed result: nothing has run on GitHub Actions yet, and the step blocks a merge only if the CI job is a required
check in the `autopilot-main` ruleset.

## Done in the owner session (2026-11-05)
Applied by `owner_edits.py`: the CI step in `ci.yml` and `repo.yaml`, `extra_protected` entries for the standard, `trace.py`
and `drill.py`, CODEOWNERS entries, `policy/waivers.yaml` (`waivers: []`), `public: true` for `autopilot`, and the quoted
`run:` in `redteam-secrets.yml`. After it, `ap standard check . --offline` on this repo: 11 pass, 2 fail (`license-present`,
`dependency-updates`), 1 unknown (`ruleset-present`, offline).

## Your list (every item needs your account or a decision)
0. Make the CI job a required status check in the `autopilot-main` ruleset. Without that, "enforced" is not true.
1. Add a `LICENSE` to `autopilot` (public repo; `license-present` fails). The choice is yours.
2. Add a Dependabot or Renovate config if you want `dependency-updates` to pass (advisory, warn only).
3. Clone `stencil` and `launch-scratch` if you want `--portfolio` to exit 0 (both are enabled in `portfolio.yaml`).
4. Run `gh api user --jq .plan.name` and `gh api repos/RyanJHamby/autopilot/rulesets`, then re-run `ap standard check --portfolio` without `--offline`. Until then `ruleset-present` is unknown, and rulesets on a private repo may not bind on your plan.
5. Decide tier numbering: `specs/_TEMPLATE.md` says 1/2/3, `kit/runtime/tier.py` uses 0/1/2.
6. `docs/journal.md` will conflict with `docs/permissions-log-2026-11-02`, which is a trivial merge.

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
