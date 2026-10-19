"""provenance_ci: the pure PR check and its REST fetchers, driven by fakes. Nothing here touches the network."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from autopilot import provenance as prov
from autopilot import provenance_ci as ci

K1, K2, K3 = "1" * 40, "2" * 40, "3" * 40
S1, S2, S3 = "a" * 40, "b" * 40, "c" * 40
HEADER = "# Kit shas the owner approved.\n"
PINS = {"CHECKOUT_SHA": "d" * 40, "SETUP_NODE_SHA": "e" * 40, "ACTION_SHA": "f" * 40}


@pytest.fixture
def verify(monkeypatch):
    """Replace the network-heavy verifier; record how it was called. Set .result to make it fail."""

    class V:
        calls: list[dict] = []
        result: list[str] = []

    v = V()
    v.calls = []

    def fake(kit_repo, kit_sha, source_sha, pins, *, previous_source=None, source_repo=None, opener=None, **_):
        v.calls.append({"kit": kit_sha, "source": source_sha, "previous": previous_source, "repo": kit_repo})
        return list(v.result)

    monkeypatch.setattr(prov, "verify_provenance", fake)
    return v


def check(base, head, files=("APPROVED",)):
    return ci.check_pr(base, head, list(files), PINS, "me/autopilot-kit", "me/autopilot")


def test_one_valid_added_line_passes(verify):
    base = HEADER + f"{K1}  old source={S1}\n"
    head = base + f"{K2}  new source={S2}\n"
    assert check(base, head) == []
    assert verify.calls == [
        {"kit": K2, "source": S2, "previous": S1, "repo": "me/autopilot-kit"}
    ]  # previous = newest base source


def test_previous_is_none_when_base_has_no_source_hints(verify):
    base = HEADER + f"{K1}  legacy approval\n"
    assert check(base, base + f"{K2}  new source={S2}\n") == []
    assert verify.calls[0]["previous"] is None


def test_two_added_lines_chain_their_sources(verify):
    base = HEADER + f"{K1}  old source={S1}\n"
    assert check(base, base + f"{K2}  a source={S2}\n{K3}  b source={S3}\n") == []
    assert [c["previous"] for c in verify.calls] == [S1, S2]


@pytest.mark.parametrize(
    "files", [["APPROVED", ".github/workflows/provenance.yml"], ["CODEOWNERS"], [], ["APPROVED", "APPROVED"] + ["x"]]
)
def test_any_other_changed_file_fails(verify, files):
    base = HEADER
    out = check(base, base + f"{K1}  n source={S1}\n", files)
    assert out and "only APPROVED" in out[0]
    assert verify.calls == []


def test_removed_or_changed_line_fails(verify):
    base = HEADER + f"{K1}  old source={S1}\n"
    assert check(base, HEADER) != []  # removed
    assert check(base, HEADER + f"{K1}  edited source={S1}\n") != []  # changed
    assert verify.calls == []


def test_added_comment_or_non_hex_line_fails(verify):
    base = HEADER
    assert check(base, base + "# sneaky\n") != []
    assert check(base, base + "not-a-sha source=" + S1 + "\n") != []


def test_zero_added_lines_fails(verify):
    base = HEADER + f"{K1}  old source={S1}\n"
    assert any("no approval line" in p for p in check(base, base))


@pytest.mark.parametrize(
    "note",
    ["no hint", f"source={S1} source={S2}", "source=zzz", f"source={S1[:39]}"],
)
def test_missing_duplicate_or_malformed_source_fails(verify, note):
    base = HEADER
    out = check(base, base + f"{K1}  {note}\n")
    assert out and out[0].startswith(K1[:7])
    assert verify.calls == []


def test_provenance_failure_propagates_with_the_kit_sha(verify):
    verify.result = ["kit tree differs from the render"]
    out = check(HEADER, HEADER + f"{K1}  n source={S1}\n")
    assert out == [f"{K1[:7]}: kit tree differs from the render"]


def test_re_adding_an_approved_sha_fails(verify):
    base = HEADER + f"{K1}  old source={S1}\n"
    assert check(base, base + f"{K1}  again source={S2}\n") != []


# --- fetchers -----------------------------------------------------------------------------------------------------------


def files_opener(pages):
    seen = []

    def opener(url):
        seen.append(url)
        n = int(url.rsplit("page=", 1)[1])
        return 200, json.dumps(pages[n - 1] if n <= len(pages) else []).encode()

    opener.seen = seen
    return opener


def test_changed_files_paginates_and_lists_renames():
    p1 = [{"filename": f"f{i}"} for i in range(100)]
    p2 = [{"filename": "APPROVED"}, {"filename": "new", "previous_filename": "old"}]
    out = ci.changed_files(files_opener([p1, p2]), "me/autopilot-approved", 7)
    assert len(out) == 103 and "old" in out and "APPROVED" in out


def test_changed_files_fails_closed():
    with pytest.raises(prov.ProvenanceError):
        ci.changed_files(lambda u: (500, b""), "me/r", 1)
    with pytest.raises(prov.ProvenanceError):
        ci.changed_files(lambda u: (200, b"not json"), "me/r", 1)
    with pytest.raises(prov.ProvenanceError):
        ci.changed_files(lambda u: (200, b'{"filename": "x"}'), "me/r", 1)  # not a list
    with pytest.raises(prov.ProvenanceError):
        ci.changed_files(lambda u: (200, b'[{"nope": 1}]'), "me/r", 1)


def test_changed_files_at_the_api_limit_is_treated_as_truncated():
    page = [{"filename": "f"}] * 100
    with pytest.raises(prov.ProvenanceError, match="truncated"):
        ci.changed_files(lambda u: (200, json.dumps(page).encode()), "me/r", 1)


def test_head_approved_validates_inputs_and_fetches_data_only():
    seen = []
    ok = ci.head_approved(lambda u: seen.append(u) or (200, b"text"), "me/fork", "a" * 40)
    assert ok == "text" and seen == [f"{prov.API}/repos/me/fork/contents/APPROVED?ref={'a' * 40}"]
    for repo, sha in (("bad repo", "a" * 40), ("me/r", "main"), ("", "a" * 40)):
        with pytest.raises(prov.ProvenanceError):
            ci.head_approved(lambda u: (200, b"x"), repo, sha)
    with pytest.raises(prov.ProvenanceError):
        ci.head_approved(lambda u: (404, b""), "me/r", "a" * 40)


# --- main() -------------------------------------------------------------------------------------------------------------


def run_main(tmp_path, monkeypatch, verify_result, *, files=("APPROVED",), approved_head=None, status=200):
    base = HEADER + f"{K1}  old source={S1}\n"
    (tmp_path / "APPROVED").write_text(base)
    (tmp_path / "pins.json").write_text(json.dumps(PINS))
    event = {"pull_request": {"number": 5, "head": {"sha": "9" * 40, "repo": {"full_name": "me/autopilot-approved"}}}}
    (tmp_path / "event.json").write_text(json.dumps(event))
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(tmp_path / "event.json"))
    monkeypatch.setenv("GITHUB_REPOSITORY", "me/autopilot-approved")
    head = approved_head if approved_head is not None else base + f"{K2}  n source={S2}\n"

    def opener(url):
        if "/pulls/5/files" in url:
            return 200, json.dumps([{"filename": f} for f in files]).encode()
        if "/contents/APPROVED" in url:
            return status, head.encode()
        raise AssertionError(url)

    prov_calls = []
    monkeypatch.setattr(prov, "verify_provenance", lambda *a, **k: prov_calls.append((a, k)) or list(verify_result))
    code = ci.main(["--pins", str(tmp_path / "pins.json"), "--approved", str(tmp_path / "APPROVED")], opener=opener)
    return code, prov_calls


def test_main_passes_and_derives_repos_from_the_owner(tmp_path, monkeypatch, capsys):
    code, calls = run_main(tmp_path, monkeypatch, [])
    assert code == 0 and "PASS" in capsys.readouterr().out
    args, kw = calls[0]
    assert args[0] == "me/autopilot-kit" and kw["source_repo"] == "me/autopilot" and kw["previous_source"] == S1


def test_main_fails_when_provenance_fails(tmp_path, monkeypatch, capsys):
    assert run_main(tmp_path, monkeypatch, ["nope"])[0] == 1
    assert "FAIL" in capsys.readouterr().err


def test_main_fails_when_another_file_changed(tmp_path, monkeypatch):
    code, calls = run_main(tmp_path, monkeypatch, [], files=("APPROVED", ".github/workflows/provenance.yml"))
    assert code == 1 and calls == []  # never reaches the verifier


def test_main_fails_when_head_approved_is_unreachable(tmp_path, monkeypatch):
    code, calls = run_main(tmp_path, monkeypatch, [], status=500)
    assert code == 1 and calls == []


def test_main_fails_closed_on_a_broken_event(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(tmp_path / "missing.json"))
    monkeypatch.setenv("GITHUB_REPOSITORY", "me/autopilot-approved")
    (tmp_path / "pins.json").write_text("{}")
    assert ci.main(["--pins", str(tmp_path / "pins.json")], opener=lambda u: (200, b"[]")) == 1


# --- hygiene ------------------------------------------------------------------------------------------------------------


def test_module_has_no_network_shell_or_graphql():
    text = (Path(__file__).parent.parent / "src/autopilot/provenance_ci.py").read_text()
    for banned in ("subprocess", "os.system", "graphql", "statusCheckRollup", "gh pr view", "yaml", "eval(", "exec("):
        assert banned not in text, banned
