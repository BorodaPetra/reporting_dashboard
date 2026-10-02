"""Parts sales report: state built from the warehouse (D4.2).

Port of the old module-level app.py. The pandas functions of udata / ucharts
are called as before; the report groups come from reports/groups.py.
"""

from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd

from dashboard.reports.sales import charts
from dashboard.reports.sales import frames
from dashboard.data import legacy
from dashboard.reports.common.daily import prepared_daily
from dashboard.reports.common.groups import breakdown_group, report_groups, with_mining_suppliers
from dashboard.reports.common.top_parts import TopParts, top_parts
from dashboard.reports.sales.budget import load_budget

NAME = "sales"

FY_COLUMNS = {
    "sm_cfy": "Actual Sales (month)", "sma_cfy": "Accum. Sales (current FY)",
    "sma_pfy": "Accum. Sales (previous FY)", "fm": "Forecast (month)", "fma": "Accum. Forecast",
    "bm_init": "Initial Budget", "bma_resid": "Accum. Budget (residual)",
    "sma_bma": "Accum. Budget (revised)", "bm_tgt": "Target Budget",
    "fm_prf": "Forecast Performace (month)", "fma_prf": "Forecast Performace (current FY)",
    "bma_prf": "Budget Performace (current FY)",
}


@dataclass
class SalesState:
    today: pd.Timestamp
    groups: list[str]
    breakdown_group: str
    daily: pd.DataFrame                 # all dealers: detailed chart, filters, breakdown mailing
    parts: pd.DataFrame                 # HID of the parts, for the breakdown mailing
    budget_uploaded: datetime | None     # None: no budget for this fiscal year yet
    tiles: dict
    table_sales: object
    table_orders: object
    report_html: str                    # body of the daily e-mail
    dlr_codes: dict
    dlr_full_names: dict
    charts: dict = field(default_factory=dict)   # name -> {"name", "chart", "table"}
    top_parts: TopParts | None = None


def outstanding_orders(dd: pd.DataFrame, groups: list[str], today: pd.Timestamp) -> pd.DataFrame:
    """uframe.update_outstanding_orders_table without the write-back: history from
    the warehouse, the current month computed from the open lines."""
    history = legacy.outstanding_orders_history()
    src = dd[(~dd["SO_PROGRESS_CODE"].isin(["6", "A"])) & (dd["DLR_META"].isin(groups))]
    src = (src.groupby("DLR_META")["SA_USD"].sum() / 1000).astype(int)
    month = today if today.is_month_end else today + pd.offsets.MonthEnd()
    src = pd.concat([history.set_index("DATE"), src.to_frame(month).T.assign(ALL=lambda x: x.sum(axis=1))])
    src["ALL"] = src[[g for g in groups if g in src.columns]].sum(axis=1)
    src = src.loc[~src.index.duplicated(keep="last"), :].copy().fillna(0).reset_index()
    return src.rename(columns={"index": "DATE"})


def top_sold(dd: pd.DataFrame, today: pd.Timestamp) -> TopParts:
    """TOP-10 parts invoiced in the current FY: the sales of the FY chart (report groups,
    invoice date in the fiscal year), per part number as invoiced."""
    fy = frames.fyfunc(today)
    sold = dd[dd["SO_INV_DATE_FY"] == str(fy)]
    return top_parts(sold.groupby("PTS_NO", as_index=False).agg(QTY=("QTY", "sum"), AMOUNT=("SA_USD", "sum")),
                     f"FY-{str(fy)[-2:]}")


def named(name: str, payload: dict) -> dict:
    return {"name": name, **payload}


def build() -> SalesState:
    today = pd.Timestamp("today").normalize()
    groups = report_groups()
    daily = prepared_daily()
    parts = with_mining_suppliers(legacy.parts(daily["PTS_NO"].dropna().unique().tolist()))
    dd = daily[daily["DLR_META"].isin(groups)].copy()

    budget, uploaded = load_budget(groups)
    fy_sales = frames.get_data_main_sales_chart(budget.copy(), dd)
    tiles_frame = frames.get_tiles_dataframe(fy_sales).round(3).fillna(0)
    table_sales, table_orders = frames.get_daily_like_table(tiles_frame, dd)
    orders = outstanding_orders(dd, groups, today)

    fy_chart = charts.show_fy_sales_chart(fy_sales)
    fy_chart["table"] = tiles_frame.reset_index().rename(columns=FY_COLUMNS).to_dict(orient="split")
    outstanding = charts.show_outstanding_orders_chart(orders)
    outstanding["table"] = orders.to_dict(orient="split")
    return SalesState(
        today=today, groups=groups, breakdown_group=breakdown_group(),
        daily=daily, parts=parts,
        budget_uploaded=uploaded,
        tiles=frames.get_tiles(tiles_frame.loc["ALL"]),
        table_sales=table_sales, table_orders=table_orders,
        report_html=frames.prepare_daily_html(budget.copy(), dd),
        # sorted: unique() keeps the order of the rows, which the database does not fix,
        # and the checkboxes of the dealer selector changed places on every build
        dlr_codes=dd.sort_values("DLR_CODE").groupby("DLR_META")["DLR_CODE"].unique().to_dict(),
        dlr_full_names=dd.sort_values("DLR_FULL_NAME").groupby("DLR_META")["DLR_FULL_NAME"].unique().to_dict(),
        charts={
            "fy": named("fy_sales", fy_chart),
            "detailed": named("detailed", charts.show_detailed_sales_chart_new(daily)),
            "outstanding": named("outstanding", outstanding),
            "breakdown": named("breakdown", charts.show_group_sales_breakdown_chart(daily)),
            "gross_profit": named("gross_profit", charts.show_gross_profit_chart(daily)),
        },
        top_parts=top_sold(dd, today),
    )
