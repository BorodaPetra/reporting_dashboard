"""Charts of the sales report, redrawn for two charts a row (after D4.4).

Moved from ucharts (show_fy_sales_chart, show_outstanding_orders_chart,
show_group_sales_breakdown_chart, show_gross_profit_chart,
show_detailed_sales_chart_new). The data preparation of each function is
unchanged; the pictures follow reports/common/chart_theme.py:
* amounts in M USD with one decimal, so a label fits above a bar in a half-width
  card (the tables keep K USD); exact values in the tooltips;
* one label per bar; a second series (margin, accumulated sales) keeps to its
  own band or axis instead of writing over the bars;
* the dealer selector is a compact row of buttons; legends right-aligned.
Fixed on the way: the gross profit used hard-coded warehouse labels to tell the
stock locations (they come from DEALER_WAREHOUSE_LABELS now).
"""

import altair as alt
import numpy as np
import pandas as pd

from dashboard.reports.common.chart_theme import (ACCENT, AMBER_LIGHT, BAR_BAND, BLUE, BLUE_DEEP, BOLD, BUTTON_LABEL_SIZE,
                                                   BUTTON_OFF, CONCAT_SPACING, DASH, FULL_CARD, GOLD, GREEN_BRIGHT,
                                                   GREEN_SOFT, GROUPS, LABEL_SIZE, LINE_POINT, MONTH, MONTH_FORMAT,
                                                   NEUTRAL, NEUTRAL_DARK, NEUTRAL_LIGHT, ORANGE, PLOT_HEIGHT, SECONDARY,
                                                   TEAL_LIGHT, TICK_COUNT, TITLE_COLOR, WHITE, WIDTH, legend_selection,
                                                   money, month_tooltip, themed)
from dashboard.reports.common.daily import GROSS_PROFIT_START
from dashboard.reports.common.groups import breakdown_group, breakdown_subgroups, report_groups, warehouse_labels

MLN = ",.1f"
USD = money("USD")                      # the y-axis title of every amount: the unit only
# spacing under the dealer buttons of a chart without a legend: concat spacing (24) + the legend row of
# the FY chart (31 px, measured in the rendered Vega scenegraph), so the plots of both charts start level
LEGEND_ROW = 55


def dealer_selector(frame: pd.DataFrame, field: str, default) -> tuple:
    """A row of buttons (one per dealer group, the name on the button): click to show
    one group in the chart below. The selection filters the other charts by value."""
    selection = alt.selection_point(fields=[field], value=default, empty=False, nearest=True)
    # "ALL" first on every chart (stable sort: the groups keep their order behind it)
    names = pd.DataFrame({field: sorted(frame[field].drop_duplicates(), key=lambda name: name != "ALL")})
    base = alt.Chart(names).encode(alt.X(f"{field}:N", axis=None, sort=None))      # small: 40 x 18 px
    button = base.mark_bar(cornerRadius=3).encode(
        color=alt.condition(selection, alt.value(ACCENT), alt.value(BUTTON_OFF))).add_params(selection)
    name = base.mark_text(fontSize=BUTTON_LABEL_SIZE, fontWeight=BOLD).encode(
        text=f"{field}:N", color=alt.condition(selection, alt.value(WHITE), alt.value(TITLE_COLOR)))
    return selection, alt.layer(button, name).properties(width=alt.Step(40), height=18)


def two_axes(left_layers, right_layers, selection=None):
    """Bars (+ their labels) on the left axis, a line (+ labels) on the right one. Explicit
    nesting: with a flat layer ("a + b + c") an independent y gives every layer its own
    scale, and the labels no longer sit on their bars. The filter goes on every chart: a
    filter on a layer reaches only the charts that share the layer's data."""
    if selection is not None:
        left_layers = [chart.transform_filter(selection) for chart in left_layers]
        right_layers = [chart.transform_filter(selection) for chart in right_layers]
    return alt.layer(alt.layer(*left_layers), alt.layer(*right_layers)) \
        .resolve_scale(y="independent", color="independent")


def x_month(field: str) -> alt.X:
    return alt.X(f"yearmonth({field}):O", axis=MONTH)


# ---- FY sales performance -------------------------------------------------------------------

