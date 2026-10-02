import logging
import pandas as pd
from flask import flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from dashboard.reports.sales import charts
from dashboard.reports.sales import frames
from dashboard.authentication.decorators import roles_required
from dashboard.reports.common.state import invalidate, report_state
from dashboard.uploads import check_excel_upload

from . import blueprint, budget, mailing
from .report import NAME, build

log = logging.getLogger(__name__)
report_url = "/sales"


@blueprint.route(f"{report_url}/upload", methods=["POST"])
@roles_required("Admin")
def upload_file():
    """budget.xlsx -> app.sales_budget of the current fiscal year."""
    upload = request.files.get("file")
    error = check_excel_upload(upload)
    if not error:
        try:
            rows = budget.parse_budget(pd.read_excel(upload.stream))
            count = budget.replace_budget(rows, budget.current_fy())
        except ValueError as exc:
            error = str(exc)
    if error:
        flash(error, "danger")
    else:
        invalidate(NAME)                     # tiles and the FY chart use the budget
        flash(f"Budget FY{budget.current_fy()} saved: {count} values.", "success")
    return redirect(url_for("sales.index"))


@blueprint.route(f"{report_url}/send/<any(daily, breakdown):kind>", methods=["POST"])
@roles_required("Admin")
def send_report(kind):
    """The cron mailing on demand: daily report, or the breakdown of the previous month."""
    state = report_state(NAME, build)
    try:
        if kind == "daily":
            mailing.send_daily_report(state)
            message = "Daily report sent."
        else:
            month = state.today - pd.DateOffset(months=1)
            mailing.send_breakdown(state, month)
            message = f"Breakdown {month:%m.%Y} sent."
    except (ValueError, OSError) as exc:     # no recipients; SMTP errors are OSError subclasses
        log.exception("mailing '%s' failed", kind)
        flash(f"Not sent: {exc}", "danger")
    else:
        flash(message, "success")
    return redirect(url_for("sales.index"))


@blueprint.route(f"{report_url}/process", methods=["POST"])
@login_required
def process():
    """Detailed chart for the period / dealers / dealer codes chosen in the form."""
    state = report_state(NAME, build)
    form = request.get_json(silent=True) or {}
    params = {
        "freq": form.get("periodScopeGroupName", "M"),
        "start_date": form.get("start_date", (state.today - pd.DateOffset(years=1)).strftime("%Y-%m-%d")),
        "end_date": form.get("end_date", state.today.strftime("%Y-%m-%d")),
        "codes": [c[:6] for c in form if "(" in str(c)],
        "dealers": [d[:3] for d in form if "CheckboxName" in str(d)],
    }
    new_daily = frames.make_new_data(state.daily, **params)
    return jsonify({"detailed": charts.show_detailed_sales_chart_new(new_daily, **params)})


@blueprint.route(report_url, methods=["GET"])
@login_required
def index():
    state = report_state(NAME, build)
    return render_template(
        "reports/sales.html",
        user=current_user,
        segment=request.path,
        today=state.today,
        year_ago=(state.today - pd.DateOffset(years=1)).strftime("%Y-%m-%d"),
        month_date=state.today.strftime("%b %d"),
        upload_url=url_for("sales.upload_file"),       # budget.xlsx, Admin only
        update_date=f"{state.budget_uploaded:%Y-%m-%d}" if state.budget_uploaded else "no budget for this FY",
        groups=state.groups,
        breakdown_group=state.breakdown_group,
        dlr_codes_dct=state.dlr_codes,
        dlr_full_names_dct=state.dlr_full_names,
        tiles=state.tiles,
        table_sales=state.table_sales,
        table_orders=state.table_orders,
        fy=state.top_parts.period,                       # "FY-26": the fiscal year of today
        chart_fy=state.charts["fy"],
        chart_detailed=state.charts["detailed"],
        chart_outstanding=state.charts["outstanding"],
        chart_breakdown=state.charts["breakdown"],
        chart_gross_profit=state.charts["gross_profit"],
        top_parts=state.top_parts,
    )


@blueprint.route(f"{report_url}/top_parts.xlsx")
@login_required
def top_parts_xlsx():
    return report_state(NAME, build).top_parts.xlsx("top_parts_sold")
