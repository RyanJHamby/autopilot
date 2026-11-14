"""Host tools each enrolled repo's CI needs (stub)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

DATA_FILE = Path(__file__).with_name("host_tools.json")


@dataclass(frozen=True)
class Probe:
    argv: tuple[str, ...]
    needs: str
    stdin: str | None = None
    expect: str | None = None


@dataclass(frozen=True)
class HostTools:
    repos: dict
    probes: dict
    hints: dict


def load(path: Path | None = None) -> HostTools:
    raise NotImplementedError