def show_fy_sales_chart(fy_sales_frame):
    fy_sales_frame = fy_sales_frame.round(2).replace({0: np.nan})
    # the old code also joined a "Predicted" flag with pd.concat on an index with repeated keys:
    # the flag was never drawn, and the join doubled the rows (sums on labels were twice the bars)
    src = (fy_sales_frame.sort_index(axis=1, level=1, sort_remaining=False).stack(future_stack=True).stack(future_stack=True).dropna().to_frame("Amount_USD").reset_index()
           .rename(columns={"level_0": "Month"}))
    fyfunc = lambda x: x.year if x.month > 3 else x.year - 1          # noqa: E731
    cfy = f"FY{str(fyfunc(pd.Timestamp('today')))[-2:]}"
    pfy = f"FY{str(fyfunc(pd.Timestamp('today')) - 1)[-2:]}"
    src["Type"] = src["Type"].replace({"sma_pfy": f"{pfy} accumulated", "bma_resid": f"{cfy} budget",
                                       "sma_cfy": f"{cfy} accumulated", "sm_cfy": "Sales", "fm": "Forecast"})
    src["Amount"] = src["Amount_USD"] / 1000                            # K USD -> M USD
    lines_src = src[src["Type"].isin([f"{cfy} budget", f"{pfy} accumulated", f"{cfy} accumulated"])]
    selection, buttons = dealer_selector(src, "DLR", src["DLR"][0])
    tooltip = [month_tooltip("Month"), alt.Tooltip("Type:N"),
               alt.Tooltip("Amount:Q", title=USD, format=",.2f")]
    bar_legend, line_legend = legend_selection("Type"), legend_selection("Type")

    monthly = src[src["Type"].isin(["Sales", "Forecast"])]
    bars = alt.Chart(monthly).mark_bar(width={"band": BAR_BAND}).encode(
        x_month("Month"), alt.XOffset("Type:N", sort=["Forecast", "Sales"]),
        alt.Y("sum(Amount):Q", title=USD, axis=alt.Axis(orient="left", tickCount=TICK_COUNT)),
        color=alt.Color("Type:N", scale=alt.Scale(domain=["Forecast", "Sales"], range=[NEUTRAL_LIGHT, ACCENT])),
        opacity=bar_legend[1], tooltip=tooltip).add_params(bar_legend[0])
    labels = alt.Chart(monthly[monthly["Type"] == "Sales"]).mark_text(dy=-6, fontSize=LABEL_SIZE, color=ACCENT).encode(
        x_month("Month"), alt.XOffset("Type:N", sort=["Forecast", "Sales"]),
        alt.Y("sum(Amount):Q"), text=alt.Text("sum(Amount):Q", format=MLN))
    line_types = sorted(lines_src["Type"].unique())          # the default (sorted) domain of the color scale
    line_base = alt.Chart(lines_src).encode(
        x_month("Month"),
        alt.Y("Amount:Q", title=USD, axis=alt.Axis(orient="right", tickCount=TICK_COUNT)),
        alt.Color("Type:N", scale=alt.Scale(range=[GOLD, GREEN_SOFT, BLUE])),
        opacity=line_legend[1], tooltip=tooltip)
    # the budget is a plan, not a fact: dashed. The points are a layer of their own: the
    # point overlay of mark_line would take the dash for its circles too
    lines = line_base.mark_line(strokeWidth=2, interpolate="monotone").encode(
        strokeDash=alt.StrokeDash("Type:N", legend=None, scale=alt.Scale(
            domain=line_types, range=[DASH if t == f"{cfy} budget" else [1, 0] for t in line_types]))
    ).add_params(line_legend[0])
    points = line_base.mark_point(**LINE_POINT, size=30)
    plot = two_axes([bars, labels], [lines, points], selection).properties(width=WIDTH, height=PLOT_HEIGHT)
    spec = themed(alt.vconcat(buttons, plot))
    # the legends of the bars and of the lines in two rows: in one row they
    # were wider than a half-width card in a small window
    spec["config"]["legend"]["layout"]["top"]["direction"] = "vertical"
    return {"chart": spec, "table": None}


# ---- outstanding orders ---------------------------------------------------------------------

