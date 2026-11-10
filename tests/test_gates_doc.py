"""docs/gates.md names real commands, flags and gates, so it cannot drift from the CLI it describes."""

import re
import subprocess
import sys
from pathlib import Path

from autopilot import gates

DOC = Path(__file__).resolve().parents[1] / "docs" / "gates.md"
TEXT = DOC.read_text(encoding="utf-8")


def help_of(*args):
    r = subprocess.run([sys.executable, "-m", "autopilot.cli", *args, "--help"], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r.stdout


def test_every_flag_the_doc_documents_exists_on_the_command_it_belongs_to():
    show, seed = help_of("gate", "show"), help_of("gate", "seed")
    for flag in ("--json", "--path", "--root", "--control"):
        assert flag in show, f"ap gate show has no {flag}"
        assert flag in TEXT, f"docs/gates.md does not mention {flag}"
    for flag in ("--apply", "--push", "--control"):
        assert flag in seed, f"ap gate seed has no {flag}"
        assert flag in TEXT, f"docs/gates.md does not mention {flag}"


def test_every_gate_the_doc_names_exists():
    named = set(re.findall(r"^- `(\w+)`:", TEXT, flags=re.M))
    assert named and named <= set(gates.load_gates()["gates"]), named


def test_the_doc_says_it_is_not_legal_or_tax_advice_and_that_steps_are_self_attested():
    assert "not legal or tax advice" in TEXT and "Self-attested" in TEXT


def test_every_item_kind_is_explained():
    for kind in gates.KINDS:
        assert f"`{kind}`" in TEXT, kind
