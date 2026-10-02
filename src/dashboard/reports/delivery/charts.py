"""Delivery status chart in the look of the stock and sales charts (after D4.4).

Replaces ucharts.get_delivery_status_chart. Same content: a bar per container from
departure (ETD) to the updated arrival (UPD_ETA), the part already travelled, the
delay against the first ETA, today's line. Changes:
* the colour is the delivery mode, with an interactive legend (the old colour was a
  completion gradient, which cannot be clicked); the completion is the bar label;
* completion of a container that has not left yet is 0 %, not "-219 %"
  (the frame keeps the old value, only the chart clips it);
* rows sorted by departure; the time axis ends two weeks after the last arrival
  (the old one added the longest trip, ~4 empty months);
* the mode is a coloured tick at the departure date instead of an emoji;
* the tooltip also shows the supplier and the PO amount the report queries.
"""

import altair as alt
import pandas as pd

from dashboard.reports.common.chart_theme import (ACCENT, ALERT, AMBER, AXIS_TITLE_COLOR, BOLD, DASH, HALF_CARD,
                                                   GRID_COLOR, LABEL_COLOR, LABEL_SIZE, NEUTRAL, NEUTRAL_DARK,
                                                   TITLE_COLOR, WHITE, legend_selection, themed)

MODES = {"SEA_RAIL": "Sea + rail", "RAIL": "Rail", "AIR": "Air"}
MODE_COLORS = [ACCENT, AMBER, NEUTRAL_DARK]
DELAY_COLOR = ALERT
ROW = 34                                  # px per container
WIDTH = 1000                              # plot width in a full-width card


def delivery_chart(frame: pd.DataFrame) -> dict:
    rows = frame.assign(
        MODE=frame["DELIVERY_TYPE"].map(MODES).fillna(frame["DELIVERY_TYPE"]),
        DONE=frame["COMPLITION"].clip(0, 1),
        TRAVELLED_TO=frame[["TODAY", "UPD_ETA"]].min(axis=1),
    )
    order = rows.sort_values(["ETD", "CONT_NUM"])["CONT_NUM"].drop_duplicates().tolist()
    start = min(rows["ETD"].min(), rows["TODAY"].min()) - pd.Timedelta(days=4)
    end = rows["UPD_ETA"].max() + pd.Timedelta(days=14)            # room for the date labels
    date = "%d %b %Y"
    tooltip = [alt.Tooltip("CONT_NUM:N", title="container"), alt.Tooltip("MODE:N", title="mode"),
               alt.Tooltip("ETD:T", format=date), alt.Tooltip("ETA:T", format=date),
               alt.Tooltip("UPD_ETA:T", title="updated ETA", format=date),
               alt.Tooltip("DONE:Q", title="done", format=".0%"), alt.Tooltip("LEFT_DAYS:Q", title="days left"),
               alt.Tooltip("DELAY:Q", title="delay, days"), alt.Tooltip("INVOICE:N", title="invoice"),
               alt.Tooltip("VND_NAME:N", title="supplier"), alt.Tooltip("AMOUNT:Q", title="PO amount, USD", format=",.0f"),
               alt.Tooltip("COMMENTS:N", title="comments")]

    x = alt.X("ETD:T", scale=alt.Scale(domain=[start.isoformat(), end.isoformat()]),
              axis=alt.Axis(format="%d %b", title=None, labelAngle=0, grid=True, gridColor=GRID_COLOR,
                            tickCount={"interval": "week", "step": 2}))
    y = alt.Y("CONT_NUM:N", sort=order, title=None, axis=alt.Axis(labelPadding=8, ticks=False, domain=False))
    mode, opacity = legend_selection("MODE")
    color = alt.Color("MODE:N", scale=alt.Scale(domain=list(MODES.values()), range=MODE_COLORS))
    base = alt.Chart(rows).encode(y=y)

    planned = base.mark_bar(height={"band": 0.5}, color=WHITE, stroke=NEUTRAL, strokeDash=DASH,
                            cornerRadius=2).encode(x, alt.X2("UPD_ETA:T"), tooltip=tooltip)
    # filtered here, not with transform_filter("datum.ETD < datum.TODAY"): Vega-Lite parses only
    # the encoded fields into dates, so ETD (a Date) was compared with TODAY (a string): always false
    travelled = (alt.Chart(rows[rows["ETD"] < rows["TODAY"]]).mark_bar(height={"band": 0.5}, cornerRadius=2)
                 .encode(x, alt.X2("TRAVELLED_TO:T"), y, color=color, opacity=opacity, tooltip=tooltip))
    delay = (base.mark_bar(height={"band": 0.5}, color=DELAY_COLOR, opacity=0.18)
             .encode(alt.X("ETA:T"), alt.X2("UPD_ETA:T"), tooltip=tooltip)
             .transform_filter("datum.DELAY > 0"))
    departure = (base.mark_tick(thickness=3, size=ROW * 0.6)
                 .encode(x, color=color, opacity=opacity, tooltip=tooltip).add_params(mode))
    done = base.mark_text(align="left", dx=6, fontSize=LABEL_SIZE, color=TITLE_COLOR).encode(
        x, text=alt.Text("DONE:Q", format=".0%"))
    arrival = base.mark_text(align="left", dx=6, fontSize=LABEL_SIZE, color=LABEL_COLOR).encode(
        alt.X("UPD_ETA:T"), text=alt.Text("UPD_ETA:T", format="%d %b"))
    late = (base.mark_text(align="left", dx=44, fontSize=LABEL_SIZE, fontWeight=BOLD, color=DELAY_COLOR)
            .encode(alt.X("UPD_ETA:T"), text="DELAY_LABEL:N")
            .transform_filter("datum.DELAY > 0")
            .transform_calculate(DELAY_LABEL="'+' + datum.DELAY + ' d'"))

    today = alt.Chart(rows.head(1)).encode(alt.X("TODAY:T"))
    today = (today.mark_rule(color=AXIS_TITLE_COLOR, strokeDash=DASH)
             + today.mark_text(y=-8, fontSize=LABEL_SIZE, fontWeight=BOLD, color=AXIS_TITLE_COLOR, text="Today"))

    chart = (alt.layer(planned, delay, travelled, today, departure, done, arrival, late)
             .properties(width=WIDTH, height=ROW * max(len(order), 1),
                         title="Delivery completion status"))
    return themed(chart, HALF_CARD)       # the left half of the page, the table right of it