def show_outstanding_orders_chart(outstanding_orders):
    outstanding_orders = outstanding_orders.copy().rename(columns={"DATE": "Date"})
    src = (outstanding_orders.set_index("Date").stack(future_stack=True).dropna().to_frame().reset_index()
           .set_axis(["Date", "Dealer", "SalesAmount"], axis=1))
    src["Amount"] = src["SalesAmount"] / 1000
    selection, buttons = dealer_selector(src, "Dealer", src["Dealer"][len(src) - 1])
    base = alt.Chart(src).encode(x_month("Date"))
    bars = base.mark_bar(color=ACCENT, width={"band": BAR_BAND}).encode(
        alt.Y("sum(Amount):Q", title=USD, axis=alt.Axis(tickCount=TICK_COUNT)),
        tooltip=[month_tooltip("Date"), alt.Tooltip("Dealer:N"),
                 alt.Tooltip("sum(SalesAmount):Q", title="K USD", format=",.0f")])
    labels = base.mark_text(dy=-6, fontSize=LABEL_SIZE, color=TITLE_COLOR).encode(
        alt.Y("sum(Amount):Q"), text=alt.Text("sum(Amount):Q", format=MLN))
    plot = alt.layer(bars, labels).transform_filter(selection).properties(width=WIDTH, height=PLOT_HEIGHT)
    outstanding_orders["Date"] = outstanding_orders["Date"].dt.strftime("%Y-%m-%d")
    return {"chart": themed(alt.vconcat(buttons, plot)), "table": outstanding_orders.to_dict(orient="split")}


# ---- monthly sales of one group, by sub-group -------------------------------------------------

def show_group_sales_breakdown_chart(daily):
    """Monthly sales of one dealer group split into sub-groups of dealers.
    Group and sub-groups (label -> dealer codes) come from the environment:
    BREAKDOWN_GROUP, BREAKDOWN_SUBGROUPS."""
    src = daily[(daily["DLR_META"] == breakdown_group()) & (daily["SO_INV_DATE"] >= "2024-09")].copy()
    src["DLR_SUB"] = "Others"
    for label, dealer_codes in breakdown_subgroups().items():
        src["DLR_SUB"] = np.where(src["DLR_CODE"].isin(dealer_codes), label, src["DLR_SUB"])
    src["DLR_SUB"] = np.where(src["DLR_ORD_NUM"].str.contains("B"), "PlanB", src["DLR_SUB"])
    src = ((src.groupby([pd.Grouper(key="SO_INV_DATE", freq="ME"), "DLR_SUB"])["SA_USD"].sum() / 1000)
           .fillna(0).round(1).reset_index().set_axis(["Date", "DealerCodeGroup", "SalesAmount"], axis=1))
    src["Amount"] = src["SalesAmount"] / 1000
    base = alt.Chart(src).encode(x_month("Date"))
    sub_legend = legend_selection("DealerCodeGroup")
    bars = base.mark_bar(width={"band": BAR_BAND}).encode(
        alt.Y("sum(Amount):Q", title=USD, axis=alt.Axis(tickCount=TICK_COUNT)),
        alt.Color("DealerCodeGroup:N", scale=alt.Scale(range=[AMBER_LIGHT, NEUTRAL_LIGHT, ACCENT, GREEN_BRIGHT])),
        opacity=sub_legend[1],
        tooltip=[month_tooltip("Date"), alt.Tooltip("DealerCodeGroup:N"),
                 alt.Tooltip("SalesAmount:Q", title="K USD", format=",.0f")]).add_params(sub_legend[0])
    labels = base.mark_text(dy=-6, fontSize=LABEL_SIZE, color=TITLE_COLOR).encode(
        alt.Y("sum(Amount):Q"), text=alt.Text("sum(Amount):Q", format=MLN))
    chart = (bars + labels).properties(width=WIDTH, height=270)
    table = src.drop(columns=["Amount"]).set_index(["Date", "DealerCodeGroup"]).unstack() \
        .droplevel(level=0, axis=1).fillna(0).reset_index()
    table["Date"] = table["Date"].dt.strftime("%Y-%m-%d")
    return {"chart": themed(chart), "table": table.to_dict(orient="split")}


# ---- gross profit ---------------------------------------------------------------------------

