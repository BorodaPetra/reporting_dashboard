"""The prepared `daily` frame shared by the sales, stock and parts reports (D4).

Port of the old pipeline

    uframe.obtain_data(['daily', 'gtd', 'cost_rub', 'usd_rate', 'kwe_inbound', ...])
    uframe.handle_gtd / handle_prices / adjust_daily

onto the warehouse. The pandas steps are kept as they were (the result
is compared column by column with the old daily.pkl); what changed is where
the reference data comes from:

| old (umap.py dictionaries, removed in D0)   | now                                            |
|---------------------------------------------|------------------------------------------------|
| dealercodename -> DLR                       | ref.dealer.short_name (legacy.order_lines)      |
| DLR contains a group code -> DLR_META       | ref.dealer.group_code; OTHER/DEPOT -> DLR      |
| dealercodenamefull -> DLR_FULL_NAME         | ref.dealer.name                                |
| supersessions.groupby(PTS_NO).PNL.last()    | ref.part_pnl via order_line_flow               |
| partsmaster PCLASS / TNVED                  | ref.part_full product_class / hs_code          |
| PCLASS "M" for two suppliers (hard-coded)  | MINING_SUPPLIERS in the environment            |
| stock_dlr_codes -> VND_NAME "HCMR_WH"       | ref.dealer.is_stock_location                   |
| two hard-coded dealers -> "TVER_WH"/"NVK_WH"| DEALER_WAREHOUSE_LABELS in the environment     |

Dropped, because they never changed anything (checked on the old pickle):
* DLR := <a group> for two dealer codes when SO_TYPE_CODE in [~6, 3]: ~6 is -7 and
  the codes are strings, so the condition was never true (the dealers belong
  to that group anyway).
* daily[PO_INVOICE != <one invoice>]: the invoice exists neither in the old
  pickle nor in the warehouse.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from dashboard.reports.common.prices import extract_time_groups, handle_prices
from dashboard.data import legacy
from dashboard.data import parts as parts_data
from dashboard.reports.common.groups import demand_groups, warehouse_labels, with_mining_suppliers
from dashboard.reports.common.shared import shared

SERVICE_GROUPS = ("OTHER", "DEPOT")
GROSS_PROFIT_START = "2024-09-01"          # sales invoices with a gross profit (Sales report chart)


@dataclass(init=False)
class Prices:
    """What uframe.handle_prices fills in (attributes are set by it)."""


def cost_prices() -> Prices:
    """Monthly unit cost per part in RUB and USD: uframe.handle_prices, unchanged.
    Shared by the report builds of the day (reports/shared.py)."""
    def compute() -> Prices:
        source = Prices()
        source.cost_rub = legacy.unit_cost_rub()
        source.usd_rate = legacy.usd_rate()
        return handle_prices(source, Prices())
    return shared("cost_prices", compute)


def adjust_daily(daily: pd.DataFrame, parts: pd.DataFrame, price: Prices,
                 gtd: pd.DataFrame, receipts: pd.DataFrame) -> pd.DataFrame:
    """uframe.adjust_daily with the reference data of the warehouse (see the module doc)."""
    so_cancelled = daily[daily["SO_PROGRESS_CODE"] == "A"]
    po_cancelled = daily[daily["PO_PROGRESS_CODE"] == "A"]
    daily = daily[(daily["SO_PROGRESS_CODE"] != "A") & (daily["PO_PROGRESS_CODE"] != "A")]
    daily = pd.concat([daily,
                       po_cancelled[po_cancelled["SO_PROGRESS_CODE"] == "6"],
                       so_cancelled[so_cancelled["PO_PROGRESS_CODE"] == "5"]])
    daily = extract_time_groups(daily, [c for c in daily.columns if "DATE" in c])

    daily["DATE_YM"] = daily["SO_DATE_YM"].fillna(daily["PO_DATE_YM"]).fillna(daily["SO_INV_DATE_YM"])
    daily["DLR_META"] = np.where(daily["DLR_META"].isin(SERVICE_GROUPS), daily["DLR"], daily["DLR_META"])
    daily["DLR_CODE_FULL_NAME"] = [f"{c}:{n}" if (pd.notna(c) and pd.notna(n)) else None
                                   for c, n in zip(daily["DLR_CODE"], daily["DLR_FULL_NAME"])]
    daily["PNL"] = daily["PNL"].fillna(daily["PTS_NO"])
    by_part = parts.groupby("PTS_NO")
    daily["PCLASS"] = daily["PTS_NO"].map(by_part["PCLASS"].last()).fillna("OTHER")
    daily["TNVED"] = daily["PTS_NO"].map(by_part["TNVED"].last()).fillna("OTHER")

    index = daily.set_index(["DATE_YM", "PTS_NO"]).index
    daily["COST_USD"] = index.map(price.cost_usd.drop(columns=["DATE"]).set_index(["DATE_YM", "PTS_NO"]).squeeze())
    daily["CA_USD"] = daily["COST_USD"] * daily["QTY"]
    daily["COST_RUB"] = index.map(price.cost_rub.drop(columns=["DATE"]).set_index(["DATE_YM", "PTS_NO"]).squeeze())
    daily["CA_RUB"] = daily["COST_RUB"] * daily["QTY"]
    # old handle_gtd kept the first declaration of an invoice (drop_duplicates)
    daily["GTD"] = daily["PO_INVOICE"].map(gtd.drop_duplicates("PO_INVOICE").set_index("PO_INVOICE")["GTD"])

    no_vendor = daily["VND_NAME"].isna()
    daily.loc[daily["IS_STOCK_LOCATION"].eq(True) & no_vendor, "VND_NAME"] = "HCMR_WH"
    for dealer_code, label in warehouse_labels().items():
        daily.loc[(daily["DLR_CODE"] == dealer_code) & daily["VND_NAME"].isna(), "VND_NAME"] = label
    daily["ENTRY_CODE"] = np.where(daily["VND_NAME"] == "HCMR_WH", "Y", daily["ENTRY_CODE"])

    daily["ARRIVE_DATE"] = daily["PO_INVOICE"].map(receipts.groupby("PREADVICEID")["FINISHDATE"].max())
    # pd.notna, not "is not None": a missing SO is None in an object column, NaN in the str column of pandas 3
    # PERF: one pass over 600k rows in Python; vectorised: (SHIP_DATE + 60 days).where(SHIP_DATE.notna()
    #   & SO_NUM.notna() & PO_PROGRESS_CODE.eq("5"))
    daily["ARRIVE_CALC"] =[shipped + pd.offsets.Day(60) if (shipped and pd.notna(so) and progress == "5")
                            else pd.NaT
                            for progress, so, shipped in zip(daily["PO_PROGRESS_CODE"], daily["SO_NUM"],
                                                             daily["SHIP_DATE"])]
    daily["ARRIVE_DATE"] = daily["ARRIVE_DATE"].fillna(daily["ARRIVE_CALC"])
    return daily.sort_values("DATE_YM")


def gross_profit_usd(lines: pd.DataFrame) -> np.ndarray:
    """The gross profit rule of the Sales report: sold from stock (HCMR_WH and the warehouse
    labels) -> sales minus cost, a direct order -> sales minus its purchase amount."""
    from_stock = lines["VND_NAME"].isin(["HCMR_WH", *warehouse_labels().values()])
    return lines["SA_USD"] - np.where(from_stock, lines["CA_USD"], lines["PA_USD"])


def demand_ranks() -> pd.Series:
    """Rank A..F of every chain (PNL) per month, (DATE_YM, PNL) -> rank: the demand model
    of the parts report (reports/parts/model.py) over all chains. Old code:
    handle_demand wrote daily['RANK'] the same way."""
    from flask import current_app

    from dashboard.reports.parts import model

    def compute() -> pd.Series:
        start = current_app.config["DEMAND_START"]
        rows = parts_data.demand(demand_groups(), start)
        table = model.rank_table(model.demand_matrix(rows, start, pd.Timestamp("today").normalize()))
        return table.T.stack(future_stack=True).dropna()
    return shared("demand_ranks", compute)


def prepared_daily(date_from: str = legacy.LEGACY_START) -> pd.DataFrame:
    """The shared daily of the sales and stock reports, built once per report day."""
    return shared(f"daily:{date_from}", lambda: _prepared_daily(date_from))


def _prepared_daily(date_from: str) -> pd.DataFrame:
    daily = legacy.order_lines(date_from)
    # PERF: a second query only for PCLASS and TNVED of the ordered parts; the two
    #   columns could come with ORDER_LINES_SQL (ref.part_full is joined there anyway).
    parts = with_mining_suppliers(legacy.parts(daily["PTS_NO"].dropna().unique().tolist()))
    daily = adjust_daily(daily, parts, cost_prices(), legacy.gtd(), legacy.warehouse_receipts())
    daily["RANK"] = daily.set_index(["DATE_YM", "PNL"]).index.map(demand_ranks())
    return daily
