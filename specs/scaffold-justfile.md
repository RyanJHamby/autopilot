---
id: scaffold-justfile
goal: "`ap standard fix` offers a stub `justfile` (rule id `commands-documented`) to any repo that has neither a justfile nor an AGENTS.md `## Commands` section, so every repo has run/test commands a catalog can index."
acceptance:
  - uv run pytest tests/test_scaffold_justfile.py
  - uv run pytest -q tests/test_scaffold.py
  - uv run ruff check .
scope:
  - src/autopilot/scaffold/core.py
  - src/autopilot/scaffold/templates.py
  - tests/test_scaffold_justfile.py
non_goals:
  - do not edit src/autopilot/standard/** or checks.yaml (protected; the owner adds the `commands-documented` warn rule by hand)
  - do not touch STANDARD.md
  - do not change any existing Item or existing test in tests/test_scaffold.py
  - no new dependencies; do not require `just` to be installed
risk_tier: 2
max_runs: 3
autonomy: inherit
---

Why: the private `devbook` repo generates a one-line-per-project index from each repo's `justfile` (recipe names plus `#` doc comments) and
its `AGENTS.md` `## Commands` section. Repos with neither show up as gaps. This spec makes the scaffolder able to fill the gap. It is the
autopilot half of making every repo feed devbook; the catalog itself is specced in the devbook repo.

What to build (copy the style of the existing `Makefile` item):
- `Ctx.has_commands: bool = False`, set in `read_ctx` when `AGENTS.md` has a line matching `^## Commands\b`.
- `templates.JUSTFILE`: dict keyed like `MAKEFILE` (`uv`, `pip`, `npm`, `cargo`, `gomod`). Each body starts with a `# ` doc comment, then a
  `test:` recipe (first recipe in the file), then, for `uv`/`pip` only, a documented `lint:` recipe. Commands match the `MAKEFILE` entries
  (e.g. `uv run pytest -q`). Recipes are indented with a tab.
- `core.ITEMS`: `Item("justfile", "commands-documented", <render>, <applies>)`. `applies` returns `("skip", "AGENTS.md already has a ## Commands section")`
  when `has_commands`, and `("skip", "no known ecosystem to write commands for")` when no ecosystem in `JUSTFILE` is detected. It is NOT public-only:
  private repos get it. Existing `justfile` is handled by `_present`; no alias needed beyond `Justfile`.
- Add `"commands-documented"` to `PROPOSED_RULES`, with the existing comment explaining why.

First step: remove the `pytestmark = pytest.mark.xfail(strict=True, ...)` line (and its comment) from `tests/test_scaffold_justfile.py`. That is the
only change allowed to that file; never weaken an assertion. With the marker gone the file fails until the feature exists, then passes.

Check `tests/test_scaffold.py::test_every_item_names_a_rule_that_exists_or_is_proposed` and the round-trip test still pass; they should, since
the id is proposed and not in checks.yaml.

Owner follow-up (not for the agent): add `commands-documented` as a `warn` rule in `checks.yaml`/`engine.py`/`STANDARD.md`, then move the id out of
`PROPOSED_RULES`.

## Log
- 2026-11-08 draft; failing test written first (12 fail without the xfail marker: no justfile item exists)
