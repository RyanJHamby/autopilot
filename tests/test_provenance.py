import json
from pathlib import Path

import pytest

from autopilot import cli
from autopilot import provenance as prov

CLI_TEXT = Path(cli.__file__).read_text()
PINS, README = prov.extract_constants(CLI_TEXT)
SRC_REPO, KIT_REPO = "me/autopilot", "me/autopilot-kit"
C, KIT_SHA, PREV = "c" * 40, "d" * 40, "1" * 40

WORKFLOWS = {"exec.yml": b"uses: actions/checkout@{{CHECKOUT_SHA}}\nnode: {{SETUP_NODE_SHA}}\nact: {{ACTION_SHA}}\n"}
RUNTIME = {"guard.py": b"print('guard')\n", "gate.py": b"print('gate')\n"}


def tree_json(files, truncated=False):
    """files: path -> (mode, bytes); blob shas are real git ids."""
    entries = [{"path": p, "mode": m, "type": "blob", "sha": prov.blob_sha(b)} for p, (m, b) in files.items()]
    entries.append({"path": "runtime", "mode": "040000", "type": "tree", "sha": "0" * 40})
    return json.dumps({"truncated": truncated, "tree": entries}).encode()


class World:
    """A fake GitHub: serves trees, blobs and compare answers. Records every URL asked."""

    def __init__(self, cli_text=CLI_TEXT, kit_edit=None, compare=None, truncated=False):
        self.asked: list[str] = []
        src = {CLI_PATH: ("100644", cli_text.encode())}
        src.update({f"kit/workflows/{n}": ("100644", b) for n, b in WORKFLOWS.items()})
        src.update({f"kit/runtime/{n}": ("100644", b) for n, b in RUNTIME.items()})
        src["kit/runtime/sub/skipped.py"] = ("100644", b"not a direct child\n")
        pins, readme = prov.extract_constants(cli_text) if cli_text else (PINS, README)
        rendered = prov.render_kit(readme, WORKFLOWS, RUNTIME, pins)
        kit = {p: ("100644", b) for p, b in rendered.items()}
        if kit_edit:
            kit_edit(kit)
        self.routes: dict[str, tuple[int, bytes]] = {
            f"{prov.API}/repos/{SRC_REPO}/git/trees/{C}?recursive=1": (200, tree_json(src)),
            f"{prov.API}/repos/{KIT_REPO}/git/trees/{KIT_SHA}?recursive=1": (200, tree_json(kit, truncated)),
        }
        for _p, (_m, b) in src.items():
            self.routes[f"{prov.API}/repos/{SRC_REPO}/git/blobs/{prov.blob_sha(b)}"] = (200, b)
        status = {"main": "ahead", PREV: "ahead"}
        status.update(compare or {})
        self.routes[f"{prov.API}/repos/{SRC_REPO}/compare/{C}...main?per_page=1"] = (
            200,
            json.dumps({"status": status["main"]}).encode(),
        )
        self.routes[f"{prov.API}/repos/{SRC_REPO}/compare/{PREV}...{C}?per_page=1"] = (
            200,
            json.dumps({"status": status[PREV]}).encode(),
        )

    def __call__(self, url):
        self.asked.append(url)
        return self.routes.get(url, (404, b""))


CLI_PATH = prov.CLI_PATH


def run(world=None, pins=None, previous=None, **kw):
    world = world or World()
    return prov.verify_provenance(
        KIT_REPO, KIT_SHA, kw.pop("source", C), pins or PINS, previous_source=previous, opener=world, **kw
    )


def test_exact_export_verifies_and_only_reads():
    w = World()
    assert run(w) == []
    assert all(u.startswith(prov.API) for u in w.asked)


def test_one_changed_byte_fails():
    def edit(kit):
        m, b = kit["runtime/guard.py"]
        kit["runtime/guard.py"] = (m, b[:-2] + b"X\n")

    out = run(World(kit_edit=edit))
    assert out and "runtime/guard.py" in out[0]


def test_extra_file_fails():
    out = run(World(kit_edit=lambda k: k.update({"evil.txt": ("100644", b"x")})))
    assert out and "extra in kit: evil.txt" in out[0]


def test_missing_file_fails():
    out = run(World(kit_edit=lambda k: k.pop("runtime/gate.py")))
    assert out and "missing from kit: runtime/gate.py" in out[0]


def test_executable_mode_fails():
    def edit(kit):
        kit["runtime/gate.py"] = ("100755", kit["runtime/gate.py"][1])

    out = run(World(kit_edit=edit))
    assert out and "runtime/gate.py" in out[0]


def test_pin_differs_from_approved_pins_fails():
    out = run(pins={**PINS, "ACTION_SHA": "f" * 40})
    assert out and "pins differ" in out[0]


def test_changed_export_source_fails_closed():
    out = run(World(cli_text=CLI_TEXT.replace('subs = {"CHECKOUT_SHA"', 'subs = {"EXTRA": "x", "CHECKOUT_SHA"')))
    assert out and "not a known export format" in out[0]


def test_known_hash_matches_this_checkouts_export_code():
    # fails when export_kit/render change: update render_kit to match, then add the new hash to KNOWN_EXPORT_HASHES
    assert prov.export_hash(CLI_TEXT) in prov.KNOWN_EXPORT_HASHES


@pytest.mark.parametrize("missing", ["ACTION_SHA", "KIT_README"])
def test_missing_constant_fails(missing):
    with pytest.raises(prov.ProvenanceError, match=missing):
        prov.extract_constants(CLI_TEXT.replace(f"{missing} = ", f"{missing}_RENAMED = ", 1))


def test_non_hex_pin_fails():
    bad = CLI_TEXT.replace(PINS["ACTION_SHA"], "v1")
    with pytest.raises(prov.ProvenanceError, match="ACTION_SHA"):
        prov.extract_constants(bad)


