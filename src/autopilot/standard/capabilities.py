"""What a repo can do, read from its own content: payments, an LLM, auth, a database, a deployment. Offline, no network.

A capability is evidence that the repo does the thing, not a mention of it. The scoping is the whole difficulty, and every rule here exists
because a real repo tripped it (surveyed 2026-11-10): an employer called Stripe in a CSV, a dependency that is only an optional extra, env
names in docs and workflow templates, copies of other repos under `examples/` and `data/template/`, worktree clones. So:

- Dependencies come from runtime sections of manifests only (never devDependencies, optional extras or lockfiles).
- Source signals are read from code files only, never docs, tests, fixtures, templates, examples, agent config or vendored/build output,
  with comments stripped, because a comment that says "previously called api.openai.com" is history, not a capability.
- The signals include raw URLs and env-var reads, because a call to Gemini or Stripe with no SDK has no dependency to find.
- Files come from `git ls-files --cached --others --exclude-standard`, so a new file nobody has committed yet counts (that is exactly when a
  tripwire must fire) while ignored directories do not.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tomllib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import yaml

CODE_EXT = {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".py", ".go", ".rs", ".dart"}
# A path with any of these as a directory is not the repo's own running code.
SKIP_DIRS = {
    "node_modules", ".venv", "venv", ".git", ".next", ".turbo", "dist", "build", "target", "__pycache__", "site-packages", "coverage",
    "vendor", "third_party", ".claude", ".autopilot", "tests", "test", "__tests__", "fixtures", "__fixtures__", "__golden__", "docs",
    "doc", "examples", "example", "template", "templates", "worktrees",
}
# Never the repo's own files in any scope. The wider `SKIP_DIRS` is only for code that decides what the repo does.
HARD_SKIP = {
    "node_modules", ".venv", "venv", ".git", ".next", ".turbo", "dist", "build", "target", "__pycache__", "site-packages", "coverage",
    "vendor", "third_party", ".claude", "worktrees",
}
SKIP_NAME = re.compile(r"(\.test\.|\.spec\.|\.d\.ts$|\.min\.js$|^test_.*\.py$|_test\.py$|^conftest\.py$|^mock)")
MAX_BYTES = 512 * 1024

DEPLOY_FILES = {"vercel.json", "dockerfile", "fly.toml", "netlify.toml", "render.yaml", "railway.json", "railway.toml", "app.yaml", "serverless.yml"}
MIGRATION = re.compile(r"(^|/)(supabase/)?migrations/[^/]+\.sql$|(^|/)alembic/|(^|/)prisma/schema\.prisma$")

# Dependency names, matched after lower-casing and turning `_` into `-`. A trailing `*` is a prefix.
DEPS = {
    "payments": ["stripe", "@stripe/*", "@paddle/*", "paddle-python-sdk", "@lemonsqueezy/*", "lemonsqueezy*", "@paypal/*", "paypal*", "braintree"],
    "llm": [
        "openai", "anthropic", "@anthropic-ai/*", "@google/genai", "@google/generative-ai", "google-generativeai", "google-genai", "ai",
        "@ai-sdk/*", "langchain", "langchain-*", "@langchain/*", "litellm", "cohere", "cohere-ai", "mistralai", "@mistralai/*", "groq", "groq-sdk",
    ],
    "auth": [
        "next-auth", "@auth/*", "@clerk/*", "@supabase/ssr", "@supabase/auth-helpers-*", "@auth0/*", "auth0", "passport", "passport-*",
        "jsonwebtoken", "jose", "bcrypt", "bcryptjs", "argon2", "argon2-cffi", "fastapi-users", "authlib", "flask-login", "django-allauth",
    ],
    "db": [
        "@supabase/supabase-js", "@supabase/ssr", "prisma", "@prisma/client", "drizzle-orm", "sqlalchemy", "psycopg", "psycopg2",
        "psycopg2-binary", "asyncpg", "pg", "mongoose", "mongodb", "pymongo", "mysql2", "mysqlclient", "typeorm", "knex", "sequelize",
    ],
    "mail": [
        "resend", "nodemailer", "@sendgrid/*", "sendgrid", "postmark", "postmarker", "@postmark/*", "mailgun.js", "mailgun-js", "mailgun",
        "@aws-sdk/client-ses", "@aws-sdk/client-sesv2", "@mailchimp/mailchimp-transactional", "mailchimp-transactional", "react-email-sender",
    ],
}
# A direct database driver (as opposed to a client that goes through an HTTP API such as supabase-js). Connection pooling only matters here.
DB_DRIVERS = [
    "pg", "postgres", "psycopg", "psycopg2", "psycopg2-binary", "asyncpg", "prisma", "@prisma/client", "drizzle-orm", "sqlalchemy", "typeorm",
    "knex", "sequelize", "mysql2", "mysqlclient",
]
# For languages whose package names are module paths, a keyword in the path is enough.
KEYWORD_DEPS = {"payments": ("stripe",), "llm": ("openai", "anthropic", "genai")}

# A call is a URL with a scheme. A bare hostname is an allowlist or a config value (autopilot's own sandbox firewall names
# api.anthropic.com without ever calling it), so it is not evidence.
_SCHEME = r"(?:https?|wss?)://"
HOSTS = {
    "payments": _SCHEME + r"(?:api\.stripe\.com|api\.paddle\.com|api\.lemonsqueezy\.com|api-m\.paypal\.com|api\.sandbox\.paypal\.com)",
    "llm": _SCHEME
    + r"(?:api\.openai\.com|api\.anthropic\.com|generativelanguage\.googleapis\.com|api\.groq\.com|api\.mistral\.ai|api\.cohere\.(?:com|ai))",
    "mail": _SCHEME + r"(?:api\.resend\.com|api\.sendgrid\.com|api\.postmarkapp\.com|api\.mailgun\.net|api\.eu\.mailgun\.net)",
}
ENV_READ = r"(?:process\.env|import\.meta\.env|os\.environ|os\.getenv|getenv|Deno\.env\.get)[^\n]{0,40}?\b"
ENV_NAMES = {
    "payments": r"(STRIPE_(?:SECRET|WEBHOOK|PUBLISHABLE)\w*|PADDLE_API_KEY|LEMON_?SQUEEZY\w*)",
    "llm": r"((?:OPENAI|ANTHROPIC|GEMINI|GOOGLE_AI|GROQ|MISTRAL|COHERE)_API_KEY)",
    "mail": r"((?:RESEND|SENDGRID|MAILGUN)_API_KEY|POSTMARK_(?:SERVER_)?(?:API_)?TOKEN)",
}
IMPORTS = {"llm": r"^\s*(?:import|from)\s+(?:openai|anthropic)\b"}
HAND_ROLLED = re.compile(r"\bcreateHmac\b|\bcreateSign\b|\bjwt\.sign\(|\bbcrypt\.hash|\bhashlib\.pbkdf2|\bhmac\.new\b")
SESSIONISH = re.compile(r"session|cookie|password|login|jwt", re.I)


@dataclass(frozen=True)
class Evidence:
    signal: str  # dependency | source | file
    path: str
    detail: str


def _own_toplevel(root: Path) -> bool:
    r = subprocess.run(["git", "-C", str(root), "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    return r.returncode == 0 and Path(r.stdout.strip()).resolve() == root.resolve()


def _skipped(rel: str) -> bool:
    parts = PurePosixPath(rel).parts
    return any(p in SKIP_DIRS for p in parts[:-1]) or bool(SKIP_NAME.search(parts[-1]))


def _enumerate(root: Path) -> list[str]:
    """Every file path that is the repo's own, repo-relative: tracked or new-but-not-ignored in a git repo, else a pruned walk."""
    root = Path(root)
    if _own_toplevel(root):
        r = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z", "--cached", "--others", "--exclude-standard"], capture_output=True, text=True
        )
        paths = [p for p in r.stdout.split("\0") if p]
    else:
        paths = []
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in HARD_SKIP]
            paths += [str((Path(dirpath) / f).relative_to(root)) for f in filenames]
    return sorted(p for p in paths if not any(part in HARD_SKIP for part in PurePosixPath(p).parts[:-1]) and (root / p).is_file())


