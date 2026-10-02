"""Shared helpers of the D4 reconciliation scripts: old pickles vs the warehouse.

The pickles are the last results of the old MySQL code (local only, git-ignored,
real data). The scripts therefore connect to the REAL database hcmr, read-only as
dashboard_app, and print only counts and totals, never values.

    uv run python scripts/reconcile/delivery.py
"""

import os
from pathlib import Path

import pandas as pd

from dashboard import create_app
from dashboard.config import DebugConfig, env_list, env_map

ROOT = Path(__file__).resolve().parents[2]
PKL = ROOT / "instance" / "reconcile"


class ReconcileConfig(DebugConfig):
    SECRET_KEY = "reconcile-only"
    SQLALCHEMY_DATABASE_URI = os.getenv("RECONCILE_DATABASE_URL",
                                        "postgresql+psycopg://dashboard_app@localhost:5432/hcmr")
    REPORT_BUILD_SYNC = True
    REPORT_WARMUP = False
    DATA_CACHE_TTL = 3600
    # real group / dealer codes for the real database: local .env only
    STOCK_EXCLUDE_GROUPS = env_list("RECONCILE_STOCK_EXCLUDE_GROUPS")
    BREAKDOWN_GROUP = os.getenv("RECONCILE_BREAKDOWN_GROUP")
    BREAKDOWN_SUBGROUPS = env_map("RECONCILE_BREAKDOWN_SUBGROUPS")
    DEALER_WAREHOUSE_LABELS = env_map("RECONCILE_DEALER_WAREHOUSE_LABELS")
    MINING_SUPPLIERS = env_list("RECONCILE_MINING_SUPPLIERS")


def app():
    return create_app(ReconcileConfig)


def old_daily() -> pd.DataFrame:
    return pd.read_pickle(PKL / "daily.pkl")


def snapshot(daily: pd.DataFrame) -> pd.Timestamp:
    """When the old code ran: the TODAY column of its query."""
    return pd.Timestamp(daily["TODAY"].iloc[0]).normalize()


def section(title: str) -> None:
    print(f"\n--- {title}")


def row(label: str, *values) -> None:
    print(f"    {label:34}", *values)


def compare_keys(old: pd.Index, new: pd.Index, what: str) -> tuple[pd.Index, pd.Index, pd.Index]:
    both, only_old, only_new = old.intersection(new), old.difference(new), new.difference(old)
    row(f"{what}: old / new / both", len(old), len(new), len(both))
    row("  only in old / only in new", len(only_old), len(only_new))
    return both, only_old, only_new


def compare_numbers(old: pd.Series, new: pd.Series, label: str, tol: float = 0.01) -> int:
    """Aligned by index; NaN == NaN counts as equal."""
    old, new = old.astype(float), new.astype(float)
    diff = (old - new).abs()
    bad = int(((diff > tol) | (old.isna() != new.isna())).sum())
    row(f"{label}: differ / total", bad, len(old))
    row("  sum old / sum new", f"{old.sum():,.2f}", f"{new.sum():,.2f}")
    return bad


def compare_labels(old: pd.Series, new: pd.Series, label: str) -> int:
    bad = int((old.fillna("<NA>").astype(str) != new.fillna("<NA>").astype(str)).sum())
    row(f"{label}: differ / total", bad, len(old))
    return bad


# ---- line matching of the daily frames (scripts/reconcile/daily.py, scripts/reconcile/parts.py)

KEY = ["SO_NUM", "ITEM", "PO_NUM"]


def keyed(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    for col in KEY:
        frame[col] = frame[col].astype("string").fillna("")
    frame["_N"] = frame.groupby(KEY).cumcount()
    return frame.set_index(KEY + ["_N"])


def differ(old: pd.Series, new: pd.Series) -> int:
    if pd.api.types.is_numeric_dtype(old) and pd.api.types.is_numeric_dtype(new):
        o, n = old.astype(float), new.astype(float)
        return int((((o - n).abs() > 0.011) | (o.isna() != n.isna())).sum())
    if pd.api.types.is_datetime64_any_dtype(old) or pd.api.types.is_datetime64_any_dtype(new):
        o, n = pd.to_datetime(old, errors="coerce"), pd.to_datetime(new, errors="coerce")
        return int(((o != n) & ~(o.isna() & n.isna())).sum())
    o, n = old.astype("string").fillna("<NA>"), new.astype("string").fillna("<NA>")
    return int((o != n).sum())
