"""Frames of the sales report: tiles, FY chart, tables, detailed chart, breakdown, daily e-mail.

Legacy module udata of the old dashboard, only the functions the report calls.
"""

import numpy as np
import pandas as pd

from dashboard.reports.common.groups import report_groups   # no group codes in code
from dashboard.reports.sales import hid_groups


def make_new_data(daily, **kw):

    dlrcodes = kw.get("codes")
    dlrs = kw.get("dealers")
    dlrs = report_groups() if not dlrs else dlrs
    period = [
        kw.get(
            "start_date",
            (pd.Timestamp("today") - pd.DateOffset(months=12))
            .normalize()
            .strftime("%Y-%m-%d"),
        ),
        kw.get("end_date", pd.Timestamp("today").strftime("%Y-%m-%d")),
    ]
    daily = daily[
        (daily["SO_INV_DATE"] >= period[0]) & (daily["SO_INV_DATE"] <= period[1])
    ]
    if dlrcodes:
        return daily[daily["DLR_CODE"].isin(dlrcodes)]
    else:
        return daily[
            daily["DLR_META"].isin(list(set(dlrs)))
        ]  # daily[daily['DLR'].str.contains('|'.join(set(dlrs)))]


def get_tiles_dataframe(final_frame):
    date_check = pd.Timestamp("today").normalize() - pd.Timedelta(days=1)
    date_check = (
        date_check
        if date_check.is_month_end
        else (date_check + pd.offsets.MonthEnd()).normalize()
    )

    if (pd.Timestamp("today") - pd.Timedelta(days=2)).isoweekday() >= 5:
        if (pd.Timestamp("today") - pd.Timedelta(days=2)).is_month_end:
            date_check = (pd.Timestamp("today") - pd.Timedelta(days=2)).normalize()

    return (
        final_frame.loc[date_check.normalize()]
        .unstack("Type")
        .sort_values("bma_resid", ascending=False)
    )


def get_daily_like_table(tiles_frame, daily):
    copy = tiles_frame.copy()

    fy_now = fyfunc(pd.Timestamp("today"))
    prev_day = pd.Timestamp("today").normalize() - pd.Timedelta(days=1)
    prev_day = (
        prev_day
        if prev_day.isoweekday() in range(1, 6)
        else prev_day - pd.Timedelta(days=1)
        if prev_day.isoweekday() == 6
        else prev_day - pd.Timedelta(days=2)
    )

    copy[copy.columns[~copy.columns.str.contains("prf")]] = copy[
        copy.columns[~copy.columns.str.contains("prf")]
    ]

    upper_part = copy.T.loc[["sm_cfy", "fm", "fm_prf", "sma_cfy"], :].fillna(0)
    upper_part = upper_part.set_axis(
        [
            "Actual Month (K USD)",
            "Forecast Month (K USD)",
            "Performance (%)",
            f"Total FY-{str(fy_now)} (K USD)",
        ],
        axis=0,
    )
    upper_part = upper_part[report_groups()]
    upper_part["TOTAL"] = upper_part.sum(axis=1)

    cmpl = (
        upper_part["TOTAL"].loc["Actual Month (K USD)"]
        / upper_part["TOTAL"].loc["Forecast Month (K USD)"]
    )
    upper_part.loc["Performance (%)", "TOTAL"] = cmpl
    upper_part = upper_part.astype(object)         # the rows become formatted strings below
    upper_part.loc["Performance (%)"] = upper_part.loc["Performance (%)"].apply(
        lambda x: f"{x:.0%}"
    )
    upper_part.loc[
        [x for x in upper_part.index.values if x != "Performance (%)"], :
    ] = upper_part.loc[
        [x for x in upper_part.index.values if x != "Performance (%)"], :
    ].map(lambda x: f"{int(x):,.0f}")

    upper_part.index.set_names("Sales", inplace=True)
    # upper_part.index =  pd.MultiIndex.from_product([['Sales'],list(upper_part.index)], names=['Type','Subtype'])FY

    daily = daily.copy()
    daily = daily[daily["SO_PROGRESS_CODE"] != "A"]
    lower_part = (
        daily[daily["SO_DATE_FY"] == str(fy_now)]
        .groupby(["SO_DATE_YM", "DLR_META"])["SA_USD"]
        .sum()
        .unstack()
        / 1000
    )
    for x in report_groups():
        if x not in lower_part.columns:
            lower_part[x] = 0

    lower_part = lower_part[report_groups()]
    lower_part_cum = lower_part.fillna(0).cumsum().iloc[-1, :]

    outstanding_amount = (
        daily[
            (daily["DLR_META"].isin(report_groups()))
            & (daily["SO_PROGRESS_CODE"] != "6")
        ]
        .groupby("DLR_META")["SA_USD"]
        .sum()
        / 1000
    )

    outstanding_lines = (
        daily[
            (daily["DLR_META"].isin(report_groups()))
            & (daily["SO_PROGRESS_CODE"] != "6")
        ]
        .groupby("DLR_META")["SO_NUM"]
        .count()
    )

    check_month = lower_part.iloc[-1, :].name == prev_day.strftime("%Y-M%m")
    orders_this_month = (
        lower_part.iloc[-1, :]
        if check_month
        else pd.Series([0, 0, 0, 0], index=lower_part.columns)
    )

    lower_part_final = (
        pd.concat(
            [orders_this_month, outstanding_amount, outstanding_lines, lower_part_cum],
            axis=1,
        )
        .fillna(0)
        .T
    )
    lower_part_final = lower_part_final.set_axis(
        [
            "Actual Month (K USD)",
            "Total Outstanding (K USD)",
            "Total Outstanding (lines)",
            f"Total FY-{str(fy_now)} (K USD)",
        ],
        axis=0,
    )

    lower_part_final = lower_part_final[report_groups()]
    lower_part_final["TOTAL"] = lower_part_final.sum(axis=1)
    lower_part_final = (
        lower_part_final.fillna(0).round(0).astype(int).map(lambda x: f"{x:,.0f}")
    )
    lower_part_final.index.set_names("Orders", inplace=True)
    # lower_part_final.index =  pd.MultiIndex.from_product([['Orders'],list(lower_part_final.index)],names=['Type','Subtype'])

    return upper_part.reset_index().to_dict(
        "split"
    ), lower_part_final.reset_index().to_dict("split")


