"""Sales budget in schema app.

Admins upload budget.xlsx (rows DLR = dealer group, columns Apr..Mar, K USD)
through the report form; the upload replaces the budget of the current fiscal
year in app.sales_budget in one transaction. The warehouse stays read-only:
schema app is the only place the dashboard writes to.
"""

from datetime import datetime

import pandas as pd
from flask_login import current_user

from dashboard import db
from dashboard.authentication.models import SCHEMA
from dashboard.reports.sales.frames import fyfunc

MONTHS = ["Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec", "Jan", "Feb", "Mar"]


class SalesBudget(db.Model):
    __tablename__ = "sales_budget"
    __table_args__ = (db.CheckConstraint(f"month IN ({', '.join(repr(m) for m in MONTHS)})", name="ck_sales_budget__month"),
                      {"schema": SCHEMA})

    fy = db.Column(db.Integer, primary_key=True)                 # fiscal year: April fy .. March fy+1
    group_code = db.Column(db.Text, primary_key=True)
    month = db.Column(db.Text, primary_key=True)                 # Apr .. Mar, as in the file
    amount_k_usd = db.Column(db.Numeric(14, 2), nullable=False)
    uploaded_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    uploaded_by = db.Column(db.Text)


def current_fy(today: pd.Timestamp | None = None) -> int:
    return fyfunc(today or pd.Timestamp("today"))


def parse_budget(frame: pd.DataFrame) -> pd.DataFrame:
    """Wide xlsx frame -> long rows; ValueError with a readable message if the layout is wrong."""
    frame = frame.rename(columns=lambda c: str(c).strip())
    missing = [c for c in ["DLR", *MONTHS] if c not in frame.columns]
    if missing:
        raise ValueError(f"budget file: missing columns {', '.join(missing)}")
    frame = frame.dropna(subset=["DLR"])
    frame["DLR"] = frame["DLR"].astype(str).str.strip()
    if frame["DLR"].duplicated().any():
        raise ValueError("budget file: a dealer group appears twice")
    values = frame.set_index("DLR")[MONTHS].apply(pd.to_numeric, errors="coerce")
    if values.isna().any().any():
        raise ValueError("budget file: every month must be a number")
    return values.stack(future_stack=True).dropna().rename("amount_k_usd").rename_axis(["group_code", "month"]).reset_index()


def replace_budget(rows: pd.DataFrame, fy: int) -> int:
    """Replace the budget of one fiscal year; one transaction, so a failed upload leaves the old one."""
    user = getattr(current_user, "username", None)
    now = datetime.now()
    db.session.execute(db.delete(SalesBudget).where(SalesBudget.fy == fy))
    db.session.add_all(SalesBudget(fy=fy, group_code=r.group_code, month=r.month, amount_k_usd=float(r.amount_k_usd),
                                   uploaded_at=now, uploaded_by=user)
                       for r in rows.itertuples())
    db.session.commit()
    return len(rows)


def load_budget(groups: list[str], fy: int | None = None) -> tuple[pd.DataFrame, datetime | None]:
    """Budget of the report groups in the legacy wide layout (DLR + Apr..Mar); missing -> 0."""
    fy = fy if fy is not None else current_fy()
    rows = db.session.scalars(db.select(SalesBudget).where(SalesBudget.fy == fy)).all()
    long = pd.DataFrame([(r.group_code, r.month, float(r.amount_k_usd)) for r in rows],
                        columns=["DLR", "month", "amount"])
    wide = long.pivot_table(index="DLR", columns="month", values="amount", aggfunc="sum") if len(long) else pd.DataFrame()
    wide = wide.reindex(index=groups, columns=MONTHS).fillna(0)
    wide.index.name = "DLR"
    uploaded = max((r.uploaded_at for r in rows), default=None)
    return wide.reset_index(), uploaded