PAGE_SKIP_DIRS = {"tests", "test", "__tests__", "fixtures", "__fixtures__", "__golden__", "examples", "example", "template", "templates", ".autopilot"}


def is_page_candidate(rel: str) -> bool:
    """A path that can honestly satisfy "this page or route exists": docs and public files count, tests, fixtures and examples do not."""
    parts = PurePosixPath(rel).parts
    return not any(p in PAGE_SKIP_DIRS for p in parts[:-1]) and not SKIP_NAME.search(parts[-1])


def listed(root: Path) -> list[str]:
    """The repo's own running code and config: `_enumerate` minus tests, fixtures, docs, templates, examples and agent config."""
    return [p for p in _enumerate(root) if not _skipped(p)]


def strip_comments(text: str, python: bool = False) -> str:
    """Remove comments but keep every newline, so a match still reports the right line. `//` counts only at a line start or after
    whitespace, so the `//` in `https://api.stripe.com` is not mistaken for a comment. In Python, triple-quoted strings go too: they
    are docstrings, and a docstring that says "calls https://api.openai.com" is documentation, not a call."""
    blank = lambda m: "\n" * m.group(0).count("\n")  # noqa: E731
    text = re.sub(r"/\*.*?\*/", blank, text, flags=re.S)
    if python:
        text = re.sub(r"(\"\"\"|''').*?\1", blank, text, flags=re.S)
    return re.sub(r"(^|\s)(//|#).*$", r"\1", text, flags=re.M)


