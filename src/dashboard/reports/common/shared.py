"""Frames shared by the report builds of one warm-up.

The sales and stock reports both need the prepared `daily` (~1 min), the unit
costs and the demand ranks. Without sharing, the stock build computed them all
again right after the sales build in the same warm-up.

* A value lives SHARED_KEEP_MINUTES (default 30) and never past the next
  REPORT_REFRESH_TIME (the nightly load). Long enough for the stock build to
  reuse what the sales build computed in the same warm-up; then a timer drops it:
  the daily alone takes ~1.5 GB (measured on the demo database), and the sales
  state keeps its own copy anyway.
* One lock per name: when two builds need the same value at the same time, the
  second waits for the first instead of computing it again.
* Every caller gets its own deep copy: the legacy pandas code changes frames in
  place, the shared value must stay as computed.
"""

import copy
import threading
from datetime import datetime, time, timedelta
from typing import Any, Callable  # noqa: UP035

import pandas as pd
from dashboard.reports.common.state import next_refresh
from flask import current_app

_entries: dict[str, tuple[datetime, Any]] = {}  # name -> (valid until, value)
_locks: dict[str, threading.Lock] = {}
_guard = threading.Lock()  # protects the two dicts


def _lock_for(name: str) -> threading.Lock:
    with _guard:
        return _locks.setdefault(name, threading.Lock())


def _drop(name: str, until: datetime) -> None:
    with _guard:
        if (
            name in _entries and _entries[name][0] == until
        ):  # not replaced by a newer value
            del _entries[name]


def _own_copy(value: Any) -> Any:
    """A new object for the caller over the same data (pandas Copy-on-Write): a frame or
    series is copied shallowly; Prices of daily.cost_prices is copied with each frame
    attribute copied shallowly; a value without attributes (a number) is deep-copied."""
    if isinstance(value, (pd.DataFrame, pd.Series)):
        return value.copy(deep=False)
    if not hasattr(value, "__dict__"):
        return copy.deepcopy(value)
    copied = copy.copy(value)
    for key, attr in vars(copied).items():
        if isinstance(attr, (pd.DataFrame, pd.Series)):
            setattr(copied, key, attr.copy(deep=False))
    return copied


def shared(name: str, compute: Callable[[], Any], now: datetime | None = None) -> Any:
    """compute() once, a copy of the result for every caller until the value expires."""
    now = now or datetime.now()
    with _lock_for(name):
        hit = _entries.get(name)
        if hit is not None and now < hit[0]:
            value = hit[1]  # a local reference: the timer may drop the entry meanwhile
        else:
            config = current_app.config
            keep = timedelta(minutes=config.get("SHARED_KEEP_MINUTES", 30))
            refresh_at = time.fromisoformat(config.get("REPORT_REFRESH_TIME", "06:00"))
            until = min(now + keep, next_refresh(now, refresh_at))
            value = compute()
            _entries[name] = (until, value)
            timer = threading.Timer(keep.total_seconds(), _drop, args=(name, until))
            timer.daemon = True  # never keeps the process alive
            timer.start()
        return _own_copy(value)


def clear() -> None:
    """Drop every shared value (tests; a manual reload after fixing the warehouse)."""
    with _guard:
        _entries.clear()


def info() -> dict[str, str]:
    with _guard:
        return {
            name: f"valid until {until:%Y-%m-%d %H:%M}"
            for name, (until, _) in _entries.items()
        }
