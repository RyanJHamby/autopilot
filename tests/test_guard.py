import guard
from guard import FileChange, analyze, parse_diff


def checks(vs):
    return {v.check for v in vs}


def test_clean_diff_passes():
    ch = [FileChange("src/a.py", added=["def f():", "    return 1"]), FileChange("tests/test_a.py", added=["def test_f():", "    assert f() == 1"])]
    assert analyze(ch, agent=True) == []


def test_secrets_flagged_for_everyone():
    ch = [FileChange("src/a.py", added=['KEY = "AKIAABCDEFGHIJKLMNOP"'])]
    assert "secret" in checks(analyze(ch, agent=False))
    ch = [FileChange("x.md", added=["ghp_" + "a" * 30])]
    assert "secret" in checks(analyze(ch, agent=False))
    ch = [FileChange("x.txt", added=["-----BEGIN OPENSSH PRIVATE KEY-----"])]
    assert "secret" in checks(analyze(ch, agent=False))


def test_comms_surfaces_flagged():
    for line in ["import smtplib", "from slack_sdk import WebClient", "url = 'https://hooks.slack.com/services/T/B/x'",
                 "import tweepy", "from googleapiclient.discovery import build", "requests.post('https://api.linkedin.com/v2/ugcPosts')",
                 "twilio.rest.Client()", "run: npm publish", "https://api.todoist.com/rest/v2/tasks"]:
        assert "comms" in checks(analyze([FileChange("src/x.py", added=[line])], agent=False)), line


def test_comms_allowlist_is_per_path():
    ch = [FileChange("tools/notify.py", added=["import smtplib"])]
    assert analyze(ch, agent=False, comms_allow=["tools/**"]) == []
    assert "comms" in checks(analyze(ch, agent=False, comms_allow=["other/**"]))


def test_protected_paths_only_for_agents():
    ch = [FileChange(".github/workflows/x.yml", added=["on: push"])]
    assert "protected-path" in checks(analyze(ch, agent=True))
    assert analyze(ch, agent=False) == []
    for p in [".autopilot/repo.yaml", ".claude/settings.json", "AGENTS.md", "CLAUDE.md", ".mcp.json", "CODEOWNERS"]:
        assert "protected-path" in checks(analyze([FileChange(p, added=["x"])], agent=True)), p


def test_mcp_config_blocked_for_agents():
    assert "mcp-config" in checks(analyze([FileChange("sub/.mcp.json", added=["{}"])], agent=True))


def test_test_weakening_and_deletion():
    ch = [FileChange("tests/test_a.py", removed=["    assert a == 1", "    assert b == 2", "    assert c", "    assert d", "def test_x():"])]
    assert "test-weakening" in checks(analyze(ch, agent=True))
    assert "test-deletion" in checks(analyze([FileChange("tests/test_a.py", status="D")], agent=True))
    ok = [FileChange("tests/test_a.py", removed=["    assert a == 1"], added=["    assert a == 2"])]
    assert analyze(ok, agent=True) == []


def test_size_cap_only_for_agents():
    big = [FileChange("src/a.py", added=["x = 1"] * 900)]
    assert "size" in checks(analyze(big, agent=True))
    assert "size" not in checks(analyze(big, agent=False))
    assert "size" not in checks(analyze(big, agent=True, max_diff_lines=1000))


def test_parse_diff_roundtrip():
    text = (
        "diff --git a/src/a.py b/src/a.py\nindex 1..2 100644\n--- a/src/a.py\n+++ b/src/a.py\n@@ -1 +1 @@\n-old\n+new\n"
        "diff --git a/tests/test_a.py b/tests/test_a.py\ndeleted file mode 100644\nindex 3..0\n--- a/tests/test_a.py\n+++ /dev/null\n@@ -1 +0,0 @@\n-assert 1\n"
        "diff --git a/n.txt b/n.txt\nnew file mode 100644\n--- /dev/null\n+++ b/n.txt\n@@ -0,0 +1 @@\n+hi\n"
    )
    chs = {c.path: c for c in parse_diff(text)}
    assert chs["src/a.py"].added == ["new"] and chs["src/a.py"].removed == ["old"]
    assert chs["tests/test_a.py"].status == "D"
    assert chs["n.txt"].status == "A"


def test_main_against_real_git_repo(tmp_path, monkeypatch):
    import subprocess
    def g(*a):
        subprocess.run(["git", "-c", "commit.gpgsign=false", "-c", "user.email=t@t", "-c", "user.name=t", *a], cwd=tmp_path, check=True, capture_output=True)
    g("init", "-q", "-b", "main")
    (tmp_path / "a.py").write_text("x = 1\n")
    g("add", "."); g("commit", "-qm", "base")
    g("checkout", "-qb", "agent/1-x")
    (tmp_path / "a.py").write_text("import smtplib\n")
    g("commit", "-qam", "bad")
    monkeypatch.chdir(tmp_path)
    assert guard.main(["--base", "main", "--agent", "true", "--config", "none.yaml"]) == 1
