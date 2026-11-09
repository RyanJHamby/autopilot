set shell := ["bash", "-c"]

# run the test suite
test:
	uv run pytest -q

# lint with ruff
lint:
	uv run ruff check src tests

# index of specs/: status, issue, handshake verdict
specs:
	uv run ap specs

# runs and agent PRs per enabled repo
status:
	uv run ap status

# run the project standard against a repo path: just standard ~/dev/foo
standard repo:
	uv run ap standard check {{repo}} --offline
