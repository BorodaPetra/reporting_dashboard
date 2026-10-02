"""Parts report, SQL-first (D4.3).

A request for a list of parts reads only those parts and their supersession
chains from the warehouse (dashboard/data/parts.py), runs the demand model
(model.py) and the unchanged presentation code of the old report
(uframe_new.prettify_outupt), so the JSON of /processing and the page stay as
they were.

The report state (build) holds only the sorted part numbers for the suggestions
of the single part search (in memory, not a warehouse index):
the database collation (Russian_Russia) puts punctuation before digits, so a
prefix range on the primary key misses up to 175 k numbers; bytes sort plainly.
"""

import re
from dataclasses import dataclass
from types import SimpleNamespace

import numpy as np
import pandas as pd
from flask import current_app

from dashboard.data import legacy
from dashboard.data import parts as parts_data
from dashboard.reports.common.daily import GROSS_PROFIT_START, Prices, gross_profit_usd
from dashboard.reports.common.prices import handle_prices
from dashboard.reports.parts import frames
from dashboard.reports.common.groups import demand_groups, with_mining_suppliers
from dashboard.stoplist import models as stoplist

from . import model
from .output import SHOW_MONTHS, prettify_output

NAME = "parts"
MODEL_PATTERN = re.compile(r"^(E[HX]\d{4}(?:-\d+)?|Z[WX]\d{3}[A-Z]{0,3}(?:-\d[A-Z])?)$")   # old first_adjustments
DISPLAY_CLASS = {"CM": "C/M", "C": "CE", "W": "CE"}                                        # old first_adjustments
SUGGESTIONS = 10                      # part numbers offered for a typed beginning


@dataclass
class PartsState:
    numbers: np.ndarray                 # bytes (ASCII part numbers), upper case, unique, sorted


def build() -> PartsState:
    # PERF: ~36 MB per worker process; an index ref.part (part_number text_pattern_ops) in
    #   the warehouse would serve LIKE 'prefix%' in ~1 ms from the database instead
    return PartsState(np.sort(parts_data.part_numbers()["PTS_NO"].to_numpy(dtype="S")))


def suggestions(state: PartsState, prefix: str) -> list[str]:
    """The first SUGGESTIONS part numbers that start with prefix (case-insensitive)."""
    key = prefix.strip().upper().encode()
    start = np.searchsorted(state.numbers, key)
    end = np.searchsorted(state.numbers, key + b"\xff")        # no byte of an ASCII string is 0xff
    return [number.decode() for number in state.numbers[start:min(end, start + SUGGESTIONS)]]


def parts_master(idx: pd.Index) -> pd.DataFrame:
    """Old obtain_partsmaster + first_adjustments for the requested parts. PCLASS keeps the
    classes of the warehouse (M / C / CM / OTHER): the DEAD rule needs them (spec, bug 2)."""
    pm = with_mining_suppliers(legacy.parts(list(idx)))
    pm["PNL"] = pm["PNL"].fillna(pm["PTS_NO"])
    prev = parts_data.previous_numbers(pm["PTS_NO"].tolist()).set_index("PTS_NO")["PREV"]
    pm["PREV"] = pm["PTS_NO"].map(prev)
    pm["STOP_FLAG"] = np.where(pm["PTS_NO"].isin(stoplist.stopped(pm["PTS_NO"].tolist())), "Y", "N")
    pm["CAT"] = pm["CAT"].fillna("-").str.upper()
    pm["QPM"] = pm["QPM"].replace({"-": 1, 0: 1, np.nan: 1})
    pm["WEIGHT"] = pm["WEIGHT"].fillna(0).round(3)
    models = pm["MDLS"].apply(lambda m: list(m) if isinstance(m, (list, np.ndarray)) else [])
    pm["MDLS_ALL"] = models.apply(lambda m: sorted({x for x in m if x}))
    pm["MDLS"] = models.apply(lambda m: ", ".join(sorted({x for x in m if x and MODEL_PATTERN.match(x)})))
    # columns of the old MySQL partsmaster that prettify_outupt drops before output
    for column in ("MDLCODE_MC", "MDLCODE_ML", "CM_FLAG"):
        pm[column] = None
    return pm


