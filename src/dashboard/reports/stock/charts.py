"""Charts of the stock report, designed for a half-width card (D4.4).

Replace ucharts.inventory_overview_chart_new / available_rank_pclass_chart_new,
which were drawn for a full-screen page (1080 px wide, a label on every bar
segment, legends inside the plot). Same content, less ink:
* one label per bar (the total); the segments are in the tooltip;
* legends above the plot; small, left-aligned titles; months as "Aug 25";
* the rows of a chart add up to the same width, so the card does not overflow.

The common look (fonts, colours, legend, design width): reports/common/chart_theme.py.
"""

import altair as alt
import pandas as pd

from dashboard.reports.common.chart_theme import (ACCENT, ACCENT_LIGHT, BAR_BAND, DASH, LABEL_SIZE,
                                                   LINE_POINT, MONTH, NEUTRAL, NEUTRAL_LIGHT, ORANGE, PANEL_HEIGHT,
                                                   PLOT_HEIGHT, SECONDARY, TICK_COUNT, TITLE_COLOR, WIDTH,
                                                   legend_selection, money, month_tooltip, themed)

def with_month(frame: pd.DataFrame) -> pd.DataFrame:
    """DATE (month end) from the "2026-M06" labels, for the time axis."""
    frame = frame.copy()
    frame["DATE"] = pd.to_datetime(frame["DATE_YM"].str.replace("-M", "-")) + pd.offsets.MonthEnd(0)
    return frame


def stacked_with_total(frame, value, color, legend_title, colors, order, width, height, title, y_title,
                       label_format=".1f", tooltip_extra=(), totals=True, y_max=None, selection=None):
    """selection: (param, opacity) of an interactive legend; the chart that owns the
    legend adds the param, the others (small panels) only follow it."""
    x = alt.X("yearmonth(DATE):O", axis=MONTH)
    base = alt.Chart(frame)
    scale = alt.Scale(domain=[0, y_max]) if y_max else alt.Scale()
    bars = base.mark_bar(width={"band": BAR_BAND}).encode(
        x, alt.Y(f"sum({value}):Q", title=y_title, scale=scale, axis=alt.Axis(orient="right", tickCount=TICK_COUNT)),
        color=alt.Color(f"{color}:N", scale=alt.Scale(range=colors),
                        legend=alt.Legend(title=legend_title) if legend_title else alt.Legend()),
        order=alt.Order(f"{color}:N", sort=order),
        tooltip=[month_tooltip("DATE"),
                 alt.Tooltip(f"{color}:N"), alt.Tooltip(f"sum({value}):Q", title=y_title or "amount", format=",.2f"),
                 *tooltip_extra])
    if selection is not None:
        bars = bars.encode(opacity=selection[1])
    total = base.mark_text(dy=-6, fontSize=LABEL_SIZE, color=TITLE_COLOR).encode(
        x, alt.Y(f"sum({value}):Q"), text=alt.Text(f"sum({value}):Q", format=label_format))
    return (bars + total if totals else bars).properties(width=width, height=height, title=title)


