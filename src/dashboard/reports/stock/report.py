"""Parts stock report: state built from the warehouse (D4.4).

The old app.py never ran on its last version (stock.inventory was never set,
get_stock_sum read a DATE column that is the index, the route expected *_AMT
columns that nothing created). The report is rebuilt from its charts: the stock
of both warehouses at every month end, valued (valuation.py), against the sales
of the stock locations; available stock by demand rank and product class.
The charts are drawn by charts.py and candles.py (ucharts' versions were made
for a full-screen page; these fit two charts a row).
"""

from dataclasses import dataclass, field

import pandas as pd
from flask import current_app

from dashboard.data import legacy
from dashboard.data import stock as stock_data
from dashboard.reports.common.daily import cost_prices, demand_ranks, prepared_daily
from dashboard.reports.common.groups import with_mining_suppliers
from dashboard.reports.common.top_parts import TopParts, top_parts

from . import candles, charts, valuation

NAME = "stock"
YM = "%Y-M%m"
HISTORY_MONTHS = 13            # 11 months on the charts + the month before, and the 53 weeks of the candles
SHOWN_MONTHS = 11
CURRENCIES = {"USD": ("$", 10**6, "M"), "RUB": ("₽", 10**9, "B")}


@dataclass
class StockState:
    today: pd.Timestamp
    last_month: pd.Timestamp
    summaries: dict                     # currency -> monthly totals (valuation.monthly_summary)
    plates: dict                        # currency -> [{"label", "value", "change", "color"}] x 3
    charts: dict = field(default_factory=dict)   # "overview_USD", "rank_RUB", ... -> {"name", "chart"}
    top_parts: TopParts | None = None


def month_costs() -> pd.DataFrame:
    """Unit cost per part and month, USD and RUB: uframe.handle_prices on the warehouse,
    as the sales report values its sales (the reference). One row per part and
    month (the cost table has one row per warehouse)."""
    price = cost_prices()
    usd = price.cost_usd.groupby(["PTS_NO", "DATE_YM"])["COST_USD"].max()
    rub = price.cost_rub.groupby(["PTS_NO", "DATE_YM"])["COST_RUB"].max()
    return pd.concat([usd, rub], axis=1).reset_index()


def priced_stock(start: str) -> pd.DataFrame:
    """Every month end and part with stock: quantities, the valuation prices, rank, class."""
    frame = with_mining_suppliers(stock_data.stock_values(start))
    frame["PCLASS"] = frame["PCLASS"].fillna("-")
    frame["DATE_YM"] = frame["DATE"].dt.strftime(YM)
    frame = frame.merge(month_costs(), on=["PTS_NO", "DATE_YM"], how="left")
    rates = legacy.usd_rate().set_index("DATE")["CURRENCY_RATE"].astype(float)
    frame["RATE"] = frame["DATE"].map(rates.resample("ME").mean())
    keys = pd.MultiIndex.from_arrays([frame["DATE_YM"], frame["PNL"]])
    # demand_ranks(), cost_prices() and prepared_daily() are shared with the sales build (reports/shared.py)
    frame["RANK"] = keys.map(demand_ranks()).fillna("F")
    return frame


def stock_location_sales(daily: pd.DataFrame) -> pd.DataFrame:
    """Old get_stock_sum: invoiced sales of the stock locations per month, from the shared
    daily (cancelled lines already out, as in the sales report)."""
    rows = daily[daily["IS_STOCK_LOCATION"].eq(True) & daily["SO_INV_DATE"].notna()]
    sales = rows.groupby(pd.Grouper(key="SO_INV_DATE", freq="ME"))[["SA_USD", "SA_RUB"]].sum()
    return sales.rename_axis("DATE").reset_index()


def plates(summary: pd.DataFrame, currency: str) -> list[dict]:
    """The three tiles: last month's available / incoming / ordered and the change."""
    sign, scale, unit = CURRENCIES[currency]
    tiles = []
    for label, kind in (("Available", "AVAILABLE"), ("Incoming", "INCOMING"), ("Ordered", "ORDERED")):
        values = summary[f"{kind}_{currency}_AMT"]
        change = values.iloc[-1] / values.iloc[-2] - 1 if len(values) > 1 and values.iloc[-2] else 0.0
        tiles.append({"label": label,
                      "value": f"{sign}{values.iloc[-1] / scale:,.2f} {unit}",
                      "change": f"{'+' if change >= 0 else '-'} {abs(change):.1%}",
                      "color": "success" if change >= 0 else "danger"})
    return tiles


def build() -> StockState:
    today = pd.Timestamp("today").normalize()
    last = stock_data.last_snapshot_date()                 # the periods end at the data, not at today
    start = (last - pd.DateOffset(months=HISTORY_MONTHS)).strftime("%Y-%m-01")
    frame = priced_stock(start)
    markup = current_app.config.get("NVK_FALLBACK_MARKUP", 0.0)
    amounts = valuation.stock_amounts(frame, markup)
    daily = prepared_daily()
    sales = stock_location_sales(daily)
    rates = legacy.usd_rate().set_index("DATE")["CURRENCY_RATE"].astype(float)
    prices = valuation.unit_prices(frame, markup).join(frame[["PTS_NO", "DATE"]])
    days = stock_data.daily_amounts(prices, start=str((last - pd.DateOffset(weeks=candles.WEEKS + 2)).date()),
                                    end=str(last.date()))

    state = StockState(today=today, last_month=amounts["DATE"].max(), summaries={}, plates={})
    # TOP-10 on free stock now: the main warehouse's available at the last snapshot, valued as
    # the charts (valuation.py); the last month end of the frame is the last snapshot
    now = amounts[amounts["DATE"] == state.last_month]
    state.top_parts = top_parts(now[["PTS_NO", "AVAILABLE", "AVAILABLE_USD_AMT"]]
                                .rename(columns={"AVAILABLE": "QTY", "AVAILABLE_USD_AMT": "AMOUNT"}),
                                f"{last:%Y-%m-%d}")
    for currency in CURRENCIES:
        summary = valuation.monthly_summary(amounts, sales, rates, currency)
        state.summaries[currency] = summary
        state.plates[currency] = plates(summary, currency)
        names = tuple(current_app.config["STOCK_WAREHOUSE_NAMES"])
        state.charts[f"overview_{currency}"] = charts.overview_chart(summary.iloc[-SHOWN_MONTHS:, :], currency, names)
        state.charts[f"rank_{currency}"] = charts.rank_chart(valuation.available_by_rank(amounts, currency), currency)
        weekly, groups, suppliers = candles.candle_frame(days, daily, rates, currency)
        state.charts[f"candles_{currency}"] = candles.candle_chart(weekly, groups, suppliers, currency)
    return state
