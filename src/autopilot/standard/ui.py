"""The `ui-no-vibe-tells` rule: scan a repo's UI source for the tells STANDARD.md's "UI and landing pages" section bans.

This is a pattern match over source text, so it finds what can be seen in source (fonts, icon packages, hex colors, utility classes,
em dashes) and cannot judge layout, copy quality or whether a testimonial is real. Those stay with the skill and the owner. A repo
with no UI source skips. Comments are stripped before the text rules run so a comment can't trip them.
"""

import colorsys
import re
from pathlib import Path

UI_EXT = {".css", ".scss", ".html", ".htm", ".tsx", ".jsx", ".vue", ".svelte", ".astro", ".mdx"}
SKIP_DIRS = {
    "node_modules",
    ".git",
    ".next",
    "dist",
    "build",
    "out",
    ".venv",
    "venv",
    "vendor",
    "coverage",
    ".turbo",
    ".vercel",
    "tests",
    "test",
    "__tests__",
    "fixtures",
    "docs",
    "examples",
    "templates",
    "storybook-static",
}
MAX_BYTES = 400_000
MAX_PER_CATEGORY = 3  # findings printed per category, so one bad file can't bury the rest

BLOCK_COMMENT = re.compile(r"/\*.*?\*/|<!--.*?-->", re.S)
LINE_COMMENT = re.compile(r"(?m)^\s*//.*$")

HEX = re.compile(r"#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b")
HSL = re.compile(r"hsla?\(\s*(-?[\d.]+)(?:deg)?[\s,]+([\d.]+)%[\s,]+([\d.]+)%")
FAMILIES = "red|orange|amber|yellow|lime|green|emerald|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose"
EMOJI = re.compile("[\U0001f300-\U0001faff☀-➿⭐⬆✅❌]")