def fyfunc(x):
    return x.year if x.month > 3 else x.year - 1


def get_tiles(data):

    fy_now = fyfunc(pd.Timestamp("today"))
    prev_day = pd.Timestamp("today").normalize() - pd.Timedelta(days=1)
    prev_day = (
        prev_day
        if prev_day.isoweekday() in range(1, 6)
        else prev_day - pd.Timedelta(days=1)
        if prev_day.isoweekday() == 6
        else prev_day - pd.Timedelta(days=2)
    )
    start_period = pd.Timestamp(f"{prev_day.year}-{prev_day.month}-01")
    end_period = start_period + pd.offsets.MonthEnd()

    diff_1 = (int(np.ceil(data["fm"])) - data["sm_cfy"]) * -1
    diff_1 = f"- $ {abs(diff_1):,.0f}" if diff_1 < 0 else f"+ $ {diff_1:,.0f}"

    diff_2 = (int(np.ceil(data["fma"])) - data["sma_cfy"]) * -1
    diff_2 = f"- $ {abs(diff_2):,.0f}" if diff_2 < 0 else f"+ $ {diff_2:,.0f}"

    diff_3 = (int(np.ceil(data["bm_tgt"])) - data["sma_cfy"]) * -1
    diff_3 = f"- $ {abs(diff_3):,.0f}" if diff_3 < 0 else f"+ $ {diff_3:,.0f}"

    tile_1 = {
        "Period": f"{start_period.strftime('%d %b')} - {end_period.strftime('%d %b')} (as of {prev_day.strftime('%d.%m.%Y')})",
        "Actual": f"$ {data['sm_cfy']:,.0f}",
        "Forecast": f"$ {int(np.ceil(data['fm'])):,.0f}",
        "Performance": f"{data['fm_prf']:.0%}",
        "Difference": diff_1,
        # "Color"   : "#03a60e" if data['fm_prf'] >= 0.8 else "#c4a829"\
        #             if (data['fm_prf'] >= 0.4 and data['fm_prf'] < 0.8)\
        #                 else "#e00902",
        "Color_diff": "secondary" if diff_1[0] == "-" else "success",
        "Color_pct": "success"
        if data["fm_prf"] >= 0.8
        else "warning"
        if (data["fm_prf"] >= 0.4 and data["fm_prf"] < 0.8)
        else "danger",
    }

    tile_2 = {
        "Period": f"Apr {fy_now} - {prev_day.strftime('%b %Y')} (as of {prev_day.strftime('%d.%m.%Y')})",
        "Actual": f"$ {data['sma_cfy']:,.0f}",
        "Forecast": f"$ {int(np.ceil(data['fma'])):,.0f}",
        "Performance": f"{data['fma_prf']:.0%}",
        "Difference": diff_2,
        # "Color"   : "#03a60e" if data['fma_prf'] >= 0.8 else "#c4a829"\
        #             if (data['fma_prf'] >= 0.4 and data['fma_prf'] < 0.8)\
        #                 else "#e00902",
        "Color_diff": "secondary" if diff_2[0] == "-" else "success",
        "Color_pct": "success"
        if data["fma_prf"] >= 0.8
        else "warning"
        if (data["fma_prf"] >= 0.4 and data["fma_prf"] < 0.8)
        else "danger",
    }

    tile_3 = {
        "Period": f"Apr {fy_now} - Mar {fy_now + 1} (as of {prev_day.strftime('%d.%m.%Y')})",
        "Actual": f"$ {data['sma_cfy']:,.0f}",
        "Forecast": f"$ {int(np.ceil(data['bm_tgt'])):,.0f}",
        "Performance": f"{data['bma_prf']:.0%}",
        "Difference": diff_3,
        # "Color"   : "#03a60e" if data['bma_prf'] >= 0.8 else "#c4a829"\
        #                 if (data['bma_prf'] >= 0.4 and data['bma_prf'] < 0.8)\
        #                     else "#e00902",
        "Color_diff": "secondary" if diff_3[0] == "-" else "success",
        "Color_pct": "success"
        if data["fma_prf"] >= 0.8
        else "warning"
        if (data["fma_prf"] >= 0.4 and data["fma_prf"] < 0.8)
        else "danger",
    }

    return {"Month Forecast": tile_1, "Year to Date": tile_2, "Budget to Date": tile_3}


