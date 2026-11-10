"""File contents the scaffolder can write. Tokens are `@@name@@`, not `{{name}}`, so they never collide with `${{ }}` in
GitHub Actions files. A token left unfilled is an error, never written."""

from __future__ import annotations

import re

TOKEN = re.compile(r"@@(\w+)@@")


def fill(text: str, **values: object) -> str:
    out = TOKEN.sub(lambda m: str(values[m.group(1)]) if m.group(1) in values else m.group(0), text)
    left = TOKEN.findall(out)
    if left:
        raise KeyError(f"unfilled template token(s): {', '.join(sorted(set(left)))}")
    return out


MIT = """MIT License

Copyright (c) @@year@@ @@holder@@

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

SECURITY = """# Security

Please report a suspected vulnerability privately through this repository's security advisory feature (Security tab,
"Report a vulnerability") instead of a public issue. Include what you found, how to reproduce it, and what you expect the
impact to be.

This is a personal project, so there is no response-time promise. Reports are read and acted on as time allows.
"""

CONTRIBUTING = """# Contributing

Thanks for helping. Small, focused pull requests are easiest to review.

## Before you open a pull request

1. Run the project's check and say in the description how you ran it and what it printed.
2. Do not include anything confidential, covered by an NDA, or private information about a person or company.
3. Disclose AI assistance in the pull request description if a model drafted any part of the change.

## Licensing of contributions

By submitting a contribution you agree it is licensed under this project's license (see `LICENSE`).
"""

PULL_REQUEST = """## What and why

Closes #

## How I checked it

Commands run and what they printed (paste the real output, not a summary):

```
```

## Risk and rollback

- Risk (what could break, and who would notice):
- Rollback (how to undo this, and how long that takes):
- Does it touch money, auth, data deletion or a migration? (yes / no; if yes, read those lines twice)

## Checklist

- [ ] The project's check passes locally
- [ ] Tests were added or changed for the new behaviour, and none were deleted, skipped or loosened to get green
- [ ] No secrets, credentials or private data in the diff
- [ ] AI assistance disclosed above if a model drafted any of this
"""

ISSUE_BUG = """---
name: Bug
about: Something does not work as described
labels: bug
---

## What happened

## What you expected

## How to reproduce

Exact commands or steps, and the version or commit.

## Environment

OS, language and tool versions.
"""

CODEOWNERS = """# Everything needs a human owner. Narrow this list as the repo grows.
* @@handle@@
"""

CHANGELOG = """# Changelog

