"""One look for the Altair charts of the reports (sales, stock, delivery; after D4.4).

Every style value a chart module uses comes from here: sizes, colours, text, axes, formats.
A chart module composes its own palettes from these names but writes no colour of its own.

themed(chart, design_width) applies the common configuration, sets the global Altair
options the charts need (no chart depends on what was imported before it) and records in
usermeta.designWidth the card width the sizes were chosen for:
static/assets/js/charts.js scales the fonts against it.
"""

import altair as alt

# ---- sizes ------------------------------------------------------------------------------------
HALF_CARD = 640                         # a half-width card on a 1920 px screen
FULL_CARD = 1300                        # a full-width card
WIDTH = 500                             # plot width of the main row in a half-width card
PLOT_HEIGHT = 240                       # the main plot of a half-width card
PANEL_HEIGHT = 120                      # the small panels under it
BAR_BAND = 0.75                         # bar width, share of its band
CONCAT_SPACING = 24

# ---- colours ----------------------------------------------------------------------------------
# accent: the series a chart is about
ACCENT = "#FF6600"
ACCENT_BRIGHT = "#FF9100"
ACCENT_LIGHT = "#FF944D"
AMBER = "#FFB627"
AMBER_LIGHT = "#FFC971"
SAND = "#D1B490"
GOLD = "#E0B000"
# the page chrome of a chart
BUTTON_OFF = "#ECEEF2"                  # an unselected button
GRID_COLOR = "#EEF0F4"
# three greys for the data (stage 2: they were nine near-identical ones)
NEUTRAL_LIGHT = "#DDDDDD"               # plans, forecasts, orders; bars outside a selection
NEUTRAL = "#BDBDBD"                     # the second series
NEUTRAL_DARK = "#8C8C8C"
# second-axis lines and other hues
SECONDARY = "#2E7D32"                   # a line on the second axis: USD/RUB rate, margin
GREEN_SOFT = "#81A263"
GREEN_BRIGHT = "#00B300"
BLUE = "#4169E1"
BLUE_DEEP = "#0C5B86"
TEAL_LIGHT = "#A3C4C4"
ALERT = "#C62828"                       # delays
WHITE = "white"
# categorical palettes
# demand ranks A-F, one palette in every report: A-C orange (demand in 3 months of 12 or more)
ORANGE = [ACCENT, ACCENT_BRIGHT, ACCENT_LIGHT, NEUTRAL_LIGHT, NEUTRAL, NEUTRAL_DARK]
GROUPS = [ACCENT, AMBER, AMBER_LIGHT, SAND, NEUTRAL, NEUTRAL_DARK]                     # dealer groups

# ---- text -------------------------------------------------------------------------------------
FONT = 'Inter, "Segoe UI", Arial, sans-serif'     # the font of the pages (theme.css --font-sans)
TITLE_COLOR = "#262B40"                 # titles, legends, value labels
LABEL_COLOR = "#4A5073"                 # axis labels, secondary value labels
AXIS_TITLE_COLOR = "#66799E"            # axis titles, reference lines
RULE_COLOR = "#D1D7E0"                  # axis domain and ticks
LABEL_SIZE = 9                          # value labels, in every chart
BUTTON_LABEL_SIZE = 10                  # the dealer buttons above a chart
BOLD = 600

# ---- axes, marks and formats ------------------------------------------------------------------
TICK_COUNT = 5
MONTH_FORMAT = "%b %y"                  # axis: "Aug 25"
MONTH_TOOLTIP_FORMAT = "%b %Y"          # tooltip: "Aug 2025"
MONTH = alt.Axis(format=MONTH_FORMAT, labelAngle=-45, title=None, labelOverlap=True)
DASH = [4, 3]                           # every dashed line: a secondary series, a plan, today
LINE_POINT = {"filled": False, "fill": WHITE}     # hollow points on a line


def month_tooltip(field: str) -> alt.Tooltip:
    """The month of a monthly bar or point, as "Aug 2025"."""
    return alt.Tooltip(f"yearmonth({field}):O", title="month", format=MONTH_TOOLTIP_FORMAT)


def money(currency: str = "USD") -> str:
    """The y-axis title of an amount: the unit only."""
    return "USD, mln" if currency == "USD" else "RUB, bln"


def legend_selection(field: str):
    """Click a legend entry to highlight that series, click again (or double-click) to reset."""
    selection = alt.selection_point(fields=[field], bind="legend")
    return selection, alt.condition(selection, alt.value(1), alt.value(0.2))


def themed(chart, design_width: int = HALF_CARD) -> dict:
    # The sales frames exceed Altair's 5000-row default. Set on every call (idempotent): the
    # spec is built right below, so no chart relies on an import having set it. Not a `with`
    # block: the reports build in a background thread too, and restoring the default on exit
    # would break a spec another thread is building at that moment.
    # PERF: the rows are embedded in the page as JSON; aggregating in pandas before the chart
    #   (or alt.data_transformers "vegafusion") would send a few hundred rows instead
    alt.data_transformers.disable_max_rows()
    spec = (chart.configure(background="transparent", padding=5, font=FONT)
            .configure_title(fontSize=13, fontWeight=BOLD, anchor="start", offset=8, color=TITLE_COLOR)
            .configure_axis(grid=False, labelFontSize=10, titleFontSize=10, titleFontWeight=400,
                            titleColor=AXIS_TITLE_COLOR, labelColor=LABEL_COLOR,
                            domainColor=RULE_COLOR, tickColor=RULE_COLOR)
            # legends: right-aligned above the plot, in the font of the titles, smaller
            .configure_legend(orient="top", direction="horizontal", title=None, symbolSize=80,
                              columnPadding=12, padding=0,
                              labelFontSize=10, labelFontWeight=BOLD, labelColor=TITLE_COLOR,
                              titleFontSize=11, titleFontWeight=BOLD, titleColor=TITLE_COLOR)
            .configure_view(strokeWidth=0)
            .configure_concat(spacing=CONCAT_SPACING)).to_dict()
    # right-aligned legends: Vega's legend layout; Altair's LegendConfig does not list it
    spec["config"]["legend"]["layout"] = {"top": {"anchor": "end"}}
    spec["usermeta"] = {"designWidth": design_width}
    return spec
