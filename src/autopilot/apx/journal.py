"""Stub: apx journal conflict resolution (tests first)."""

KIND = "resolve-journal"
NEEDS: dict = {}


class AllowlistError(ValueError):
    pass


def load_allowlist(path=None):
    raise NotImplementedError


def journal_files(repo, allow=None):
    raise NotImplementedError


def merge_appended(base, main, head):
    raise NotImplementedError


def has_markers(data):
    raise NotImplementedError
