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

## Not verified
- How GitHub renders a template into a new repo (not tried until the repo exists).
- That regenerating the template is a step anyone remembers: `converge` is the backstop, not this.