def get_fy_sales_frame(fy, daily):

    return (
        daily[
            (daily["SO_INV_DATE_FY"] == str(fy))
            & (daily["DLR_META"].isin(report_groups()))
        ]
        .groupby(["DLR_META", pd.Grouper(key="SO_INV_DATE", freq="ME")])
        .agg({"SA_USD": "sum"})
        .unstack("DLR_META")
        .fillna(0)
        .apply(lambda x: x / 1000, axis=1)
        .round(2)
        .droplevel(level=0, axis=1)
        .assign(ALL=lambda x: x.sum(axis=1))
    ).fillna(0)


def get_data_main_sales_chart(forecast, daily):
    daily = daily.copy()
    date_now = pd.Timestamp("today").normalize()
    date_end_month = date_now + pd.offsets.MonthEnd()
    fy_now = fyfunc(date_now)
    fy_prev = fy_now - 1
    fy_next = fy_now + 1

    sales_pfy = get_fy_sales_frame(fy_prev, daily)
    sales_cfy = get_fy_sales_frame(fy_now, daily)
    current_fy_period = pd.date_range(
        start=f"{fy_now}-04-01", end=f"{fy_next}-03-31", freq="ME"
    )

    if date_now != date_end_month:
        if date_end_month not in sales_cfy.index:
            sales_cfy.loc[date_end_month] = 0
    accum_sales_cfy = sales_cfy.cumsum()
    accum_sales_pfy = sales_pfy.cumsum()
    accum_sales_pfy.index = current_fy_period

    if isinstance(forecast.index, pd.RangeIndex):
        forecast = forecast.set_index("DLR")
    forecast.loc["ALL"] = forecast.sum()
    cols_1 = [f"{fy_now}-{x.capitalize()}-01" for x in forecast.columns[:-3]]
    cols_2 = [f"{fy_next}-{x.capitalize()}-01" for x in forecast.columns[-3:]]

    forecast.columns = pd.to_datetime(cols_1 + cols_2) + pd.offsets.MonthEnd()

    budget_init = forecast.T.copy()
    accum_budget_init = budget_init.cumsum()
    # PERF: a frame of NaN of the same shape without a Python call per cell:
    # pd.DataFrame(np.nan, index=accum_budget_init.index, columns=accum_budget_init.columns)
    accum_budget_latest = accum_budget_init.copy().map(lambda x: np.nan)
    accum_budget_latest.iloc[-1, :] = accum_budget_init.tail(1).squeeze()

    accum_budget_rev = (
        accum_budget_latest.fillna(accum_sales_cfy)
        .astype("float")
        .interpolate(
            method="linear", limit_area="inside", limit_direction="backward", axis=0
        )
        .round(1)
    )
    idx_ = [
        i1 - 1
        for i1, i2 in list(enumerate(accum_sales_cfy.index))
        if i2 == accum_sales_cfy.last_valid_index()
    ][0]
    accum_budget_only = (
        accum_budget_latest.fillna(
            accum_sales_cfy.loc[[accum_sales_cfy.iloc[idx_, :].name]]
        )
        .astype("float")
        .interpolate(
            method="linear", limit_area="inside", limit_direction="backward", axis=0
        )
        .round(1)
    )

    # budget_imax    = accum_budget_init.tail(1)
    budget_rmax = accum_budget_rev.tail(1)
    frames_dict = {
        "sm_cfy": sales_cfy,
        "sma_cfy": accum_sales_cfy,
        "sma_pfy": accum_sales_pfy,
        "fm": budget_init.copy(),
        "fma": accum_budget_init,
        "bm_init": budget_init,
        "bma_resid": accum_budget_only,
        "sma_bma": accum_budget_rev,
        # PERF: pd.DataFrame(np.nan, index=budget_init.index, columns=budget_init.columns)
        # builds the empty frame without a Python lambda per cell
        "bm_tgt": budget_init.copy()
        .map(lambda x: np.nan)
        .fillna(budget_rmax)
        .bfill(),
        "fm_prf": sales_cfy / budget_init,
        "fma_prf": accum_sales_cfy / accum_budget_init,
        "bma_prf": accum_sales_cfy / budget_rmax.squeeze(),
        #'PerfBudgetInit'    :accum_sales_24 / budget_imax.squeeze(),
        #'BudgetInitMax'     :budget_init.copy().applymap(lambda x: np.nan).fillna(budget_imax).fillna(method='bfill'),
        #'BudgetInitAccum'   :accum_budget_init,
    }
    for key in frames_dict:
        # #frames_dict[f].index = frames_dict[f].index.strftime("%b")
        frames_dict[key].columns = pd.MultiIndex.from_product(
            [[key], list(frames_dict[key].columns)], names=["Type", "DLR"]
        )

    # sort=True: the months of the frames differ; pandas 2 always sorted a DatetimeIndex union
    return (
        pd.concat([v for v in frames_dict.values()], axis=1, sort=True)
        .round(3)
        .dropna(how="all", axis="columns")
    )