# (category, regex, message). A match anywhere in a UI file is one finding.
TEXT_RULES: list[tuple[str, re.Pattern, str]] = [
    (
        "font",
        re.compile(r"font-family[^;{}]*\b(Inter|Geist|Space Grotesk)\b", re.I),
        "Inter, Geist or Space Grotesk as the typeface",
    ),
    (
        "font",
        re.compile(r"family=(Inter|Geist|Space\+Grotesk)\b", re.I),
        "Inter, Geist or Space Grotesk loaded from Google Fonts",
    ),
    (
        "font",
        re.compile(r"import\s*\{[^}]*\b(Inter|Geist|Geist_Mono|Space_Grotesk)\b[^}]*\}\s*from\s*['\"]next/font"),
        "Inter, Geist or Space Grotesk via next/font",
    ),
    ("font", re.compile(r"from\s*['\"]geist/font"), "the Geist font package"),
    ("icons", re.compile(r"""from\s*['"]lucide(-react|-vue-next|-svelte|-react-native)?['"]"""), "Lucide icons"),
    ("icons", re.compile(r"\bSparkles?\b\s*[,}]|<Sparkles?\b"), "a sparkle icon"),
    ("emdash", re.compile("—"), "an em dash (use a period, comma or colon)"),
    ("glyph", EMOJI, "an emoji, checkmark or sparkle glyph used as UI text"),
    ("glass", re.compile(r"backdrop-filter|\bbackdrop-blur"), "liquid glass (backdrop blur)"),
    ("gradient", re.compile(r"radial-gradient|\bbg-radial|bg-\[radial"), "a radial gradient (orbs, dot grids, glows)"),
    ("gradient", re.compile(r"bg-clip-text|background-clip:\s*text"), "gradient text"),
    ("gradient", re.compile(r"\b(from|via|to)-(purple|violet|indigo|fuchsia)-\d{2,3}"), "a purple/violet/indigo gradient stop"),
    ("stripe", re.compile(r"\bborder-l-(2|4|8)\b|border-left:\s*([3-9]|\d{2,})px\s+solid"), "a colored left stripe"),
    ("radius", re.compile(r"\brounded-(2xl|3xl)\b"), "a large soft corner radius"),
    ("shadow", re.compile(r"\bshadow-(lg|xl|2xl)\b"), "a large drop shadow"),
    (
        "motion",
        re.compile(r"\bhover:(scale|-?translate-y)|\banimate-bounce\b|group-hover:translate-x"),
        "a hover animation or animated arrow",
    ),
    (
        "grid",
        re.compile(r"\bgrid-cols-3\b|grid-template-columns:\s*repeat\(\s*3\b|\bbento\b", re.I),
        "a three-column grid or bento grid (three cards in a row)",
    ),
    (
        "copy",
        re.compile(
            r"\b(it['’]s|this is|that['’]s) not (a |an |just )?[^.,;!?\n<>{}]{1,40}[,.;]\s*(it['’]s|this is|that['’]s)\b", re.I
        ),
        "\"it's not X, it's Y\" phrasing",
    ),
    (
        "testimonial",
        re.compile(r"testimonial", re.I),
        "a testimonials block (the standard allows only real quotes with a name and a source)",
    ),
]
TEXT_RULES += [
    (
        "scroll",
        re.compile(r"data-aos|\bwhileInView\b|from\s*['\"]aos['\"]|scrollreveal|animate-on-scroll", re.I),
        "everything fades in on scroll",
    ),
    ("cursor", re.compile(r"\bmousemove\b|\bonMouseMove\b|\bpointermove\b|\bonPointerMove\b"), "a cursor-following effect"),
    (
        "buzzwords",
        re.compile(
            r"\b(seamless(ly)?|supercharge[sd]?|revolutioni[sz]e[sd]?|unlock the power|elevate your|cutting-edge|game-?chang(er|ing)"
            r"|next[- ]level|reimagine[sd]?|effortless(ly)?|all-in-one|empower(s|ing)?)\b",
            re.I,
        ),
        "generic buzzword copy",
    ),
    (
        "button",
        re.compile(
            r"<(button|a|Button|Link)\b[^>]*>\s*(learn more|get started|click here|submit|read more|sign up now|try it now|explore)\s*</",
            re.I,
        ),
        "a vague button label (say what happens: 'Start the free trial', 'Download the report')",
    ),
    (
        "placeholder",
        re.compile(
            r"lorem ipsum|\bjohn doe\b|\bjane doe\b|123 main st|\(555\)|\b555-\d{4}\b|\bacme (inc|corp)\b|\byour company\b"
            r"|company name|hello@company\.com|your@email\.com",
            re.I,
        ),
        "placeholder business info",
    ),
    (
        "keyboard",
        re.compile(r"<(div|span)\b(?![^>]*\brole=)[^>]*\bonClick="),
        "a clickable div or span with no role (not reachable by keyboard; use a button or link)",
    ),
    ("spacing", re.compile(r"\b(?:p|px|py|pt|pb|pl|pr|m|mx|my|mt|mb|ml|mr|gap|space-x|space-y)-\[\d+px\]"), "arbitrary pixel spacing (inconsistent spacing)"),
    (
        "shadcn",
        re.compile(r"--primary:\s*(222\.2 47\.4% 11\.2%|0 0% 9%|oklch\(0\.205 0 0\))"),
        "untouched shadcn/ui default theme (change the tokens to your own palette)",
    ),
    (
        "gradient",
        re.compile(r"\b(?:linear|conic)-gradient\([^;{}]*\b(purple|violet|indigo|fuchsia)\b", re.I),
        "a purple/violet gradient",
    ),
]
OUTLINE_NONE = re.compile(r"\boutline-none\b|outline:\s*(none|0)\b")
FORM = re.compile(r"<form\b.*?</form>", re.S | re.I)
FIELD = re.compile(r"<(input|textarea|select|Input|Textarea|Select)\b(?![^>]*type=[\"'](hidden|submit|checkbox|radio)[\"'])")
MAX_FIELDS = 5
RULE_BLOCK = re.compile(r"\{([^{}]*)\}")
TEXT_COLOR = re.compile(r"(?<![-\w])color\s*:\s*#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b")
BG_COLOR = re.compile(r"(?<![-\w])background(?:-color)?\s*:\s*#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b")
MIN_CONTRAST = 4.5  # WCAG AA for body text
GRADIENT_ARGS = re.compile(r"(?:linear|conic)-gradient\(([^;{}]*)")
PASTEL_CLASS = re.compile(rf"\b(bg|from|via|to)-({FAMILIES})-(100|200|300)\b")
WHITE_BODY_CLASS = re.compile(r"<(body|html)\b[^>]*\bbg-white\b")
WHITE_RULE = re.compile(r"(?:^|[}\s,])(html|body|:root|#root|#__next)\s*\{([^}]*)\}", re.S)
WHITE_VALUE = re.compile(r"background(?:-color)?\s*:\s*(#fff\b|#ffffff\b|white\b|rgb\(\s*255\s*,\s*255\s*,\s*255\s*\))", re.I)