def _read(root: Path, rel: str) -> str | None:
    p = root / rel
    try:
        return p.read_text(encoding="utf-8", errors="replace") if p.stat().st_size <= MAX_BYTES else None
    except OSError:
        return None


def _norm(name: str) -> str:
    return re.split(r"[\s<>=!~;\[\(@]", name.strip().lower().replace("_", "-"), maxsplit=1)[0] if not name.startswith("@") else name.lower()


def matches_any(name: str, patterns: list[str]) -> bool:
    """Whether a dependency name matches any pattern: exact, or a prefix when the pattern ends in `*`."""
    n = _norm(name)
    return any((pat[:-1] == n[: len(pat) - 1] if pat.endswith("*") else n == pat) for pat in patterns)


def _dep_capabilities(name: str) -> set[str]:
    return {capability for capability, patterns in DEPS.items() if matches_any(name, patterns)}


def manifest_deps(root: Path, paths: list[str]) -> list[tuple[str, str]]:
    """(dependency name, manifest path) for runtime dependencies only. Never dev dependencies, optional extras or lockfiles."""
    out: list[tuple[str, str]] = []
    for rel in paths:
        name = PurePosixPath(rel).name
        text = _read(root, rel)
        if text is None:
            continue
        try:
            if name == "package.json":
                out += [(d, rel) for d in (json.loads(text).get("dependencies") or {})]
            elif name == "pyproject.toml":
                out += [(d, rel) for d in (tomllib.loads(text).get("project", {}).get("dependencies") or [])]
            elif re.fullmatch(r"requirements[\w.-]*\.txt", name) and not re.search(r"dev|test|lint|doc", name):
                out += [(ln, rel) for ln in text.splitlines() if ln.strip() and not ln.lstrip().startswith(("#", "-"))]
            elif name == "pubspec.yaml":
                out += [(d, rel) for d in ((yaml.safe_load(text) or {}).get("dependencies") or {})]
            elif name in ("go.mod", "Cargo.toml"):
                mods = re.findall(r"^\s*([\w./-]+)\s+v?[\d.]+", text, flags=re.M) if name == "go.mod" else list(
                    tomllib.loads(text).get("dependencies") or {}
                )
                out += [(m, rel) for m in mods]
        except (ValueError, tomllib.TOMLDecodeError, yaml.YAMLError, AttributeError, TypeError):
            continue  # a manifest that does not parse tells us nothing; it is not evidence either way
    return out


