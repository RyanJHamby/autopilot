"""`ui-no-vibe-tells`: each banned tell has a failing fixture, clean UI passes, and comments, tests and non-UI repos are left alone."""

import pytest

from autopilot.standard import engine, load_checks, ui


def run(root):
    (r,) = engine.run(engine.Repo(root, force_new=True), only=["ui-no-vibe-tells"])
    return r.result, r.findings


def put(root, rel, text):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


CLEAN = """<body style="background:#f4efe6;color:#1a1a1a"><h1>Ledger</h1><p>Track orders. Ship faster.</p>
<style>body{font-family:"Newsreader",serif;border-radius:4px}.cta{background:#1d3557;color:#f4efe6}</style></body>"""


def test_a_repo_with_no_ui_skips(tmp_path):
    put(tmp_path, "main.py", "print('hi')")
    assert run(tmp_path)[0] == "skip"


def test_clean_ui_passes(tmp_path):
    put(tmp_path, "index.html", CLEAN)
    assert run(tmp_path) == ("pass", [])


@pytest.mark.parametrize(
    "rel,text,word",
    [
        ("a.css", "body{font-family: Inter, sans-serif}", "typeface"),
        ("a.tsx", "import { Geist } from 'next/font/google'", "next/font"),
        ("a.tsx", "import { Menu } from 'lucide-react'", "Lucide"),
        ("a.html", "<p>Fast — and simple</p>", "em dash"),
        ("a.html", "<li>✓ Included</li>", "glyph"),
        ("a.html", "<h1>Launch \U0001f680</h1>", "glyph"),
        ("a.css", ".card{backdrop-filter: blur(8px)}", "glass"),
        ("a.css", ".hero{background: radial-gradient(circle, #123, #456)}", "radial"),
        ("a.tsx", "<div className='bg-gradient-to-r from-purple-500 to-pink-500'/>", "purple"),
        ("a.tsx", "<div className='border-l-4 border-blue-600'/>", "left stripe"),
        ("a.tsx", "<div className='rounded-3xl shadow-2xl'/>", "radius"),
        ("a.tsx", "<div className='hover:scale-105'/>", "hover"),
        ("a.tsx", "<div className='grid md:grid-cols-3'/>", "three-column"),
        ("a.html", "<p>It's not a tool, it's a movement.</p>", "it's not X"),
        ("a.tsx", "<Testimonials />", "testimonials"),
        ("a.css", "body{background:#fff}", "pure white"),
        ("a.tsx", "<body className='bg-white'>", "pure white"),
        ("a.css", ".tag{background:#bfdbfe}", "pastel"),
        ("a.css", ".tag{background:hsl(210, 90%, 85%)}", "pastel"),
        ("a.tsx", "<div className='bg-pink-200'/>", "pastel"),
        ("a.tsx", "<div data-aos='fade-up'/>", "fades in on scroll"),
        ("a.tsx", "<motion.div whileInView={{opacity:1}}/>", "fades in on scroll"),
        ("a.tsx", "window.addEventListener('mousemove', f)", "cursor-following"),
        ("a.html", "<p>Seamless, effortless workflows.</p>", "buzzword"),
        ("a.html", "<button>Get started</button>", "vague button"),
        ("a.tsx", "<Button>Learn more</Button>", "vague button"),
        ("a.html", "<p>Lorem ipsum dolor</p>", "placeholder"),
        ("a.html", "<p>Call (555) 123-4567</p>", "placeholder"),
        ("a.tsx", "<div onClick={go}>Go</div>", "no role"),
        ("a.css", "input{outline: none}", "focus outline"),
        ("a.tsx", "<div className='p-[13px]'/>", "arbitrary pixel spacing"),
        ("a.css", ":root{--primary: 222.2 47.4% 11.2%}", "shadcn"),
        ("a.css", ".hero{background: linear-gradient(90deg, #4f46e5, #7c3aed)}", "purple"),
        ("a.css", ".hero{background: linear-gradient(90deg, #2563eb, #9333ea)}", "purple"),
        ("a.css", ".t{color:#777777;background:#888888}", "low contrast"),
        ("a.html", "<form>" + "<input>" * 6 + "</form>", "6 fields"),
    ],
)
def test_each_tell_fails_and_names_the_file_and_line(tmp_path, rel, text, word):
    put(tmp_path, rel, "\n" + text)
    result, findings = run(tmp_path)
    assert result == "fail", findings
    assert any(rel in f and ":2:" in f and word.lower() in f.lower() for f in findings), findings


