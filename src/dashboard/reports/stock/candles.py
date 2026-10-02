"""Weekly candlestick of the main warehouse (D4.4).

Port of uframe.get_data_for_candels + ucharts.candle_stock_chart (the chart was
removed in D4.2 with the dead duplicates of ucharts and restored here):
* a candle per week: the value of the available stock on the first / lowest /
  highest / last snapshot of the week; it opens at the previous week's close;
* incoming and ordered stock at the end of the week;
* dispatched from the stock locations (cost of the invoiced lines, by dealer
  group) and arrived (PO amount by arrival date, by supplier).
The four panels share a period selection (drag on the candles).

Main warehouse only: the second warehouse has one snapshot a
month, too coarse for weekly candles. Values follow valuation.py. The
group and supplier columns come from the data: the old chart listed real codes
in its tooltips.
"""

import altair as alt
import pandas as pd

from dashboard.reports.common.chart_theme import ACCENT, ACCENT_LIGHT, FULL_CARD, MONTH_FORMAT, NEUTRAL_DARK, money, themed

WEEKS = 52
TOP_SUPPLIERS = 6                       # the rest of the suppliers are summed as OTHERS
SCALES = {"USD": 10**6, "RUB": 10**9}    # USD in millions, RUB in billions (one format for all charts)


def weekly_candles(daily_amounts: pd.DataFrame, currency: str) -> pd.DataFrame:
    days = daily_amounts.set_index("DATE")
    available = days[f"AVAILABLE_{currency}_AMT"] / SCALES[currency]
    weeks = available.resample("W").agg(["first", "min", "max", "last", "mean"])
    weeks.columns = ["OPEN", "MIN", "MAX", "CLOSE", "AVG"]
    weeks["INC"] = (days[f"INCOMING_{currency}_AMT"] / SCALES[currency]).resample("W").last()
    weeks["ORD"] = (days[f"ORDERED_{currency}_AMT"] / SCALES[currency]).resample("W").last()
    weeks = weeks.dropna(subset=["CLOSE"])
    weeks["OPEN"] = weeks["CLOSE"].shift()       # as the old code: a week opens at the last close
    return weeks.iloc[1:].tail(WEEKS).round(2)


def weekly_dispatched(daily: pd.DataFrame, currency: str) -> pd.DataFrame:
    """Cost of the lines invoiced to the stock locations, per week and dealer group."""
    rows = daily[daily["IS_STOCK_LOCATION"].eq(True) & daily["SO_INV_DATE"].notna()]
    table = (rows.groupby([pd.Grouper(key="SO_INV_DATE", freq="W"), "DLR_META"])[f"CA_{currency}"].sum()
             .unstack("DLR_META").fillna(0) / SCALES[currency]).round(3)
    table.index.name = "DATE"
    table["SOLD_AMT"] = table.sum(axis=1)
    return table


def weekly_arrived(daily: pd.DataFrame, rates: pd.Series, currency: str) -> pd.DataFrame:
    """PO amount by arrival date and supplier (old: PA_USD by ARRIVE_DATE, VND_NAME)."""
    rows = daily[daily["ARRIVE_DATE"].notna()].copy()
    rows["AMOUNT"] = rows["PA_USD"].astype(float)
    if currency == "RUB":
        rows["AMOUNT"] *= (rows["ARRIVE_DATE"] + pd.offsets.MonthEnd(0)).map(rates.resample("ME").mean())
    top = rows.groupby("VND_NAME")["AMOUNT"].sum().nlargest(TOP_SUPPLIERS).index
    rows["VND_NAME"] = rows["VND_NAME"].where(rows["VND_NAME"].isin(top), "OTHERS")
    table = (rows.groupby([pd.Grouper(key="ARRIVE_DATE", freq="W"), "VND_NAME"])["AMOUNT"].sum()
             .unstack("VND_NAME").fillna(0) / SCALES[currency]).round(3)
    table.index.name = "DATE"
    table["ARRIVED_AMT"] = table.sum(axis=1)
    return table


def candle_frame(daily_amounts, daily, rates, currency):
    candles = weekly_candles(daily_amounts, currency)
    sold = weekly_dispatched(daily, currency)
    arrived = weekly_arrived(daily, rates, currency)
    frame = candles.join(sold).join(arrived).fillna(0).reset_index()
    return frame, [c for c in sold.columns if c != "SOLD_AMT"], [c for c in arrived.columns if c != "ARRIVED_AMT"]


def candle_chart(frame: pd.DataFrame, groups: list[str], suppliers: list[str], currency: str) -> dict:
    """ucharts.candle_stock_chart, with the tooltips built from the columns of the frame."""
    unit = money(currency)
    number = ",.2f"
    x = alt.X("DATE:T", axis=alt.Axis(labelAngle=-45, title=None, format=MONTH_FORMAT))
    period = alt.selection_interval(encodings=["x"])
    rising = alt.condition("datum.OPEN <= datum.CLOSE", alt.value(ACCENT), alt.value(NEUTRAL_DARK))
    base = alt.Chart(frame)

    body = base.mark_bar(size=8).encode(
        x, alt.Y("OPEN:Q", scale=alt.Scale(zero=False, clamp=True), title=unit), alt.Y2("CLOSE:Q"),
        color=rising,
        tooltip=[alt.Tooltip("DATE:T", title="week")]
                + [alt.Tooltip(f"{c}:Q", format=number) for c in ("OPEN", "MIN", "AVG", "MAX", "CLOSE")])
    wick = base.mark_rule().encode(x, alt.Y("MIN:Q", scale=alt.Scale(zero=False)), alt.Y2("MAX:Q"), color=rising)

    def area(column, title):
        return (base.mark_area(fill=ACCENT_LIGHT, fillOpacity=0.35, stroke=ACCENT, strokeWidth=1,
                               interpolate="step")
                .encode(x, alt.Y(f"{column}:Q", title=unit),
                        tooltip=[alt.Tooltip("DATE:T", title="week"), alt.Tooltip(f"{column}:Q", format=number)])
                .properties(title=title, width=320, height=170).transform_filter(period))

    def bars(total, columns, color, title):
        return (base.mark_bar(color=color)
                .encode(x, alt.Y(f"{total}:Q", title=unit),
                        tooltip=[alt.Tooltip("DATE:T", title="week"), alt.Tooltip(f"{total}:Q", format=number)]
                                # field=, not "name:Q": a supplier name with ":" or "." would break the shorthand
                                + [alt.Tooltip(field=c, type="quantitative", format=number) for c in columns])
                .properties(title=title, width=544, height=170).transform_filter(period))

    candles = ((body + wick)
               .properties(title=f"Available stock, main warehouse, weekly ({unit})", width=767, height=450)
               .add_params(period))
    chart = alt.vconcat(
        alt.hconcat(candles, alt.vconcat(area("INC", "Incoming (end of week)"),
                                         area("ORD", "Ordered (end of week)"))),
        alt.hconcat(bars("SOLD_AMT", groups, NEUTRAL_DARK, "Dispatched from the stock locations (cost)"),
                    bars("ARRIVED_AMT", suppliers, ACCENT, "Arrived (PO amount)"))
        .resolve_scale(y="shared"))
    return {"name": f"candles_{currency.lower()}_chart", "chart": themed(chart, FULL_CARD)}