All notable changes are recorded here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and versions follow [Semantic Versioning](https://semver.org/).

## [Unreleased]
"""

# Action pins were read from each repo's tags with `git ls-remote` on 2026-11-08; the comment names the tag. Tags can move,
# which is why the workflow pins the commit. Refresh them with Dependabot's github-actions entry, not by hand.
CHECKOUT = "actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4"
SETUP_UV = "astral-sh/setup-uv@68559e99cc807c1eb7e9238fd43a15bba460eec2 # v10.3.3"
UPLOAD = "actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9 # v7.0.2"
DOWNLOAD = "actions/download-artifact@9000827ccba6bdab643e8b6fd33ac0654aef8333 # v8.0.2"
PYPI_PUBLISH = "pypa/gh-action-pypi-publish@7245906fb61fa33a13554f9d5fb856fe61758086 # v1.14.3"

CI_UV = f"""name: ci
on:
  pull_request:
  push:
    branches: [main]
permissions:
  contents: read
jobs:
  test:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - uses: {CHECKOUT}
      - uses: {SETUP_UV}
      - run: uv sync --quiet
      - run: make check
"""

# For a new repo with no package: one dependency-free check, so every repo has a status check a ruleset can require. It is a real
# check (no key material or env files tracked), not a placeholder, and CI runs the same `make check` you run locally. The job id
# (`check`) is what the ruleset requires; core.required_check names it and a test pins that they agree.
CI_GENERIC = f"""name: ci
on:
  pull_request:
  push:
    branches: [main]
permissions:
  contents: read
jobs:
  check:
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - uses: {CHECKOUT}
      - run: make check
"""

# Trusted publishing (OIDC): no token is stored anywhere. `id-token: write` is on the publish job only, and that job waits
# for a human to approve the `pypi` Environment. An agent can push neither the tag nor the approval.
RELEASE_UV = f"""name: release
on:
  push:
    tags: ["v*"]
permissions:
  contents: read
jobs:
  build:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: {CHECKOUT}
      - uses: {SETUP_UV}
      - run: uv build
      - uses: {UPLOAD}
        with:
          name: dist
          path: dist/
  publish:
    needs: build
    runs-on: ubuntu-latest
    timeout-minutes: 10
    environment: pypi
    permissions:
      id-token: write
    steps:
      - uses: {DOWNLOAD}
        with:
          name: dist
          path: dist/
      - uses: {PYPI_PUBLISH}
"""

MAKEFILE = {
    "uv": ".PHONY: check\ncheck:\n\tuv run ruff check .\n\tuv run pytest -q\n",
    "pip": ".PHONY: check\ncheck:\n\truff check .\n\tpytest -q\n",
    "npm": ".PHONY: check\ncheck:\n\tnpm test\n",
    "cargo": ".PHONY: check\ncheck:\n\tcargo test\n",
    "gomod": ".PHONY: check\ncheck:\n\tgo test ./...\n",
}

# The generic check for a repo with no package. `$$` is make's escape for a literal `$`. The Makefile excludes itself from the
# key-material grep because the pattern text is in it. A test runs it with real make against a clean and a dirty repo.
TRACKED_SECRETS_BODY = (
    "\t@bad=$$(git ls-files | grep -E '(^|/)\\.env(\\.|$$)|\\.(pem|key|p12)$$|(^|/)id_(rsa|ed25519)' "
    "| grep -v -E '\\.(example|sample|template)$$' || true); \\\n"
    '\tif [ -n "$$bad" ]; then echo "tracked secret-like files:"; echo "$$bad"; exit 1; fi; \\\n'
    "\tif git grep -I -n -e 'BEGIN [A-Z ]*PRIVATE KEY' -- . ':!.github' ':!Makefile'; "
    'then echo "private key material is tracked"; exit 1; fi\n'
)
MAKEFILE_GENERIC = ".PHONY: check\ncheck:\n" + TRACKED_SECRETS_BODY

# --- the day-0 layer for a new repo --------------------------------------------------------------------------------------
# A git hook cannot be forced onto a clone, so a fresh clone has none until `make setup` runs. `setup` symlinks the hook into the
# repo's own .git/hooks, never changes the hooks path (the machine-wide dispatcher in ~/.gitconfig finds it there and forwards
# to it), and refuses to replace a real file someone put there. The hook runs `make quick`: lint plus a staged secret scan.
# `check` is the full set CI runs. A missing tool warns locally instead of failing, so a laptop without gitleaks is not blocked
# into using --no-verify; the secret scan is still wired and `make setup` says what is missing.
HOOK_PRE_COMMIT = """#!/usr/bin/env bash
# Runs before every commit. Install it in a clone with `make setup`.
set -euo pipefail
exec make --quiet quick
"""

_SETUP = (
    "setup:\n"
    '\t@h="$$(git rev-parse --git-common-dir)/hooks/pre-commit"; \\\n'
    '\tif [ -e "$$h" ] && [ ! -L "$$h" ]; then echo "$$h exists and is not a symlink; left alone"; exit 1; fi; \\\n'
    '\tln -sf ../../.githooks/pre-commit "$$h"; echo "installed $$h -> .githooks/pre-commit"\n'
    "\t@command -v gitleaks >/dev/null 2>&1 || echo 'WARN: gitleaks is not installed (brew install gitleaks): the secret scan is skipped'\n"
)
_STAGED_SECRETS = (
    "staged-secrets:\n"
    "\t@if command -v gitleaks >/dev/null 2>&1; then gitleaks git --staged --redact --no-banner; "
    "else echo 'WARN: gitleaks is not installed (brew install gitleaks): staged secret scan skipped'; fi\n"
)
# `if/else`, not `a && b || warn`: that form would report a missing tool when the tool ran and failed, and swallow the failure.
_WORKFLOW_LINT = (
    "workflow-lint:\n"
    "\t@if [ -d .github/workflows ]; then \\\n"
    "\t  if command -v actionlint >/dev/null 2>&1; then actionlint || exit 1; "
    "else echo 'WARN: actionlint is not installed (brew install actionlint): workflow lint skipped'; fi; \\\n"
    "\t  if command -v zizmor >/dev/null 2>&1; then zizmor .github/workflows || exit 1; "
    "else echo 'WARN: zizmor is not installed (brew install zizmor): workflow security lint skipped'; fi; \\\n"
    "\tfi\n"
)


def makefile_new(lint: str = "", test: str = "", audit: str = "") -> str:
    """The Makefile a brand-new repo gets: setup, quick (the hook), check (what CI runs), audit (slow, uses the network)."""
    quick = "quick: staged-secrets\n" + (f"\t{lint}\n" if lint else "")
    check = "check: quick tracked-secrets workflow-lint\n" + (f"\t{test}\n" if test else "")
    audit_body = (
        "audit:\n"
        "\t@if command -v gitleaks >/dev/null 2>&1; then gitleaks git --redact --no-banner; "
        "else echo 'WARN: gitleaks is not installed (brew install gitleaks): history scan skipped'; fi\n"
        + (f"\t{audit}\n" if audit else "")
    )
    return "\n".join(
        [
            ".PHONY: setup quick check audit staged-secrets tracked-secrets workflow-lint\n",
            _SETUP,
            quick,
            check,
            _STAGED_SECRETS,
            "tracked-secrets:\n" + TRACKED_SECRETS_BODY,
            _WORKFLOW_LINT,
            audit_body,
        ]
    )


EDITORCONFIG = """root = true

[*]
charset = utf-8
end_of_line = lf
insert_final_newline = true
trim_trailing_whitespace = true
indent_style = space
indent_size = 4

[*.{yml,yaml,json,toml,md}]
indent_size = 2

[Makefile]
indent_style = tab
"""

DECISIONS_README = """# Decisions

One short file per decision that someone would otherwise have to re-argue: `NNNN-title.md`, numbered in order and never
rewritten. If a decision changes, add a new file that says it supersedes the old one.

Five lines each:

- **Context**: what forced a choice.
- **Decision**: what was chosen.
- **Why**: the reason that mattered most.
- **Alternatives**: what was rejected, and why.
- **Date**: when it was decided.
"""

RUNBOOKS_README = """# Runbooks

One file per alert or recurring job: `<name>.md`. Write it for someone who has never seen the system and is reading it at 2 a.m.
(an agent counts):

- **What it means**: what is wrong and who feels it.
- **How to check**: the exact commands, and what a healthy answer looks like.
- **How to fix**: the exact steps, and how to undo them.
- **When to stop**: when to stop fixing and turn something off instead.
"""

JUSTFILE = {
    "uv": "# Run the tests\ntest:\n\tuv run pytest -q\n\n# Lint the code\nlint:\n\tuv run ruff check .\n",
    "pip": "# Run the tests\ntest:\n\tpytest -q\n\n# Lint the code\nlint:\n\truff check .\n",
    "npm": "# Run the tests\ntest:\n\tnpm test\n",
    "cargo": "# Run the tests\ntest:\n\tcargo test\n",
    "gomod": "# Run the tests\ntest:\n\tgo test ./...\n",
}

# .gitignore sections by language family. `results/` and `docs/` are deliberately never ignored.
GITIGNORE_BASE = ".DS_Store\n*.log\n.env\n.env.*\n!.env.example\n"
GITIGNORE = {
    "python": "__pycache__/\n*.py[cod]\n.venv/\n.pytest_cache/\n.ruff_cache/\n.mypy_cache/\nbuild/\ndist/\n*.egg-info/\n",
    "node": "node_modules/\ndist/\n.next/\ncoverage/\n",
    "rust": "target/\n",
    "go": "bin/\n",
}
FAMILY = {"uv": "python", "pip": "python", "npm": "node", "cargo": "rust", "gomod": "go"}


def gitignore(ecosystems: list[str]) -> str:
    out = ["# Generated by `ap standard fix`. Edit freely; it is never overwritten.\n", GITIGNORE_BASE]
    seen: list[str] = []
    for e in ecosystems:
        fam = FAMILY.get(e)
        if fam and fam not in seen:
            seen.append(fam)
            out.append(f"\n# {fam}\n{GITIGNORE[fam]}")
    return "".join(out)


def dependabot(ecosystems: list[str], has_workflows: bool) -> str:
    """One weekly update entry per detected ecosystem, plus github-actions when the repo has workflows. Values are
    Dependabot's `package-ecosystem` strings (`uv`, `pip`, `npm`, `cargo`, `gomod`, `docker`, `github-actions`)."""
    kinds = list(ecosystems) + (["github-actions"] if has_workflows else [])
    lines = ["version: 2", "updates:"]
    for k in kinds:
        lines += [f"  - package-ecosystem: {k}", '    directory: "/"', "    schedule: {interval: weekly}"]
        # A version a week old is far less likely to be a hijacked release. `default-days` is the one cooldown key every ecosystem
        # supports (github-actions takes no semver keys), and cooldown never delays security updates.
        lines += ["    cooldown: {default-days: 7}"]
        if k != "github-actions":  # one weekly pull request for the routine bumps, instead of one per package
            lines += ["    groups:", "      minor-and-patch:", '        patterns: ["*"]', "        update-types: [minor, patch]"]
    return "\n".join(lines) + "\n"


# --- new-package skeleton (written only into an empty directory) ---------------------------------------------------------


def pyproject(name: str, pkg: str, owner: str, holder: str | None, public: bool, cli: bool) -> str:
    """Package metadata. Fields nobody can know yet are TODO, never invented."""
    lines = [
        "[build-system]",
        'requires = ["hatchling>=1.27"]',
        'build-backend = "hatchling.build"',
        "",
        "[project]",
        f'name = "{name}"',
        'version = "0.1.0"',
        'description = "TODO: one sentence on what this does"',
        'readme = "README.md"',
        'requires-python = ">=3.11"',
    ]
    if public:
        lines += ['license = "MIT"', 'license-files = ["LICENSE"]']
    if holder:
        lines.append(f'authors = [{{ name = "{holder}" }}]')
    lines += [
        'classifiers = ["Programming Language :: Python :: 3", "Typing :: Typed"]',
        "",
        "[project.urls]",
        f'Homepage = "https://github.com/{owner}/{name}"',
        f'Issues = "https://github.com/{owner}/{name}/issues"',
    ]
    if cli:
        lines += ["", "[project.scripts]", f'{name} = "{pkg}:main"']
    lines += [
        "",
        "[tool.hatch.build.targets.wheel]",
        f'packages = ["src/{pkg}"]',
        "",
        "[dependency-groups]",
        'dev = ["pytest", "ruff"]',
        "",
    ]
    return "\n".join(lines)


def init_py(cli: bool) -> str:
    if not cli:
        return '"""TODO: one line on this package."""\n'
    return '"""TODO: one line on this package."""\n\n\ndef main() -> None:\n    print("hello")\n'


def smoke_test(pkg: str) -> str:
    return f"import {pkg}\n\n\ndef test_imports():\n    assert {pkg}.__doc__\n"


def readme(name: str) -> str:
    return (
        f"# {name}\n\nTODO: what this is, how to install it, one example.\n\n"
        "## How this was built\n\nTODO: say plainly how AI assistance was used, and keep it accurate.\n"
    )


def template_readme() -> str:
    """README for the generated template repo. Every new repo made from it starts with the heading the standard looks for."""
    return (
        "# TODO: name\n\nTODO: what this is, how to install it, one example.\n\n"
        "## How this was built\n\nTODO: say plainly how AI assistance was used, and keep it accurate.\n"
    )