def test_lucide_in_package_json_fails(tmp_path):
    put(tmp_path, "index.html", CLEAN)
    put(tmp_path, "package.json", '{"dependencies": {"lucide-react": "^0.4"}}')
    assert run(tmp_path)[0] == "fail"


def test_an_email_field_without_policy_pages_fails_and_with_them_passes(tmp_path):
    put(tmp_path, "index.html", CLEAN + '<label for="e">Email</label><input id="e" type="email">')
    assert run(tmp_path)[0] == "fail"
    put(tmp_path, "privacy.html", CLEAN)
    put(tmp_path, "terms.html", CLEAN)
    assert run(tmp_path)[0] == "pass"


def test_comments_tests_and_node_modules_are_ignored(tmp_path):
    put(tmp_path, "index.html", CLEAN + "<!-- Inter — lucide-react ✓ -->")
    put(tmp_path, "a.css", "/* font-family: Inter; background:#bfdbfe */ .x{color:#111}")
    put(tmp_path, "tests/bad.html", "<p>—</p>")
    put(tmp_path, "node_modules/x/bad.css", "body{font-family:Inter}")
    assert run(tmp_path) == ("pass", [])


@pytest.mark.parametrize("color", ["#faf8f5", "#f4efe6", "#f5ecd9", "#1d3557", "#e5e5e5", "#c0392b", "#0b0b0f"])
def test_off_whites_greys_paper_and_saturated_colors_are_not_pastel(color):
    assert ui.pastel_colors(f"x{{color:{color}}}") == []


@pytest.mark.parametrize("color", ["#bfdbfe", "#aec6ff", "#ffd1dc", "#b5ead7", "#e6e6fa"])
def test_known_pastels_are_found(color):
    assert ui.pastel_colors(f"x{{color:{color}}}") == [color]


def test_findings_are_capped_per_category_with_a_count_of_the_rest(tmp_path):
    put(tmp_path, "a.html", "".join(f"<p>a — b {i}</p>\n" for i in range(10)))
    _, findings = run(tmp_path)
    assert len(findings) == ui.MAX_PER_CATEGORY + 1 and "7 more" in findings[-1]


def test_the_rule_is_fail_level_enforced_and_dated_so_old_repos_only_warn():
    rule = {c["id"]: c for c in load_checks()["checks"]}["ui-no-vibe-tells"]
    assert (rule["level"], rule["label"], str(rule["since"])) == ("fail", "enforced", "2026-11-11")


def test_limit_a_pattern_cannot_see_layout_or_whether_a_demo_is_real(tmp_path):
    """Known blind spot, recorded so it stays visible: a vibe-coded layout with clean source passes."""
    put(tmp_path, "index.html", CLEAN + "<section><div>Card</div><div>Card</div><div>Card</div></section>")
    assert run(tmp_path)[0] == "pass"


def test_hidden_directories_such_as_claude_worktrees_are_not_scanned(tmp_path):
    put(tmp_path, "index.html", CLEAN)
    put(tmp_path, ".claude/worktrees/x/bad.html", "<p>—</p>")
    assert run(tmp_path) == ("pass", [])


def test_a_dark_theme_with_enough_contrast_passes(tmp_path):
    put(tmp_path, "index.html", CLEAN + "<style>.t{color:#f4efe6;background:#14110f}</style>")
    assert run(tmp_path) == ("pass", [])


def test_a_focus_style_on_the_same_line_a_small_form_and_a_specific_button_pass(tmp_path):
    put(
        tmp_path,
        "index.html",
        CLEAN
        + "\n<style>input:focus-visible{outline:none;box-shadow:0 0 0 2px #1d3557}</style>\n"
        + "<form>"
        + "".join(f'<label for="f{i}">F</label><input id="f{i}">' for i in range(5))
        + "<button>Download the report</button></form>",
    )
    assert run(tmp_path) == ("pass", [])