def stock_tables(idx: pd.Index, pm: pd.DataFrame, demand) -> SimpleNamespace:
    """Old handle_inventory + get_stock_tables / get_stock_age / get_extended_stock,
    on a full grid parts x snapshot months (no row on a month's last snapshot = no stock)."""
    months = parts_data.stock_months()
    rows = parts_data.stock(list(idx))
    grid = pd.MultiIndex.from_product([months, idx], names=["DATE", "PTS_NO"])
    inventory = (rows.set_index(["DATE", "PTS_NO"])[["AVAILABLE", "INCOMING", "ORDERED"]]
                 .reindex(grid, fill_value=0).astype(float))
    stock = SimpleNamespace(inventory=inventory.reset_index())
    stock.avl = inventory["AVAILABLE"].replace({0: np.nan}).unstack("DATE")        # parts x months, as before
    stock.age = frames.get_stock_age(parts_data.initial_stock_age(list(idx)), stock.avl)
    stock.last_time_avl = frames.last_time_on_stock(stock.avl)
    extended = frames.get_extended_stock(stock, SimpleNamespace(partsmaster=pm), demand)
    stock.current = frames.filter_latest(model.stock_health(extended))
    return stock


def prices(idx: pd.Index, pm: pd.DataFrame) -> SimpleNamespace:
    """Cost per month (uframe.handle_prices, as in the sales report) + the latest prices.
    CPD Net Price has no source: empty column. HCMR Buy Rate is a fixed coefficient,
    HCMR_BUY_RATE of the local .env."""
    source = Prices()
    source.cost_rub = parts_data.unit_cost_rub(list(idx))
    source.usd_rate = legacy.usd_rate()
    cost = handle_prices(source, Prices()) if len(source.cost_rub) else None
    empty = pd.DataFrame(columns=["PTS_NO", "DATE", "DATE_YM"])
    cost_rub = cost.cost_rub if cost is not None else empty.assign(COST_RUB=[])
    cost_usd = cost.cost_usd if cost is not None else empty.assign(COST_USD=[])

    def latest(frame, column):
        frame = frame.dropna(subset=[column])
        frame = frame[frame["DATE"] >= frame["DATE"].max()] if len(frame) else frame
        return frame.drop_duplicates("PTS_NO", keep="last").set_index("PTS_NO")[column]

    recent = pd.concat([latest(cost_rub, "COST_RUB"), latest(cost_usd, "COST_USD")], axis=1).reindex(idx)
    recent = recent.join(parts_data.latest_prices(list(idx)).set_index("PTS_NO"))
    recent["DLP"] = pm.set_index("PTS_NO")["DLP"]
    recent["DNP_CPD_USD"] = np.nan                   # no source (keep, empty)
    recent = recent.astype(float).fillna(0).round(2)
    rate = current_app.config.get("HCMR_BUY_RATE", np.nan)
    recent["BUY_RATE"] = "-" if pd.isna(rate) else rate     # after round(2): a rate with 3 decimals is kept as is
    recent.index.name = "PTS_NO"
    start = (pd.Timestamp("today") - pd.DateOffset(months=SHOW_MONTHS)).strftime("%Y-%m-01")
    monthly = parts_data.monthly_purchase_prices(list(idx), start)
    return SimpleNamespace(recent_prices=recent.reset_index(), cost_rub=cost_rub, cost_usd=cost_usd, monthly=monthly)


def demand_model(pnls: list[str], today: pd.Timestamp, pm: pd.DataFrame) -> SimpleNamespace:
    config = current_app.config
    rows = parts_data.demand(demand_groups(), config["DEMAND_START"], pnls)
    matrix = model.demand_matrix(rows, config["DEMAND_START"], today)
    stop_flags = pm.set_index("PTS_NO")["STOP_FLAG"]
    return SimpleNamespace(
        m=matrix,
        rank_table=model.rank_table(matrix),
        stats=model.demand_stats(rows, matrix, config["DEMAND_WEIGHTS"], stop_flags, today),
        # PERF: get_demand_age filters the rows once per month since 2022-09 (O(months x rows)). The same
        # table in one pass: monthly max of LAST_ORDER per PNL, reindexed to the month grid, cummax along
        # the months, then (month_end - last) / 360 days.
        age=frames.get_demand_age(model.demand_age_frame(rows)) if len(rows) else pd.DataFrame(),
    )


def process(part_numbers: list[str]) -> tuple:
    """The answer of /processing: (datatable, overview, breakdown) for the requested parts."""
    idx = pd.Index(sorted({str(p).strip() for p in part_numbers if str(p).strip()}))
    today = pd.Timestamp("today").normalize()
    pm = parts_master(idx)
    demand = demand_model(pm["PNL"].unique().tolist(), today, pm)
    stock = stock_tables(idx, pm, demand)
    price = prices(idx, pm)
    shown = pm.assign(PCLASS=pm["PCLASS"].replace(DISPLAY_CLASS))
    return prettify_output(idx, shown, price, demand, stock, legacy.usd_rate())