def get_days_for_breakdown_report(year):
    import calendar
    import datetime

    def third_working_day(year, month):
        """
        Calculate the third working day (Monday-Friday) of a given month.
        :param year: Year as an integer
        :param month: Month as an integer
        :return: The date of the third working day as a datetime.date object
        """
        month_days = [
            datetime.date(year, month, day)
            for day in range(1, calendar.monthrange(year, month)[1] + 1)
        ]
        working_days = [day for day in month_days if day.weekday() < 5]
        return working_days[2]  # Index 2 corresponds to the third working day

    return [
        third_working_day(year, month) for year, month in zip([year] * 12, range(1, 13))
    ]


def get_sales_breakdown(
    original_daily, period_start, period_end=None, partsmaster=None
):
    if period_end is None:
        period_end = (pd.Timestamp(period_start) + pd.offsets.MonthEnd()).strftime(
            "%Y-%m-%d"
        )
    subset = original_daily[
        (original_daily["SO_INV_DATE"] >= period_start)
        & (original_daily["SO_INV_DATE"] <= period_end)
    ]
    if partsmaster is not None:
        subset["HID"] = (
            subset["HID"]
            .fillna(subset["PTS_NO"].map(partsmaster.groupby(["PTS_NO"])["HID"].last()))
            .fillna(subset["PNL"].map(partsmaster.groupby(["PTS_NO"])["HID"].last()))
        )
    sales_break = (
        subset.groupby("HID", dropna=False)["SA_USD"]
        .sum()
        .to_frame("Amount (USD)")
        .sort_values("Amount (USD)", ascending=False)
        .assign(Product_Class=lambda x: x.index.map(hid_groups.hidpclass))
        .assign(HID_Description=lambda x: x.index.map(hid_groups.hid_descr_full))
    )
    sales_break["Product_Class"] = (
        sales_break["Product_Class"]
        .fillna("M")
        .replace({"OTHER": "C", "W": "C", "CM": "C"})
    )
    sales_break["Ratio"] = sales_break["Amount (USD)"] / sum(
        sales_break["Amount (USD)"]
    )
    sales_break["Ratio"] = sales_break["Ratio"].apply(lambda x: f"{x:.2%}")

    return sales_break


