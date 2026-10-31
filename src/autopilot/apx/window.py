"""The hours apx may work (APX_ACTIVE_WINDOW, e.g. "18:00-08:30" in America/New_York, weekends all day).

Outside the window a pass does nothing at all: no polling, no CI, no agent run, no swap. Unset means always on.
A malformed value is a config error (the daemon refuses to start), never "always on".
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

_HHMM = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


@dataclass(frozen=True)
class Window:
    start: dt.time
    end: dt.time
    tz: str = "America/New_York"
    weekends: bool = True

    def label(self) -> str:
        return f"{self.start:%H:%M}-{self.end:%H:%M} {self.tz}" + (", weekends all day" if self.weekends else "")

    def is_open(self, now: dt.datetime) -> bool:
        local = now.astimezone(ZoneInfo(self.tz))
        if self.weekends and local.weekday() >= 5:
            return True
        t = local.time().replace(second=0, microsecond=0)
        if self.start <= self.end:
            return self.start <= t < self.end
        return t >= self.start or t < self.end  # wraps midnight: evening start, morning end


def minutes_left(w: Window, now: dt.datetime, horizon: int = 24 * 60) -> int:
    """Whole minutes until the window closes, capped at `horizon`; 0 when closed."""
    n = 0
    while n < horizon and w.is_open(now + dt.timedelta(minutes=n)):
        n += 1
    return n


def parse(spec: str, tz: str = "", weekends: str = "1") -> Window | None:
    """`spec` is "HH:MM-HH:MM"; empty means no window. Raises ValueError on anything else."""
    spec = spec.strip()
    if not spec:
        return None
    a, sep, b = spec.partition("-")
    ma, mb = _HHMM.match(a.strip()), _HHMM.match(b.strip())
    if not sep or not ma or not mb:
        raise ValueError(f"APX_ACTIVE_WINDOW must look like 18:00-08:30, got {spec!r}")
    start, end = dt.time(int(ma[1]), int(ma[2])), dt.time(int(mb[1]), int(mb[2]))
    if start == end:
        raise ValueError("APX_ACTIVE_WINDOW start and end are the same")
    zone = tz.strip() or "America/New_York"
    try:
        ZoneInfo(zone)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError(f"unknown time zone {zone!r}") from None
    return Window(start, end, zone, weekends.strip() != "0")


def idle_line(w: Window) -> str:
    return f"idle: outside the active window ({w.label()}); nothing ran"
