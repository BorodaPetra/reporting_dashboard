"""Data layer: parameterised queries against the warehouse views -> pandas.

    from dashboard.data import legacy
    daily = legacy.order_lines(date_from="2024-01-01", groups=["AUR"])

* SQL text is constant; values travel as bound parameters (:name), never as
  f-strings -> no SQL injection, and PostgreSQL can reuse the plan.
* Results are cached in the process for DATA_CACHE_TTL seconds (default 900):
  the warehouse is loaded nightly, a report opened ten times an hour must not
  run the same query ten times. The cache key is (query name, parameters).
* Every call returns a COPY: the legacy pandas code modifies frames in place,
  a shared cached frame would be corrupted for the next request.
"""

import threading
import time
from typing import Any

import pandas as pd
from flask import current_app
from sqlalchemy import text

from dashboard import db

_cache: dict[tuple, tuple[float, pd.DataFrame]] = {}
_lock = threading.Lock()


def _key(name: str, params: dict[str, Any]) -> tuple:
    return name, tuple(sorted((k, tuple(v) if isinstance(v, list) else v) for k, v in params.items()))


def query_frame(name: str, sql: str, params: dict[str, Any] | None = None,
                parse_dates: list[str] | None = None, cache: bool = True) -> pd.DataFrame:
    """Run a named query with bound parameters; cached for DATA_CACHE_TTL seconds.
    cache=False for one-off queries with large array parameters: the key would hold
    every element of the arrays (millions of Python objects) for the lifetime of the entry."""
    params = params or {}
    ttl = current_app.config.get("DATA_CACHE_TTL", 900)
    key = _key(name, params) if cache else None
    now = time.monotonic()
    with _lock:
        hit = _cache.get(key) if cache else None
        if hit and now - hit[0] < ttl:
            return hit[1].copy()

    # PERF: two requests that miss the cache at the same time both run the query
    # (20-30 s each for full loads). A per-key lock or a "loading" future in _cache
    # would let the second request wait for the first instead.
    with db.engine.connect() as conn:
        # PERF: pd.read_sql builds a Python object per value, then a frame from them;
        # that, not PostgreSQL, is most of the 19-30 s of the full loads (04-data-layer.md).
        # Arrow-native loading skips the Python objects: pd.read_sql(..., dtype_backend="pyarrow")
        # helps a little; an ADBC connection (adbc-driver-postgresql, COPY in binary format)
        # is usually several times faster. Measure on legacy.parts() before switching.
        frame = pd.read_sql(text(sql), conn, params=params, parse_dates=parse_dates)

    if not cache:
        return frame
    with _lock:
        _cache[key] = (now, frame)
    return frame.copy()


def clear_cache() -> None:
    with _lock:
        _cache.clear()


def cache_info() -> dict[str, int]:
    with _lock:
        return {"entries": len(_cache), "rows": sum(len(f) for _, f in _cache.values())}