def show_gross_profit_chart(daily):
    gg = daily[daily["SO_INV_DATE"] >= GROSS_PROFIT_START].copy()
    gg_grp = (gg.groupby([pd.Grouper(key="SO_INV_DATE", freq="ME"), "DLR_CODE", "DLR_META", "SO_INVOICE", "SO_NUM",
                          "DLR_ORD_NUM", "PO_NUM", "VND_NAME", "PTS_NO"], dropna=False)
              .agg({"DESCR": "last", "QTY": "sum", "SA_USD": "sum", "PA_USD": "sum", "CA_USD": "sum"})
              .reset_index())
    # sold from stock -> cost; direct orders -> purchase amount. The stock locations are
    # HCMR_WH and the warehouse labels of the environment (was: two hard-coded labels)
    stock_labels = ["HCMR_WH", *warehouse_labels().values()]
    gg_grp["DLR_USE_COST"] = np.where(gg_grp["VND_NAME"].isin(stock_labels), "Y", "N")
    gg_grp[["SA_USD", "PA_USD", "CA_USD"]] = gg_grp[["SA_USD", "PA_USD", "CA_USD"]].round(2)
    # PERF: the two list comprehensions below loop in Python over every invoice line; vectorised:
    #   gg_grp["GP_USD"] = gg_grp["SA_USD"] - np.where(gg_grp["DLR_USE_COST"] == "Y", gg_grp["CA_USD"], gg_grp["PA_USD"])
    #   gg_grp["GPM"] = (gg_grp["GP_USD"] / gg_grp["SA_USD"].replace(0, np.nan)).round(2).fillna(0)
    gg_grp["GP_USD"] = [sa - ca if ec == "Y" else sa - pa
                        for sa, pa, ca, ec in zip(gg_grp["SA_USD"], gg_grp["PA_USD"], gg_grp["CA_USD"],
                                                  gg_grp["DLR_USE_COST"])]
    gg_grp["GPM"] = [round(gp / sa, 2) if sa != 0 else 0 for gp, sa in zip(gg_grp["GP_USD"], gg_grp["SA_USD"])]
    src = gg_grp.groupby([pd.Grouper(key="SO_INV_DATE", freq="ME"), "DLR_META"]).agg({"SA_USD": "sum", "GP_USD": "sum"})
    src = (pd.concat([src["SA_USD"].unstack().fillna(0).assign(ALL=lambda x: x.sum(axis=1)).stack(future_stack=True).dropna().to_frame("SA_USD"),
                      src["GP_USD"].unstack().fillna(0).assign(ALL=lambda x: x.sum(axis=1)).stack(future_stack=True).dropna().to_frame("GP_USD")],
                     axis=1).fillna(0).reset_index())
    src["GPM"] = [round(gp / sa, 2) if sa != 0 else 0 for gp, sa in zip(src["GP_USD"], src["SA_USD"])]
    src["SA_USD"] = src["SA_USD"].apply(lambda x: round(x / 1000, 0))
    src["GP_USD"] = src["GP_USD"].apply(lambda x: round(x / 1000, 0))
    src = src.rename(columns={"SO_INV_DATE": "InvoiceDate", "DLR_META": "Dealer", "SA_USD": "SalesAmount",
                              "GP_USD": "GrossProfitAmount", "GPM": "GrossProfitMargin"})
    gg_grp = gg_grp[gg_grp["SO_INV_DATE"] >= "2026"].copy()
    gg_grp["SO_INV_DATE"] = gg_grp["SO_INV_DATE"].dt.strftime("%Y-%m-%d")
    gg_grp = gg_grp.rename(columns={
        "SO_INV_DATE": "InvoiceDate", "DLR_META": "Dealer", "SA_USD": "SalesAmount", "GP_USD": "GrossProfitAmount",
        "GPM": "GrossProfitMargin", "SO_INVOICE": "SalesInvoice", "SO_NUM": "SalesOrder", "DLR_ORD_NUM": "DealerOrder",
        "PO_NUM": "PurchaseOrder", "VND_NAME": "Vendor", "PTS_NO": "PartNo", "DESCR": "PartDescr", "QTY": "Qty",
        "PA_USD": "PurchaseAmount", "CA_USD": "CostAmount"})

    src["Profit"] = src["GrossProfitAmount"] / 1000
    selection, buttons = dealer_selector(src, "Dealer", "ALL")
    tooltip = [month_tooltip("InvoiceDate"), alt.Tooltip("Dealer:N"),
               alt.Tooltip("SalesAmount:Q", title="sales, K USD", format=",.0f"),
               alt.Tooltip("GrossProfitAmount:Q", title="gross profit, K USD", format=",.0f"),
               alt.Tooltip("GrossProfitMargin:Q", title="margin", format=".0%")]
    # two bands, as on the stock chart: the bars below, the margin line above them
    top = float(src.groupby("InvoiceDate")["Profit"].max().max() or 1) * 1.6
    base = alt.Chart(src).encode(x_month("InvoiceDate"))
    bars = base.mark_bar(color=ACCENT, width={"band": BAR_BAND}).encode(
        alt.Y("Profit:Q", title=USD, scale=alt.Scale(domain=[0, top]),
              axis=alt.Axis(orient="left", tickCount=TICK_COUNT)), tooltip=tooltip)
    bar_labels = base.mark_text(dy=-6, fontSize=LABEL_SIZE, color=TITLE_COLOR).encode(
        alt.Y("Profit:Q", scale=alt.Scale(domain=[0, top])), text=alt.Text("Profit:Q", format=MLN))
    line = base.mark_line(color=SECONDARY, strokeWidth=1.5, interpolate="monotone",
                          point={**LINE_POINT, "size": 25, "color": SECONDARY}).encode(
        # no axis title: a "%" centred on the whole axis (-120%..80%) hung far below the labels;
        # the labels themselves say "%" and take the colour of the line
        alt.Y("GrossProfitMargin:Q", title=None, scale=alt.Scale(domain=[-1.2, 0.8]),
              axis=alt.Axis(orient="right", format=".0%", labelColor=SECONDARY, values=[0, 0.2, 0.4, 0.6])),
        tooltip=tooltip)
    line_labels = base.mark_text(dy=-9, fontSize=LABEL_SIZE, color=SECONDARY).encode(
        alt.Y("GrossProfitMargin:Q", scale=alt.Scale(domain=[-1.2, 0.8])),
        text=alt.Text("GrossProfitMargin:Q", format=".0%"))
    # one filter on the whole plot: all layers share src here. A filter on every layer (two_axes
    # with selection) ran into a Vega-Lite 6.4 optimizer bug: the bar labels lost yearmonth(), and
    # piled up in a "null" month at the start of the axis
    plot = two_axes([bars, bar_labels], [line, line_labels]).transform_filter(selection) \
        .properties(width=WIDTH, height=260)
    src["InvoiceDate"] = src["InvoiceDate"].dt.strftime("%Y-%m-%d")
    # no legend here: the extra spacing puts the plot level with the FY chart next to it
    # (buttons, legend row, plot)
    return {"chart": themed(alt.vconcat(buttons, plot, spacing=LEGEND_ROW)), "table": gg_grp.to_dict(orient="split")}


