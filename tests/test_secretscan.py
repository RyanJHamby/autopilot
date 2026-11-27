import subprocess

import pytest
import secretscan
from guard import FileChange, parse_diff
from secretscan import Finding, UsageError, is_env_file, parse_allowlist, scan

# Every fake secret is assembled at runtime from pieces, so no secret-shaped literal exists in this file (the scanner,
# the guard and GitHub push protection would otherwise flag the test itself).
A16 = "ABCDEFGHIJKLMNOP"
FAKES = {
    "aws-access-key-id": ["AK" + "IA" + A16, "AS" + "IA" + A16[::-1]],
    "github-token": [
        "gh" + "p_" + "a1" * 18,
        "gh" + "s_" + "Z9" * 18,
        "github" + "_pat_" + "B" * 22 + "_" + "c" * 59,
    ],
    "anthropic-key": ["sk-" + "ant-" + "api03-" + "x" * 40],
    "openai-key": ["sk-" + "proj-" + "Q" * 48, "sk-" + "m" * 48],
    "slack-token": ["xo" + "xb-" + "123456789012-" + "abcdefghijKLMN"],
    "google-api-key": ["AI" + "za" + "S" * 35],
    "private-key": ["-----BEGIN " + "RSA PRIVATE" + " KEY-----", "-----BEGIN " + "PRIVATE" + " KEY-----"],
    "stripe-live": ["sk" + "_live_" + "4" * 24, "rk" + "_live_" + "r" * 30],
    "huggingface-token": ["h" + "f_" + "T" * 34],
}


def rules(findings):
    return {f.rule for f in findings}


@pytest.mark.parametrize("rule,value", [(r, v) for r, vs in FAKES.items() for v in vs])
def test_each_rule_flags_its_shape(rule, value):
    ch = FileChange("src/config.py", added=["x = 1", f'KEY = "{value}"'], added_at=[10, 11])
    assert scan([ch]) == [Finding("src/config.py", rule, 11)]


@pytest.mark.parametrize(
    "line",
    [
        "AKIA is the AWS prefix",
        "ghp_short",
        "sk-ant-short",
        "sk-" + "m" * 20,
        "AIza" + "S" * 10,
        "-----BEGIN PUBLIC KEY-----",
        "sk_test_" + "4" * 24,
        "hf_" + "T" * 10,
        "sha256: " + "a" * 64,
        "xoxb-",
    ],
)
def test_near_misses_are_not_flagged(line):
    assert scan([FileChange("a.txt", added=[line], added_at=[1])]) == []


def test_removed_lines_are_ignored():
    ch = FileChange("src/a.py", added=["x = 1"], removed=[FAKES["aws-access-key-id"][0]], added_at=[3])
    assert scan([ch]) == []


def test_parse_diff_line_numbers_and_only_added_lines():
    key = FAKES["github-token"][0]
    diff = "\n".join(
        [
            "diff --git a/app.py b/app.py",
            "--- a/app.py",
            "+++ b/app.py",
            "@@ -5 +5,2 @@",
            f"-old = '{key}'",
            "+new = 1",
            f"+tok = '{key}'",
        ]
    )
    assert [str(f) for f in scan(parse_diff(diff))] == ["app.py:6: github-token"]


def test_env_file_rule_and_exceptions():
    for p in [".env", "svc/.env", ".env.local", "deploy/.env.production"]:
        assert is_env_file(p), p
        assert rules(scan([FileChange(p, status="A")])) == {"env-file"}, p
    for p in [".env.example", "svc/.env.sample", ".env.template", "env.txt", "my.env", ".envrc", "docs/.environment"]:
        assert not is_env_file(p), p
        assert scan([FileChange(p, status="A", added=["A=1"], added_at=[1])]) == [], p
    assert scan([FileChange(".env", status="M", added=["A=1"], added_at=[1])]) == []  # file rule is for added files