def ui_files(root: Path):
    for p in sorted(root.rglob("*")):
        if p.suffix not in UI_EXT or not p.is_file() or ".min." in p.name:
            continue
        rel = p.relative_to(root)
        if any(part in SKIP_DIRS or part.startswith(".") for part in rel.parts[:-1]) or p.stat().st_size > MAX_BYTES:
            continue
        yield p, rel


def strip_comments(text: str) -> str:
    """Blank comments but keep every newline, so a reported line number still points at the right line."""
    text = BLOCK_COMMENT.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), text)
    return LINE_COMMENT.sub("", text)


def is_pastel(r: int, g: int, b: int) -> bool:
    """High lightness with real saturation: a tint, not a grey, an off-white or a saturated brand color. Warm paper tones are allowed."""
    h, light, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
    if not (0.72 <= light <= 0.95 and s >= 0.40):
        return False
    return not (20 <= h * 360 <= 60 and light >= 0.90)  # cream and paper, not a pastel yellow


def pastel_colors(text: str) -> list[str]:
    found = []
    for m in HEX.finditer(text):
        v = m.group(1)
        v = "".join(c * 2 for c in v) if len(v) == 3 else v
        if is_pastel(int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16)):
            found.append(m.group(0))
    for m in HSL.finditer(text):
        h, s, light = float(m.group(1)) % 360, float(m.group(2)) / 100, float(m.group(3)) / 100
        r, g, b = colorsys.hls_to_rgb(h / 360, light, s)
        if is_pastel(round(r * 255), round(g * 255), round(b * 255)):
            found.append(m.group(0))
    return found


def hex_rgb(v: str) -> tuple[int, int, int]:
    v = "".join(c * 2 for c in v) if len(v) == 3 else v
    return int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16)