def prepare_daily_html(hcmr_sales_plan, daily):

    final_frame = get_data_main_sales_chart(hcmr_sales_plan, daily)
    tiles_frame = get_tiles_dataframe(final_frame).round(3).fillna(0)
    table_sales, table_orders = get_daily_like_table(tiles_frame, daily)
    tf = pd.DataFrame(get_tiles(tiles_frame.loc["ALL"]))
    hex_colors = [
        "#03a60e" if x == "success" else "#c4a829" if x == "warning" else "#e00902"
        for x in list(tf.iloc[-1, :].values)
    ]
    hex_colors_dict = dict(enumerate(hex_colors, start=1))

    tiles_dict = pd.DataFrame(
        tf.iloc[:-3, :]
        .set_axis(
            [
                "Period",
                "Actual Sales (K USD)",
                "Planned Sales (K USD)",
                "Performance (%)",
            ]
        )
        .reset_index()
        .rename(columns={"index": "Contents"})
    ).to_dict(orient="split")

    fy_now = fyfunc(pd.Timestamp("today"))
    title_header = f'<h2 style="font-size: 16px; font-family: Arial;">FY-{fy_now} Parts Sales and Orders Performance</h2>'

    tiles_table_body = (
        '<table role="presentation" border="1" width="75%" cellspacing="0" cellpadding="2">'
        + "<thead>"
        + '<tr  bgcolor="#d7d7d7">'
        + "".join([f"<th>{tiles_col}</th>" for tiles_col in tiles_dict["columns"]])
        + "</tr>"
        + "</thead>"
    )
    tiles_table_body += "<tbody>"

    for row in tiles_dict["data"]:
        tiles_table_body += "<tr>"
        for i, d in enumerate(row):
            d = (
                "<b>" + "</b><br><em>(".join(d.split("(")) + "</em>"
                if "-" in d
                else d[2:]
                if "$" in d
                else d
            )
            if i == 0:
                tiles_table_body += f'<th style="text-align: left; margin-left: 3px; border-collapse: collapse; font-weight: bold;">{d}</th>'
            else:
                if d.__contains__("%"):
                    tiles_table_body += f'<td style="text-align: center; border-collapse: collapse; color:{hex_colors_dict.get(i)}; font-weight: bold;">{d}</td>'
                else:
                    tiles_table_body += f'<td style="text-align: center; border-collapse: collapse;" >{d}</td>'
        tiles_table_body += "</tr>"
    tiles_table_body += "</tbody></table>"

    body_sales_table = (
        '<table role="presentation" border="1" width="75%" cellspacing="0" cellpadding="2">'
        + "<thead>"
        + '<tr  bgcolor="#d7d7d7">'
        + "".join([f"<th>{sale_col}</th>" for sale_col in table_sales["columns"]])
        + "</tr>"
        + "</thead>"
    )
    body_sales_table += "<tbody>"
    for sale_row in table_sales["data"]:
        body_sales_table += "<tr>"
        for sale_idx, sale_data in enumerate(sale_row):
            if sale_idx == 0:
                body_sales_table += f'<th style="text-align: left; margin-left: 3px; font-weight: bold;">{sale_data}</th>'
            else:
                body_sales_table += f'<td style="text-align: center;  border-collapse: collapse;">{sale_data}</td>'
        body_sales_table += "</tr>"
    body_sales_table += "</tbody></table>"

    body_orders_table = (
        '<table role="presentation" border="1" width="75%" cellspacing="0" cellpadding="2">'
        + "<thead>"
        + '<tr  bgcolor="#d7d7d7">'
        + "".join([f"<th>{ord_col}</th>" for ord_col in table_orders["columns"]])
        + "</tr>"
        + "</thead>"
    )
    body_orders_table += "<tbody>"
    for ord_row in table_orders["data"]:
        body_orders_table += "<tr>"
        for ord_idx, ord_data in enumerate(ord_row):
            if ord_idx == 0:
                body_orders_table += f'<th style="text-align: left; margin-left: 3px; font-weight: bold;">{ord_data}</th>'
            else:
                body_orders_table += f'<td style="text-align: center;  border-collapse: collapse;">{ord_data}</td>'
        body_orders_table += "</tr>"
    body_orders_table += "</tbody></table>"

    compiled_html = title_header + "<br>".join(
        [tiles_table_body, body_sales_table, body_orders_table]
    )
    return compiled_html