def test_a_password_field_needs_policy_pages_too(tmp_path):
    put(tmp_path, "index.html", CLEAN + '<label for="p">Password</label><input id="p" type="password">')
    assert run(tmp_path)[0] == "fail"


@pytest.mark.parametrize(
    "rel,text,word",
    [
        ("a.css", ".dot{background:#ff5f56}", "terminal"),
        ("a.html", "<span class='badge'>New in 2026</span>\n<h1>Ledger</h1>", "badge"),
        ("a.html", "<p>Trusted by thousands of teams</p>", "unproven"),
        ("a.html", "<p>Up to 40% faster</p>", "unproven"),
        ("a.tsx", "<CheckIcon />", "checkmark icon"),
        ("a.html", "<iframe src='https://x.test/map'></iframe>", "no title"),
        ("a.html", "<img src='http://x.test/a.png'>", "http://"),
        ("a.html", "<input name='q'>", "label hook"),
        ("a.css", ".c{border-radius: 24px}", "corner radius"),
        ("a.css", ".c{box-shadow: 0 20px 60px rgba(0,0,0,.3)}", "blurred drop shadow"),
        ("a.css", ".c:hover{transform: translateY(-2px)}", "hover animation"),
        ("a.css", ".h{color:#00ff66}", "neon"),
        ("a.css", ".h{color:#ff00ff}", "neon"),
        ("a.css", ".b{background:#6d28d9}", "purple"),
        ("a.css", ".h{background:linear-gradient(90deg,#ff0000,#00cc00,#0000ff)}", "rainbow"),
        ("a.css", ".h{background:linear-gradient(90deg,#d62828,#1d9bf0)}", "harsh gradient"),
        ("a.html", "<h2>Starter</h2><h2>Pro</h2><h2>Enterprise</h2>", "pricing tiers"),
        ("a.html", "<p>Our revolutionary, innovative platform</p>", "buzzword"),
        ("a.html", "<p>Sarah Johnson, CEO</p>", "placeholder"),
    ],
)
def test_each_audit_gap_is_now_caught(tmp_path, rel, text, word):
    put(tmp_path, rel, "\n" + text)
    result, findings = run(tmp_path)
    assert result == "fail", findings
    assert any(rel in f and word.lower() in f.lower() for f in findings), findings


def test_a_spinner_with_no_skeleton_fails_and_with_one_passes(tmp_path):
    put(tmp_path, "index.html", CLEAN + "<div class='animate-spin'></div>")
    result, findings = run(tmp_path)
    assert result == "fail" and any("skeleton" in f for f in findings)
    put(tmp_path, "b.html", "<div class='skeleton'></div>")
    assert run(tmp_path)[0] == "pass"


def test_pricing_or_checkout_words_need_policy_pages(tmp_path):
    put(tmp_path, "index.html", CLEAN + "<a href='/checkout'>Checkout</a>")
    assert any("terms" in f for f in run(tmp_path)[1])


@pytest.mark.parametrize(
    "css",
    [
        ".a{color:#22c55e}",  # an ordinary green, not neon
        ".a{color:#c0392b;background:#f4efe6}",
        ".a{border-radius:8px;box-shadow:0 1px 2px rgba(0,0,0,.2)}",
        ".a{background:linear-gradient(180deg,#f4efe6,#e9dfcf)}",  # same-hue gradient
        ".a{background:linear-gradient(90deg,#1d3557,#457b9d)}",  # two nearby blues
        ".a:hover{color:#1d3557}",
        ".a{color:#1d3557}",
    ],
)
def test_ordinary_css_is_not_flagged_by_the_new_rules(tmp_path, css):
    put(tmp_path, "a.css", css)
    put(tmp_path, "index.html", CLEAN)
    assert run(tmp_path) == ("pass", [])


def test_line_numbers_stay_right_when_blank_lines_precede_a_comment(tmp_path):
    put(tmp_path, "a.tsx", "const a = 1\n\n\n// a comment\nconst b = <p>x \u2014 y</p>\n")
    _, findings = run(tmp_path)
    assert any("a.tsx:5:" in f for f in findings), findings