# ---- interactive chart (full width; also redrawn by /process with the filters of the form) ----

def show_detailed_sales_chart_new(daily, **kw):
    def dmax(x):
        return ftmp.groupby(x)["ActualSales"].sum().max() * 1.25

    frq = kw.get("freq", "M").upper()
    axis_name = {"D": "yearmonthdate(InvoiceDate)", "W": "yearweek(InvoiceDate)",
                 "M": "yearmonth(InvoiceDate)", "Y": "year(InvoiceDate)"}.get(frq)
    daily = daily[daily["DLR_META"].isin(report_groups())].copy()
    daily["PCLASS"] = (daily["PCLASS"].replace({"OTHER": "ND"})).fillna("ND")
    daily["ENTRY_CODE"] = np.where(daily["IS_STOCK_LOCATION"].eq(True), "Y", "N")   # was umap.stock_dlr_codes
    daily["RANK"] = daily["RANK"].fillna("F")
    tmp_data = (daily.groupby([pd.Grouper(key="SO_INV_DATE", freq={"M": "ME", "Y": "YE"}.get(frq, frq)),
                               "PCLASS", "DLR_META", "RANK", "ENTRY_CODE"])["SA_USD"]
                .sum().to_frame("ActualSales").reset_index())
    ftmp = tmp_data.copy().rename(columns={"DLR_META": "Dealer", "RANK": "DemandRank", "PCLASS": "ProductClass",
                                           "SO_INV_DATE": "InvoiceDate", "ENTRY_CODE": "FromStock"})
    select = {name: alt.selection_point(fields=[name]) for name in ("Dealer", "DemandRank", "ProductClass", "FromStock")}
    select_period = alt.selection_interval(encodings=["x"])
    colors = {"Dealer": GROUPS[:4],
              "DemandRank": ORANGE,
              "ProductClass": [NEUTRAL_LIGHT, TEAL_LIGHT, BLUE_DEEP, NEUTRAL_DARK],
              "FromStock": [NEUTRAL, ACCENT]}
    titles = {"Dealer": "Dealer", "FromStock": "From stock", "DemandRank": "Demand rank", "ProductClass": "Product class"}
    # the four summaries end where the Sales plot below ends: each takes a fixed y-axis extent (codes are
    # 1-3 characters) plus the concat spacing, and the rest of the width is shared equally
    width, axis_extent, spacing = 1180, 36, CONCAT_SPACING
    summary_width = (width - 3 * (axis_extent + spacing)) // 4

    def summary(name):
        others = [s for n, s in select.items() if n != name]
        bars = alt.Chart(ftmp).mark_bar(cornerRadiusEnd=2).encode(
            alt.X("sum(ActualSales):Q", title=None, axis=None, scale=alt.Scale(domain=(0, dmax(name)), clamp=True)),
            alt.Y(f"{name}:N", title=None, axis=alt.Axis(labelFontWeight=BOLD, labelColor=TITLE_COLOR,
                                                           minExtent=axis_extent, maxExtent=axis_extent)),
            color=alt.Color(f"{name}:N", legend=None, scale=alt.Scale(range=colors[name])),
            opacity=alt.condition(select[name], alt.value(1), alt.value(0.2)),
            tooltip=[alt.Tooltip(f"{name}:N"), alt.Tooltip("sum(ActualSales):Q", title="USD", format=",.0f")])
        labels = bars.mark_text(align="left", dx=3, fontSize=LABEL_SIZE, color=TITLE_COLOR).encode(
            text=alt.Text("sum(ActualSales):Q", format=".2s"), color=alt.value(TITLE_COLOR), opacity=alt.value(1))
        chart = (bars.add_params(select[name]) + labels).properties(width=summary_width, height=90, title=titles[name])
        for s in others + [select_period]:
            chart = chart.transform_filter(s)
        return chart

    x = alt.X(axis_name, type="temporal", title=None,
              axis=alt.Axis(labelAngle=-45, labelOverlap="greedy",
                            format=MONTH_FORMAT if frq in ("M", "W") else alt.Undefined))
    vert = alt.Chart(ftmp).mark_bar(strokeWidth=0.5, stroke=WHITE).encode(
        x, alt.Y("sum(ActualSales):Q", title=USD,
                 axis=alt.Axis(labelExpr="format(datum.value / 1e6, ',.0f')", tickCount=TICK_COUNT)),
        color=alt.condition(select["Dealer"], alt.Color("Dealer:N", legend=None, scale=alt.Scale(range=colors["Dealer"])),
                            alt.value(NEUTRAL_LIGHT)),
        opacity=alt.condition(select_period, alt.value(1), alt.value(0.3)),
        tooltip=[alt.Tooltip(axis_name, type="temporal", title="period"),
                 alt.Tooltip("sum(ActualSales):Q", title="USD", format=",.0f")]
    ).properties(width=width, height=300, title="Sales (drag to select a period; click a bar above to filter)")
    for s in select.values():
        vert = vert.transform_filter(s)
    chart = alt.vconcat(alt.hconcat(*(summary(n) for n in ("Dealer", "FromStock", "DemandRank", "ProductClass")))
                        .resolve_scale(color="independent", x="independent").properties(spacing=spacing),
                        vert.add_params(select_period))

    agg_date_col_name = {"Y": "SO_INV_DATE_Y", "M": "SO_INV_DATE_YM", "W": "SO_INV_DATE_YW",
                         "D": "SO_INV_DATE"}.get(frq.upper(), "SO_INV_DATE_YM")
    table = (daily.groupby([agg_date_col_name, "DLR_META", "PCLASS"], as_index=False).agg({"SA_USD": "sum"}).round({"SA_USD": 2})
             .set_axis(["Invoice Date", "Dealer", "Product Class", "Sales Amount USD"], axis=1))
    table["Sales Amount USD"] = [float(f"{x:.2f}") for x in table["Sales Amount USD"]]
    table["Product Class"] = table["Product Class"].replace({"C": "Constr.", "M": "Mining", "CM": "Common", "ND": "N/D"})
    return {"chart": themed(chart, FULL_CARD), "table": table.to_dict(orient="split")}
