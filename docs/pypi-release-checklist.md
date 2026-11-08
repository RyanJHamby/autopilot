# Publishing a package to PyPI (owner checklist)

`ap standard fix` writes `.github/workflows/release.yml` for public library and cli repos that use uv. It only
*builds and publishes when a `v*` tag is pushed and a human approves*. Everything below is owner-only: agents never
publish (see `.autopilot/CONSTITUTION.md`). Do these once per package, in order.

Sources: <https://docs.pypi.org/trusted-publishers/> and <https://docs.pypi.org/trusted-publishers/using-a-publisher/>.

## Before the first release
1. **Pick the name and check it is free**: open `https://pypi.org/project/NAME/`. A 404 means it is available (a name
   can still be taken between that check and your first upload).
2. **Fill in `pyproject.toml`**: `name`, `version`, `description`, `readme`, `license`, `authors`, `requires-python`,
   `[project.urls]`, and `[project.scripts]` for a cli. Run `uv build` locally and open the wheel to check it.
3. **Reserve the name with a pending publisher** (no upload needed): on pypi.org go to *Your account, Publishing,
   Add a new pending publisher* and enter owner `RyanJHamby`, the repo name, workflow `release.yml`, environment `pypi`.
4. **Create the GitHub Environment** `pypi` (repo Settings, Environments). Add yourself as a required reviewer so a
   publish waits for your approval.
5. **Restrict who can create `v*` tags** (repo Settings, Rules, a tag ruleset): only you. A stray tag then cannot start a
   release.
6. **Dry run on TestPyPI first.** It is a separate account and a separate pending publisher on test.pypi.org. Copy
   `release.yml`, point the publish step at `repository-url: https://test.pypi.org/legacy/`, push a tag on a scratch
   branch, and confirm the upload. Remove the override afterwards.

## Each release
1. Move the `CHANGELOG.md` entries from Unreleased to the new version and bump `version` in `pyproject.toml`.
2. Merge that through a PR as usual, then `git tag -s vX.Y.Z && git push origin vX.Y.Z` yourself.
3. Approve the `pypi` Environment deployment when GitHub asks.
4. Check `https://pypi.org/project/NAME/` shows the version, then `uvx NAME --help` or `pip install NAME` in a clean
   environment.

## What is and is not verified
- The workflow's shape matches the PyPI documentation: `id-token: write` on the publish job only, `environment: pypi`,
  `pypa/gh-action-pypi-publish` pinned to a commit.
- **Not verified:** that any real publish has succeeded. Until step 6 above passes, treat the template as untested.
- Tags can be moved, so the workflow pins action commits; Dependabot's `github-actions` entry proposes updates.
