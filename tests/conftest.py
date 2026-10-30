import sys
import textwrap

import pytest

# Variables git exports to hooks (pre-push runs this suite) that point every git command at the CHECKOUT being pushed. Tests build
# their own throwaway repos, so they must not inherit them: otherwise `git -C tmp ...` operates on the real repo and fails, and
# `git config user.email` in a test writes into the real repo's shared config.
_GIT_REPO_VARS = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR", "GIT_PREFIX", "GIT_OBJECT_DIRECTORY")


@pytest.fixture(autouse=True)
def _isolate_from_hook_git_env(monkeypatch):
    for v in _GIT_REPO_VARS:
        monkeypatch.delenv(v, raising=False)


@pytest.fixture()
def fake_sudo(tmp_path):
    """A stand-in for sudo: records its argv, drops the environment except PATH and --preserve-env names (like env_reset), runs the rest."""
    log = tmp_path / "sudo.log"
    f = tmp_path / "sudo"
    f.write_text(
        "#!"
        + sys.executable
        + "\n"
        + textwrap.dedent(
            f"""
            import json, os, sys
            args = sys.argv[1:]
            open({str(log)!r}, "a").write(json.dumps(args) + "\\n")
            keep, user = [], None
            while args:
                a = args.pop(0)
                if a == "-n":
                    continue
                if a == "-u":
                    user = args.pop(0)
                    continue
                if a.startswith("--preserve-env="):
                    keep = a.split("=", 1)[1].split(",")
                    continue
                if a == "--":
                    break
            env = {{"PATH": "/usr/bin:/bin"}}
            env.update({{k: os.environ[k] for k in keep if k in os.environ}})
            os.execvpe(args[0], args, env)
            """
        )
    )
    f.chmod(0o755)
    return str(f), log