def overview_chart(summary: pd.DataFrame, currency: str, warehouses: tuple[str, str]) -> dict:
    """Stock by kind (bars, right axis) and the USD/RUB rate (line, left axis); below,
    months on hand and the rolling sales of the stock locations."""
    scale = 10**6 if currency == "USD" else 10**9
    unit = money(currency)
    kinds = {f"AVAILABLE_{currency}_AMT": f"1. {warehouses[0]}", f"NVK_{currency}_AMT": f"2. {warehouses[1]}",
             f"INCOMING_{currency}_AMT": "3. In transit", f"ORDERED_{currency}_AMT": "4. On order"}
    long = (summary.melt(id_vars=["DATE"], value_vars=list(kinds), var_name="KIND", value_name="AMOUNT")
            .assign(KIND=lambda f: f["KIND"].map(kinds), AMOUNT=lambda f: f["AMOUNT"] / scale))
    # two bands, as the old chart meant: the bars in the lower ~70 %, the rate line above them
    top_total = long.groupby("DATE")["AMOUNT"].sum().max()
    low, high = summary["RATE_AVG"].min(), summary["RATE_AVG"].max()
    spread = max(high - low, 1.0)
    kind = legend_selection("KIND")
    stock = stacked_with_total(long, "AMOUNT", "KIND", None, [ACCENT, ACCENT_LIGHT, NEUTRAL, NEUTRAL_LIGHT],
                               "ascending", WIDTH, PLOT_HEIGHT, "Stock by kind; USD/RUB rate (line)",
                               unit, y_max=float(top_total) * 1.45, selection=kind).add_params(kind[0])
    rate = alt.Chart(summary).mark_line(color=SECONDARY, strokeDash=DASH, point=LINE_POINT).encode(
        alt.X("yearmonth(DATE):O", axis=MONTH),
        alt.Y("RATE_AVG:Q", title="USD/RUB", scale=alt.Scale(domain=[float(low - 3.2 * spread), float(high + 0.3 * spread)]),
              axis=alt.Axis(orient="left", titleColor=SECONDARY, tickCount=4)),
        tooltip=[month_tooltip("DATE"),
                 alt.Tooltip("RATE_AVG:Q", title="USD/RUB (avg)", format=".2f")])
    top = alt.layer(stock, rate).resolve_scale(y="independent")

    small = (WIDTH - 60) // 2
    moh = alt.Chart(summary).encode(alt.X("yearmonth(DATE):O", axis=MONTH))
    moh = (moh.mark_bar(color=ACCENT, width={"band": BAR_BAND}).encode(alt.Y("MOH:Q", title="months"))
           + moh.mark_text(dy=-6, fontSize=LABEL_SIZE).encode(alt.Y("MOH:Q"), text=alt.Text("MOH:Q", format=".0f"))
           ).properties(width=small, height=PANEL_HEIGHT, title="Months on hand")
    sales = summary.assign(SALES=summary["INVOICED_ROLLING"] / scale)
    sales = alt.Chart(sales).encode(alt.X("yearmonth(DATE):O", axis=MONTH))
    sales = (sales.mark_bar(color=NEUTRAL, width={"band": BAR_BAND}).encode(alt.Y("SALES:Q", title=unit))
             + sales.mark_text(dy=-6, fontSize=LABEL_SIZE).encode(alt.Y("SALES:Q"), text=alt.Text("SALES:Q", format=".2f"))
             ).properties(width=small, height=PANEL_HEIGHT, title="Sales of the stock locations, 12-month mean")
    return {"name": f"overview_{currency.lower()}_chart", "chart": themed(top & (moh | sales))}


CLASSES = {"C": "Construction", "CM": "Common (C/M)", "M": "Mining"}


def rank_chart(by_rank: pd.DataFrame, currency: str) -> dict:
    """Available stock by demand rank; below, the same for each product class."""
    scale = 10**6 if currency == "USD" else 10**9
    unit = money(currency)
    frame = with_month(by_rank.rename(columns={"Product Class": "PCLASS", "Rank": "RANK"}))
    frame["PCLASS"] = frame["PCLASS"].replace({"OTHER": "M", "TBD": "M", "-": "M"})    # as the old chart
    frame["AMOUNT"] = frame["AMOUNT"] / scale
    months = sorted(frame["DATE"].unique())[-11:]
    frame = frame[frame["DATE"].isin(months)]
    rank = legend_selection("RANK")
    top = stacked_with_total(frame, "AMOUNT", "RANK", "Demand rank", ORANGE, "descending", WIDTH, PLOT_HEIGHT,
                             "Available stock by demand rank", unit, selection=rank).add_params(rank[0])
    small = (WIDTH - 100) // 3
    panels = [stacked_with_total(frame[frame["PCLASS"] == code], "AMOUNT", "RANK", None, ORANGE, "descending",
                                 small, PANEL_HEIGHT, title, "", totals=False, selection=rank)   # 11 labels would not fit
              for code, title in CLASSES.items()]
    return {"name": f"rank_{currency.lower()}_chart", "chart": themed(top & alt.hconcat(*panels))}
