# A template repo for new projects: `ap standard template`

GitHub cannot force files onto a new personal repo, so a template covers creation and `ap standard converge` covers whatever slipped
through. See `docs/standard-converge.md` for the second half.

## What it is
`ap standard template OUT_DIR` renders the generic hygiene layer into a new, empty directory: LICENSE, SECURITY.md, CONTRIBUTING.md,
CODEOWNERS, the PR and bug issue templates, `.gitignore`, a Dependabot config for GitHub Actions, and a README stub with the
"How this was built" heading.

It leaves out anything that needs a per-repo value: `pyproject.toml`, `src/<pkg>`, Makefile, justfile, CI, release, CHANGELOG.
Those come from `ap standard fix --kind ...` (existing repos) or `ap new` (new ones).

The files are `core.plan`'s output for a synthetic public repo, not a second copy, so the template cannot drift from the
scaffolder. `tests/test_standard_template.py` pins the exact file list and runs the standard's rules over the result.

Two rules still fail on a fresh template, on purpose: `journal-present` (run `pow init` in the new repo) and `thin-claude-md`
(`AGENTS.md` and `CLAUDE.md` come per repo).

## Publish it (owner steps; nothing here is done for you)
Creating a repo is outward-facing, so it is a script you run and read first:
```
bash <path to>/owner_create_repo_template.sh   # run from the autopilot root; it asks before it creates anything
```
It renders the template, commits it signed, creates `OWNER/repo-template` as a **private** repo, and marks it a template.
A private template works for its owner; the public-only files in it are harmless in a private repo.

Use it: `gh repo create NAME --private --template OWNER/repo-template`, or "Use this template" on GitHub.
Regenerate after the scaffolder changes: render into a fresh directory, diff against the template repo, commit there.

## Starting a project with the right shape: `ap new`
The template cannot know the package name or kind, so `ap new NAME --kind library|cli|app|notes [--public]` does the per-repo part
locally: `mkdir`, `git init -b main`, and the files `ap standard fix` would write (a package skeleton, CI and release for a
library or cli; the generic layer for an app or notes). It makes no commit, creates nothing on GitHub and pushes nothing. It prints
your steps: `pow init`, a signed commit, `gh repo create`, then the portfolio entry and ruleset. The only rules still failing
afterwards are `journal-present` and `thin-claude-md`, which `pow init` and `AGENTS.md` cover. Private is the default; `--public`
adds LICENSE, SECURITY and CONTRIBUTING and needs a holder.

Every new repo has a status check a ruleset can require: a library or cli reports the `test` job, and an app or notes repo gets a
Makefile `check` (no tracked env or key material) and a CI job named `check` that runs it. `core.required_check` names the job, and
a test pins it to the generated workflow, because a required check that never reports blocks every merge. The template itself
carries no CI: it serves repos of every kind, so a repo made from the template button has no check to require, and the admin doctor
flags it. Use `ap new` for new repos.

### `--create`: the whole way, owner-run
`ap new NAME --kind K [--public] --create` also makes the signed first commit, runs `gh repo create --push` (private unless
`--public`), applies the `autopilot-main` ruleset with only that repo's own CI job required (never autopilot's `guard`, which a repo
that is not autopilot-managed does not have), then reads the ruleset back from GitHub and fails if it is narrower than asked. It
checks before touching anything outward that commit signing is on and that the required job exists in the generated workflow. If a
step fails it says exactly what now exists (for example "EXISTS BUT IS UNPROTECTED" with the fix command). Run it yourself: agents
are denied `gh`. It was tested with a fake `gh`, not against real GitHub. On a free GitHub plan, rulesets are not available on private
repos, so the ruleset step fails there and the message says so. For an existing repo use `ap ruleset REPO --standalone --check JOB --apply`.
The admin doctor discovers repos from GitHub, so nothing needs registering for a repo to be audited.

## Not verified
- How GitHub renders a template into a new repo (not tried until the repo exists).
- That regenerating the template is a step anyone remembers: `converge` is the backstop, not this.