def luminance(rgb: tuple[int, int, int]) -> float:
    def lin(c: int) -> float:
        c = c / 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (lin(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def blue_purple(hexv: str) -> bool:
    h, light, s = colorsys.rgb_to_hls(*(c / 255 for c in hex_rgb(hexv)))
    return 235 <= h * 360 <= 320 and s >= 0.40 and 0.15 <= light <= 0.85


def scan_text(text: str) -> list[tuple[str, int, str]]:
    """(category, line, message) for every tell in one file's text."""
    text = strip_comments(text)
    out: list[tuple[str, int, str]] = []

    def line_of(pos: int) -> int:
        return text.count("\n", 0, pos) + 1

    for cat, rx, msg in TEXT_RULES:
        for m in rx.finditer(text):
            out.append((cat, line_of(m.start()), msg))
    for m in PASTEL_CLASS.finditer(text):
        out.append(("pastel", line_of(m.start()), f"a pastel color class ({m.group(0)})"))
    for m in HEX.finditer(text):
        if pastel_colors(m.group(0)):
            out.append(("pastel", line_of(m.start()), f"a pastel color ({m.group(0)})"))
    for m in HSL.finditer(text):
        if pastel_colors(m.group(0)):
            out.append(("pastel", line_of(m.start()), f"a pastel color ({m.group(0)})"))
    for m in WHITE_BODY_CLASS.finditer(text):
        out.append(("white", line_of(m.start()), "a pure white page background (bg-white on the page root)"))
    for m in WHITE_RULE.finditer(text):
        if WHITE_VALUE.search(m.group(2)):
            out.append(("white", line_of(m.start(1)), f"a pure white page background ({m.group(1)})"))
    for m in OUTLINE_NONE.finditer(text):
        line = text[text.rfind("\n", 0, m.start()) + 1 : text.find("\n", m.end()) if "\n" in text[m.end() :] else len(text)]
        if "focus" not in line and "ring" not in line:
            out.append(("keyboard", line_of(m.start()), "focus outline removed with no focus style (keyboard users lose their place)"))
    for m in FORM.finditer(text):
        n = len(FIELD.findall(m.group(0)))
        if n > MAX_FIELDS:
            out.append(("form", line_of(m.start()), f"a form with {n} fields (more than {MAX_FIELDS}: ask only for what you need)"))
    for m in RULE_BLOCK.finditer(text):
        fg, bg = TEXT_COLOR.search(m.group(1)), BG_COLOR.search(m.group(1))
        if fg and bg:
            ratio = contrast(hex_rgb(fg.group(1)), hex_rgb(bg.group(1)))
            if ratio < MIN_CONTRAST:
                out.append(("contrast", line_of(m.start()), f"low contrast text ({ratio:.1f}:1, needs {MIN_CONTRAST}:1)"))
    for m in GRADIENT_ARGS.finditer(text):
        if any(blue_purple(h) for h in re.findall(r"#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b", m.group(1))):
            out.append(("gradient", line_of(m.start()), "a purple or blue-to-purple gradient"))
    return out


def asks_for_email(texts: list[str]) -> bool:
    return any(re.search(r"type\s*=\s*[\"'](email|password)[\"']", t) for t in texts)


def has_policy_pages(root: Path) -> tuple[bool, bool]:
    names = [
        str(p.relative_to(root)).lower()
        for p in root.rglob("*")
        if p.is_file() and not any(x in SKIP_DIRS for x in p.relative_to(root).parts[:-1])
    ]
    return any("privacy" in n for n in names), any(re.search(r"terms|tos\b", n) for n in names)


def scan(root: Path) -> tuple[bool, list[str]]:
    """(had_ui, findings). Findings are capped per category and say how many more there were."""
    by_cat: dict[str, list[str]] = {}
    texts: list[str] = []
    seen = False
    for p, rel in ui_files(root):
        seen = True
        text = p.read_text(encoding="utf-8", errors="replace")
        texts.append(text)
        for cat, line, msg in scan_text(text):
            by_cat.setdefault(cat, []).append(f"{rel}:{line}: {msg}")
    pkg = root / "package.json"
    if pkg.is_file() and re.search(r'"lucide(-react|-vue-next|-svelte)?"\s*:', pkg.read_text(encoding="utf-8", errors="replace")):
        seen = True
        by_cat.setdefault("icons", []).append("package.json: depends on Lucide icons")
    if not seen:
        return False, []
    if asks_for_email(texts):
        privacy, terms = has_policy_pages(root)
        for ok, what in ((privacy, "privacy policy"), (terms, "terms of service")):
            if not ok:
                by_cat.setdefault("policy", []).append(f"the UI collects an email or password but no {what} file or route was found")
    findings = []
    for cat in sorted(by_cat):
        items = by_cat[cat]
        findings += items[:MAX_PER_CATEGORY]
        if len(items) > MAX_PER_CATEGORY:
            findings.append(f"({cat}: {len(items) - MAX_PER_CATEGORY} more)")
    return True, findings
