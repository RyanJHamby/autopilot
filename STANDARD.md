# Project standard

Status: **v0 draft, standard version 1.** The rule list and labels are in
[`src/autopilot/standard/checks.yaml`](src/autopilot/standard/checks.yaml). Run them with `ap standard check REPO`, or
`ap standard check --portfolio` for every enabled repo. All 14 rules have a check. The engine runs from the CLI on a
machine and, offline, from a CI step in `ci.yml`.

This file says what a repo should have and how each rule is backed. It makes no claim that following it improves how
well agents work. Where a rule is judgment, it says so.

## How each rule is backed

| Label | Meaning | Can it fail a run? |
|---|---|---|
| `enforced` | CI or a ruleset blocks the change | Yes, and it blocks the merge |
| `audited` | `ap standard check` reports it when someone runs it | Yes, but nothing blocks a merge |
| `advisory` | Judgment, not enforced anywhere | No, it only warns |

Six rules are `enforced`: the `fail`-level ones. They are enforced by the `ci.yml` step
`uv run ap standard check . --offline`, which exits non-zero when one of them fails. That step runs offline, so it
never asks GitHub anything. Two limits: nothing has yet run on GitHub Actions, so "enforced" is the design until a real
pull request shows the step blocking; and whether the step is a *required* status check depends on the ruleset, which
is an owner setting. A test checks that the CI step exists whenever any rule claims `enforced`.

A result is `pass`, `fail`, `unknown`, `skip` or `waived`. `unknown` means the check couldn't be answered, for example
because `gh` isn't installed, the ruleset can't be read, or a workflow file doesn't parse. It is never counted as a pass,
and `--strict` makes it fail a level-`fail` rule. `skip` means the rule doesn't apply to this repo, and is still printed.
`waived` is a failure covered by a live waiver, below.

A rule's **level** says what a failing result does to the run: `fail` exits non-zero, `warn` prints. New rules start at
`warn` until the portfolio is clean, so adding a rule never breaks a repo overnight.

## The rules

| Rule | Level | Label | Applies to |
|---|---|---|---|
| `pinned-actions` | fail | enforced | all |
| `workflow-permissions` | fail | enforced | all |
| `no-privileged-triggers` | fail | enforced | all |
| `secret-exposed-workflows` | fail | enforced | all |
| `codeowners-cover-protected-paths` | fail | enforced | all |
| `no-tracked-secrets` | fail | enforced | all |
| `thin-claude-md` | warn | audited | all |
| `one-check-entrypoint` | warn | audited | all |
| `license-present` | warn | audited | public repos |
| `ruleset-present` | warn | audited | all |
| `agents-md-budget` | warn | advisory | all |
| `how-this-was-built` | warn | advisory | all |
| `journal-present` | warn | advisory | all |
| `dependency-updates` | warn | advisory | all |
| `gitignore-present` | warn | advisory | all |
| `templates-present` | warn | advisory | all |
| `commands-documented` | warn | advisory | all |
| `security-policy` | warn | advisory | public repos |
| `contributing-present` | warn | advisory | public repos |

Each rule's reason and fix are in `checks.yaml`, which is the single source. A test fails if this table and that file
disagree.

## Which repos a rule applies to

`applies_to` is derived from keys that already exist in `policy/portfolio.yaml` (`public`, `data_class`). There is no
separate "repo kind" field, and this standard doesn't read a product's stage: stage belongs to the bets ledger, and
reading it here would create a second policy file.

A rule can also report `skip` when the repo has nothing for it to check. `dependency-updates` skips a repo with no
manifests and no workflows, and `one-check-entrypoint` skips a repo with no manifests, workflows or Makefile (a
docs-only repo, for example). A skip is shown as a skip, never as a pass, and a repo that has something to update or
run but no config or check still fails.

## Waivers

A repo that can't meet a rule yet needs a waiver. Waivers live in one central file, `policy/waivers.yaml` in the
autopilot checkout, one entry per repo and rule with an `owner`, a `reason`, and `granted` and `expires` dates at most 30
days apart. They are read from `origin/main`, not the working tree, so a pull request can't waive its own failure. An
expired waiver stops applying and the rule fails again. An entry that is malformed is ignored and reported, never
half-applied. If `origin/main` can't be found, no waiver is applied. The file doesn't exist yet: creating it is an owner
edit (`policy/**` is protected).

Only a `fail` can be waived. An `unknown` has nothing to waive.

## What is measured and what isn't

- The rules marked `advisory` are judgment. Whether a short `AGENTS.md` helps an agent is unproven: one paper reports
  that context files don't generally improve task success, and I have only read its abstract.
- The 60-line figure is a starting value, not a measured threshold.
- Nothing here has been shown to raise first-pass success. Measuring that needs your own numbers, captured with
  `pow run`.

## Open decisions (owner)

1. **Tier numbering.** `specs/_TEMPLATE.md` numbers risk tiers 1, 2, 3 while `kit/runtime/tier.py` uses 0, 1, 2. This
   standard doesn't choose.
2. **Required check.** Make the CI job a required status check in the `autopilot-main` ruleset, or the step can fail
   without blocking the merge.
3. **Rulesets on your plan.** Whether rulesets and code owners bind on private repos depends on the GitHub plan, which
   hasn't been checked. Run `gh api user --jq .plan.name`.

## Related

A product repo is either autopilot-managed or pawl-scaffolded, never both: the two disagree about who owns `.claude/`,
`.mcp.json`, and the list of protected paths.
