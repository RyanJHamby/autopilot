import sys
import textwrap

import pytest


@pytest.fixture(autouse=True)
def _clean_git_env(monkeypatch):
    """git sets GIT_DIR, GIT_INDEX_FILE etc. for hooks (pre-push runs this suite); tests that make their own repos must not inherit them."""
    for name in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY", "GIT_COMMON_DIR", "GIT_PREFIX"):
        monkeypatch.delenv(name, raising=False)


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
