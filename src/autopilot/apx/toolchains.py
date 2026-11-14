"""Stub (red commit): per-repo toolchains."""


def load_declared(path=None):
    raise NotImplementedError


def bin_dirs(repo, root, declared=None):
    raise NotImplementedError


def check_repos(repos, root, declared=None):
    raise NotImplementedError