class Scan:
    """One cached look at a repo, shared by capability detection and the pack evaluator so each file is listed and read once."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self._all: list[str] | None = None
        self._stripped: dict[str, str | None] = {}
        self._deps: list[tuple[str, str]] | None = None
        self._caps: dict[str, list[Evidence]] | None = None

    @property
    def all_paths(self) -> list[str]:
        if self._all is None:
            self._all = _enumerate(self.root)
        return self._all

    @property
    def code_paths(self) -> list[str]:
        return [p for p in self.all_paths if not _skipped(p)]

    @property
    def page_paths(self) -> list[str]:
        return [p for p in self.all_paths if is_page_candidate(p)]

    @property
    def deps(self) -> list[tuple[str, str]]:
        if self._deps is None:
            self._deps = manifest_deps(self.root, self.code_paths)
        return self._deps

    def raw(self, rel: str) -> str | None:
        return _read(self.root, rel)

    def code(self, rel: str) -> str | None:
        """A code file with comments (and, in Python, docstrings) stripped; None if unreadable or over the size cap."""
        if rel not in self._stripped:
            raw = _read(self.root, rel)
            self._stripped[rel] = None if raw is None else strip_comments(raw, python=rel.endswith(".py"))
        return self._stripped[rel]

    @property
    def caps(self) -> dict[str, list[Evidence]]:
        if self._caps is None:
            self._caps = capabilities(self.root, self)
        return self._caps


def capabilities(root: Path, scan: Scan | None = None) -> dict[str, list[Evidence]]:
    """{capability: [evidence]} for the capabilities this repo has. A capability with no evidence is absent from the dict."""
    scan = scan or Scan(root)
    paths = scan.code_paths
    found: dict[str, list[Evidence]] = {}

    def add(cap: str, e: Evidence) -> None:
        found.setdefault(cap, []).append(e)

    for dep, manifest in scan.deps:
        caps = _dep_capabilities(dep)
        if manifest.endswith(("go.mod", "Cargo.toml")):
            caps |= {c for c, kws in KEYWORD_DEPS.items() if any(k in dep.lower() for k in kws)}
        for cap in caps:
            add(cap, Evidence("dependency", manifest, f"{_norm(dep)} in {manifest} dependencies"))

    for rel in paths:
        base = PurePosixPath(rel).name.lower()
        if base in DEPLOY_FILES:
            add("deploy", Evidence("file", rel, f"{base} is a deploy config"))
        if MIGRATION.search(rel):
            add("db", Evidence("file", rel, "database migrations"))
        if PurePosixPath(rel).suffix not in CODE_EXT:
            continue
        text = scan.code(rel)
        if text is None:
            continue
        for cap, pattern in HOSTS.items():
            for m in re.finditer(pattern, text):
                add(cap, Evidence("source", rel, f"calls {m.group(0)} (line {text.count(chr(10), 0, m.start()) + 1})"))
        for cap, names in ENV_NAMES.items():
            for m in re.finditer(ENV_READ + names, text):
                add(cap, Evidence("source", rel, f"reads {m.group(1)} (line {text.count(chr(10), 0, m.start()) + 1})"))
        for cap, pattern in IMPORTS.items():
            for m in re.finditer(pattern, text, flags=re.M):
                add(cap, Evidence("source", rel, f"imports {m.group(0).split()[-1]} (line {text.count(chr(10), 0, m.start()) + 1})"))
        if HAND_ROLLED.search(text) and SESSIONISH.search(text):
            m = HAND_ROLLED.search(text)
            add("auth", Evidence("source", rel, f"hand-rolled {m.group(0)} (line {text.count(chr(10), 0, m.start()) + 1})"))
    return found


def hosted(caps: dict[str, list[Evidence]]) -> bool:
    """Deployed, and either somebody logs in or somebody pays. A local tool that uses its owner's own key is not hosted."""
    return "deploy" in caps and ("auth" in caps or "payments" in caps)


_CRON_PATH = re.compile(r"(^|/)cron(/|$)")


def has_cron(scan: Scan) -> bool:
    """Whether the repo runs scheduled jobs: a `cron` directory in its own code, or a non-empty `crons` list in `vercel.json`.
    Tests and docs never count (they are not in `code_paths`)."""
    if any(_CRON_PATH.search(p) for p in scan.code_paths):
        return True
    for rel in scan.code_paths:
        if PurePosixPath(rel).name.lower() == "vercel.json":
            try:
                if (json.loads(scan.raw(rel) or "{}").get("crons") or []):
                    return True
            except (ValueError, AttributeError):
                continue
    return False


def has_db_driver(scan: Scan) -> bool:
    """Whether the repo's runtime dependencies include a direct database driver or ORM (not an HTTP-API client like supabase-js)."""
    return any(matches_any(name, DB_DRIVERS) for name, _ in scan.deps)
