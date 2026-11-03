# Project standard

Status: **v0 draft, standard version 1.** The rule list and labels exist in
[`src/autopilot/standard/checks.yaml`](src/autopilot/standard/checks.yaml). The engine that runs them
(`ap standard check`) is being built this week and isn't here yet, so everything below describes what the rules are,
not yet what runs.

This file says what a repo should have and how each rule is backed. It makes no claim that following it improves how
well agents work. Where a rule is judgment, it says so.

## How each rule is backed

| Label | Meaning | Can it fail a run? |
|---|---|---|
| `enforced` | CI or a ruleset blocks the change | Yes, and it blocks the merge |
| `audited` | `ap standard check` reports it when someone runs it | Yes, but nothing blocks a merge |
| `advisory` | Judgment, not enforced anywhere | No, it only warns |

**Nothing is `enforced` yet.** That label is reserved for a rule that a protected CI step actually runs. Until that
step exists, calling a rule enforced would be false, so none is. A test checks this and has to be removed on purpose
when the CI step lands.

A result is `pass`, `fail`, or `unknown`. `unknown` means the check couldn't be answered, for example because `gh`
isn't installed or the ruleset can't be read. It is never counted as a pass.

A rule's **level** says what a failing result does to the run: `fail` exits non-zero, `warn` prints. New rules start at
`warn` until the portfolio is clean, so adding a rule never breaks a repo overnight.

## The rules

| Rule | Level | Label | Applies to |
|---|---|---|---|
| `pinned-actions` | fail | audited | all |
| `workflow-permissions` | fail | audited | all |
| `no-privileged-triggers` | fail | audited | all |
| `secret-exposed-workflows` | fail | audited | all |
| `codeowners-cover-protected-paths` | fail | audited | all |
| `no-tracked-secrets` | fail | audited | all |
| `thin-claude-md` | warn | audited | all |
| `one-check-entrypoint` | warn | audited | all |
| `license-present` | warn | audited | public repos |
| `ruleset-present` | warn | audited | all |
| `agents-md-budget` | warn | advisory | all |
| `how-this-was-built` | warn | advisory | all |
| `journal-present` | warn | advisory | all |
| `dependency-updates` | warn | advisory | all |

Each rule's reason and fix are in `checks.yaml`, which is the single source. A test fails if this table and that file
disagree.

## Which repos a rule applies to

`applies_to` is derived from keys that already exist in `policy/portfolio.yaml` (`public`, `data_class`). There is no
separate "repo kind" field, and this standard doesn't read a product's stage: stage belongs to the bets ledger, and
reading it here would create a second policy file.

## Waivers

A repo that can't meet a rule yet needs a waiver. Waivers live in one central file, `policy/waivers.yaml`, keyed by
repo, with an owner and an expiry of at most 30 days. They are read from the base branch, so a pull request can't waive
its own failure, and an expired waiver fails. *Planned for Wednesday; the file doesn't exist yet.*

## What is measured and what isn't

- The rules marked `advisory` are judgment. Whether a short `AGENTS.md` helps an agent is unproven: one paper reports
  that context files don't generally improve task success, and I have only read its abstract.
- The 60-line figure is a starting value, not a measured threshold.
- Nothing here has been shown to raise first-pass success. Measuring that needs your own numbers, captured with
  `pow run`.

## Open decisions (owner)

1. **Tier numbering.** `specs/_TEMPLATE.md` numbers risk tiers 1, 2, 3 while `kit/runtime/tier.py` uses 0, 1, 2. This
   standard doesn't choose.
2. **Enforcement.** Making any rule `enforced` needs an owner edit to `.github/workflows/ci.yml` and `.autopilot/repo.yaml`.
3. **Rulesets on your plan.** Whether rulesets and code owners bind on private repos depends on the GitHub plan, which
   hasn't been checked. Run `gh api user --jq .plan.name`.

## Related

A product repo is either autopilot-managed or pawl-scaffolded, never both: the two disagree about who owns `.claude/`,
`.mcp.json`, and the list of protected paths.