def test_allowlist_glob_matching():
    aws = FAKES["aws-access-key-id"][0]
    chs = [
        FileChange("tests/fixtures/keys.txt", added=[aws], added_at=[1]),
        FileChange("src/app.py", added=[aws], added_at=[2]),
        FileChange("examples/.env", status="A"),
    ]
    allow = parse_allowlist("# known fixtures\n\ntests/fixtures/**:aws-access-key-id\nexamples/*:env-file  # sample\n")
    assert [str(f) for f in scan(chs, allow)] == ["src/app.py:2: aws-access-key-id"]
    # the rule id must match too: allowing a path for one rule does not hide another rule there
    other = parse_allowlist("tests/fixtures/**:github-token")
    assert rules(scan(chs[:1], other)) == {"aws-access-key-id"}


@pytest.mark.parametrize("bad", ["no-colon-here", ":aws-access-key-id", "src/**:not-a-rule", "src/**:"])
def test_malformed_allowlist_names_the_line(bad):
    with pytest.raises(UsageError, match="line 3"):
        parse_allowlist(f"# header\nok/**:private-key\n{bad}\n")


def test_missing_allowlist_is_empty(tmp_path):
    assert secretscan.load_allowlist(str(tmp_path / "nope.txt")) == []


# ---- end to end through the CLI on a throwaway repo ----


def _git(repo, *a):
    return subprocess.run(["git", "-C", str(repo), *a], check=True, capture_output=True, text=True).stdout


@pytest.fixture()
def repo(tmp_path):
    r = tmp_path / "r"
    r.mkdir()
    _git(r, "init", "-q", "-b", "main")
    _git(r, "config", "user.email", "t@example.invalid")
    _git(r, "config", "user.name", "t")
    _git(r, "config", "commit.gpgsign", "false")  # throwaway test repo only
    (r / "README.md").write_text("hi\n")
    _git(r, "add", ".")
    _git(r, "commit", "-qm", "base")
    _git(r, "checkout", "-qb", "feature")
    return r


def _commit(repo, files):
    for rel, text in files.items():
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "change")


def _run(repo, monkeypatch, *extra):
    monkeypatch.chdir(repo)
    return secretscan.main(["--base", "main", "--head", "HEAD", *extra])


def test_cli_clean_exits_0(repo, monkeypatch, capsys):
    _commit(repo, {"src/a.py": "print('hello')\n"})
    assert _run(repo, monkeypatch) == 0
    assert "clean" in capsys.readouterr().out


def test_cli_findings_exit_1_and_never_print_the_value(repo, monkeypatch, capsys):
    values = [v for vs in FAKES.values() for v in vs]
    _commit(repo, {"src/keys.py": "".join(f"k{i} = '{v}'\n" for i, v in enumerate(values)), ".env": "X=1\n"})
    assert _run(repo, monkeypatch) == 1
    cap = capsys.readouterr()
    out = cap.out + cap.err
    for v in values:
        assert v not in out
        assert v[8:] not in out  # not even a tail of it
    assert "src/keys.py:1: aws-access-key-id" in out
    assert ".env: env-file" in out
    assert set(FAKES) <= {ln.rsplit(": ", 1)[-1] for ln in out.splitlines() if ln.startswith("  src/keys.py:")}


def test_cli_removed_secret_is_clean(repo, monkeypatch):
    _git(repo, "checkout", "-q", "main")
    _commit(repo, {"old.py": f"k = '{FAKES['huggingface-token'][0]}'\n"})
    _git(repo, "checkout", "-qb", "cleanup")
    _commit(repo, {"old.py": "k = None\n"})
    assert _run(repo, monkeypatch) == 0


def test_cli_allowlist_and_usage_errors(repo, monkeypatch, tmp_path, capsys):
    _commit(repo, {"tests/fx.txt": FAKES["google-api-key"][0] + "\n"})
    assert _run(repo, monkeypatch) == 1
    allow = tmp_path / "allow.txt"
    allow.write_text("tests/*:google-api-key\n")
    assert _run(repo, monkeypatch, "--allowlist", str(allow)) == 0
    allow.write_text("tests/*\n")
    capsys.readouterr()
    assert _run(repo, monkeypatch, "--allowlist", str(allow)) == 2
    assert "line 1" in capsys.readouterr().err
    assert _run(repo, monkeypatch, "--allowlist", str(tmp_path / "missing.txt")) == 1
    monkeypatch.chdir(repo)
    assert secretscan.main(["--base", "no-such-ref"]) == 2
    with pytest.raises(SystemExit) as e:
        secretscan.main([])
    assert e.value.code == 2