def test_source_hint_missing_or_malformed_fails():
    good = f"{KIT_SHA}  ok source={C}\n"
    assert prov.parse_source_hint(good, KIT_SHA) == C
    for text in (f"{KIT_SHA}  ok\n", f"{KIT_SHA}  source=abc\n", f"{KIT_SHA} source={C} source={C}\n", "", good + good):
        with pytest.raises(prov.ProvenanceError):
            prov.parse_source_hint(text, KIT_SHA)


def test_source_not_on_main_fails_in_both_bad_directions():
    # compare/{C}...main: 'ahead' = main is ahead of C (C is an ancestor); 'identical' = C is the tip
    assert run(World(compare={"main": "identical"})) == []
    for status in ("diverged", "behind"):  # behind = main is an ancestor of C, i.e. C is NOT on main
        out = run(World(compare={"main": status}))
        assert out and "not reachable" in out[0]


def test_rollback_fails():
    assert run(World(), previous=PREV) == []
    for status in ("behind", "diverged"):
        out = run(World(compare={PREV: status}), previous=PREV)
        assert out and "rollback" in out[0]


def test_truncated_tree_fails():
    out = run(World(truncated=True))
    assert out and "truncated" in out[0]


@pytest.mark.parametrize("status", [404, 500])
def test_http_errors_fail(status):
    w = World()
    key = f"{prov.API}/repos/{KIT_REPO}/git/trees/{KIT_SHA}?recursive=1"
    w.routes[key] = (status, b"")
    out = run(w)
    assert out and str(status) in out[0]


def test_invalid_json_fails():
    w = World()
    w.routes[f"{prov.API}/repos/{KIT_REPO}/git/trees/{KIT_SHA}?recursive=1"] = (200, b"not json")
    out = run(w)
    assert out and "invalid JSON" in out[0]


def test_blob_bytes_not_matching_tree_sha_fails():
    w = World()
    for url, (st, _b) in list(w.routes.items()):
        if "/git/blobs/" in url and prov.blob_sha(b"print('gate')\n") in url:
            w.routes[url] = (st, b"tampered")
    out = run(w)
    assert out and "do not hash" in out[0]


def test_forbidden_content_in_render_fails():
    with pytest.raises(prov.ProvenanceError, match="forbidden"):
        prov.render_kit("r", {}, {"bad.py": b"# /Users/someone/x\n"}, PINS)


def test_crlf_input_fails():
    with pytest.raises(prov.ProvenanceError, match="carriage return"):
        prov.render_kit("r", {"a.yml": b"a\r\n"}, {}, PINS)


def test_bad_shas_fail_before_any_request():
    w = World()
    assert prov.verify_provenance(KIT_REPO, KIT_SHA, "main", PINS, opener=w)
    assert w.asked == []


def test_opener_is_bound_at_call_time(monkeypatch):
    seen = []
    monkeypatch.setattr(prov, "_default_opener", lambda u: seen.append(u) or (404, b""))
    assert prov.verify_provenance(KIT_REPO, KIT_SHA, C, PINS)
    assert seen


# --- APPROVED diff ---------------------------------------------------------------------------------------------------

OLD = f"# header\n{'a' * 40}  first\n"


def test_approved_diff_accepts_added_hex_lines_only():
    assert prov.verify_approved_diff(OLD, OLD + f"{'b' * 40}  note source={C}\n") == []
    assert prov.verify_approved_diff(OLD, OLD + f"{'b' * 40}\n") == []
    assert prov.verify_approved_diff("", f"{'b' * 40}\n") == []


@pytest.mark.parametrize(
    "new",
    [
        OLD + "not-hex  note\n",
        OLD + f"{'B' * 40}  upper\n",
        OLD + f"{'b' * 39}\n",
        OLD + "# a comment\n",
        OLD + "\n\n",
        f"# header\n{'a' * 40}  CHANGED\n",
        f"{'a' * 40}  first\n",  # header removed
        OLD + f"{'a' * 40}  again\n",  # re-adding an approved sha
        OLD + f"{'b' * 40}  tab\there\n",
        OLD + f"{'b' * 40}  x\r\n",
    ],
)
def test_approved_diff_rejects_everything_else(new):
    assert prov.verify_approved_diff(OLD, new)


# --- hygiene and agreement with the real exporter ---------------------------------------------------------------------


def test_module_never_uses_graphql_or_check_rollups():
    code = Path(prov.__file__).read_text()
    for banned in ("graphql", "statusCheckRollup", "gh pr view", "import subprocess", "import yaml"):
        assert banned not in code
    assert "datetime" not in code and "time.time" not in code


def test_verifier_render_agrees_with_cli_export_kit(tmp_path, monkeypatch):
    kit = tmp_path / "kit"
    (kit / "workflows").mkdir(parents=True)
    (kit / "runtime").mkdir()
    for n, b in WORKFLOWS.items():
        (kit / "workflows" / n).write_bytes(b)
    for n, b in RUNTIME.items():
        (kit / "runtime" / n).write_bytes(b)
    monkeypatch.setattr(cli, "KIT", kit)  # main's export_kit has no kit-root argument
    out = tmp_path / "out"
    cli.export_kit(out)
    exported = {p.relative_to(out).as_posix(): p.read_bytes() for p in out.rglob("*") if p.is_file()}
    mine = prov.render_kit(README, WORKFLOWS, RUNTIME, PINS)
    assert {p: prov.blob_sha(b) for p, b in exported.items()} == {p: prov.blob_sha(b) for p, b in mine.items()}
    assert mine[".github/workflows/exec.yml"].count(PINS["ACTION_SHA"].encode()) == 1