def json_frame(frame: pd.DataFrame) -> pd.DataFrame:
    return frame.astype(object).where(frame.notna(), None)        # JSON null, not NaN


def supersession_tree(part: str) -> dict | None:
    """The chain of a part as a tree (Supersessions tab): the chain head at the root, every
    number under the number it leads to (leads_to); link / icc say how (data/parts.py). A number
    whose step does not reach the head in the chain hangs under the head, so that no number is lost, with
    outside: "chain" (leads out of it), "none" (no step of its own) or "loop" (a loop without
    the head); the head has outside "chain" when it leads on to another chain. None: unknown part."""
    family = json_frame(parts_data.supersession_family(part))
    if family.empty:
        return None
    head = family["PNL"].iloc[0]
    nodes = {row.PTS_NO: {"part_number": row.PTS_NO, "description": row.DESCR, "link": row.LINK,
                          "icc": row.ICC, "tnved": row.TNVED, "primary_vendor": row.VENDOR,
                          "leads_to": row.PARENT, "outside": None, "children": []} for row in family.itertuples()}
    parent = {row.PTS_NO: row.PARENT for row in family.itertuples() if row.PTS_NO != head}
    done = {head}                           # numbers that reach the head
    for start in sorted(parent):
        path, number = set(), start
        while number not in done:
            target = parent[number]
            if target not in nodes or number in path:
                nodes[number]["outside"] = "loop" if number in path else "none" if target is None else "chain"
                parent[number] = head
                break
            path.add(number)
            number = target
        done |= path | {start}
    for number in sorted(parent):
        nodes[parent[number]]["children"].append(nodes[number])
    root = nodes[head]
    if root["leads_to"] is not None and root["leads_to"] not in nodes:
        root["outside"] = "chain"
    else:                                   # in a cycle the head leads on as well: it stays the root
        root.update(link=None, icc=None, leads_to=None)
    return root


def order_summary(frame: pd.DataFrame) -> dict:
    """The line above an order table: all of the part's orders, whatever the table filters show.
    A row is an order and invoice, so an order with several invoices counts once."""
    dates = frame["Order date"].dropna()                # 'YYYY-MM-DD': min / max as text are the dates
    return {"qty": float(frame["Qty"].sum()), "orders": int(frame["Order number"].nunique()),
            "first": dates.min() if len(dates) else None, "last": dates.max() if len(dates) else None}


def average_gross_profit(daily: pd.DataFrame, part: str) -> float | None:
    """Mean gross profit margin of the part's invoiced sales orders (the mean of
    the orders' margins, not total profit / total sales), from the Sales report's daily and by
    its rule: since GROSS_PROFIT_START, grouped by purchase order and vendor as its chart does.
    None: no invoice with sales of that time."""
    lines = daily[(daily["PTS_NO"] == part) & (daily["SO_INV_DATE"] >= GROSS_PROFIT_START)
                  & daily["SO_INVOICE"].notna()]
    # PERF: a boolean mask over the whole daily (~600k rows) per request; the sales state could
    #   keep the invoiced lines grouped by PTS_NO once (daily.groupby("PTS_NO").indices)
    lines = (lines.groupby(["SO_NUM", "SO_INVOICE", "PO_NUM", "VND_NAME"], dropna=False)
             [["SA_USD", "PA_USD", "CA_USD"]].sum().round(2).reset_index())
    lines["GP_USD"] = gross_profit_usd(lines)
    by_order = lines.groupby(["SO_NUM", "SO_INVOICE"])[["SA_USD", "GP_USD"]].sum()
    by_order = by_order[by_order["SA_USD"] != 0]              # a margin of no sales has no meaning
    return float((by_order["GP_USD"] / by_order["SA_USD"]).mean()) if len(by_order) else None


def orders(part: str, sales_daily: pd.DataFrame | None) -> dict:
    """The sales and purchase orders of a part (Orders tab): per kind the report table
    ({columns, data}) and its summary. sales_daily: None while the Sales report is being built,
    the gross profit is left out then."""
    sales, purchase = parts_data.sales_orders(part), parts_data.purchase_orders(part)
    return {"sales": {"table": json_frame(sales).to_dict(orient="split", index=False),
                      "summary": order_summary(sales)
                      | {"gross_profit": None if sales_daily is None else average_gross_profit(sales_daily, part)}},
            "purchase": {"table": json_frame(purchase).to_dict(orient="split", index=False),
                         "summary": order_summary(purchase) | {"available": parts_data.available_now(part)}}}
