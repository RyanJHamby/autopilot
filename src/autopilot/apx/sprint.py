"""Sprints (stub: tests first; the implementation follows in the next commit)."""

from __future__ import annotations

from dataclasses import dataclass


class SprintError(ValueError):
    pass


@dataclass(frozen=True)
class Limits:
    window_h: float
    runs: int
    usd: float
    per_run_usd: float


def policy_limits() -> Limits:
    raise NotImplementedError


def limits_for(cfg: dict):
    raise NotImplementedError


def record(ledger, planned, now) -> None:
    raise NotImplementedError
