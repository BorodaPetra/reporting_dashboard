from flask import abort, jsonify, render_template, request
from flask_login import current_user, login_required

from dashboard.reports.common.daily import GROSS_PROFIT_START
from dashboard.reports.common.state import ReportBuildFailed, ReportNotReady, report_state
from dashboard.reports.sales import report as sales_report

from . import blueprint, report

report_url = "/parts"
MAX_PARTS = 500          # one request reads these parts from the warehouse; a sane upper bound
MIN_PREFIX = 2           # suggestions from the second typed character


@blueprint.route(report_url)
@login_required
def index():
    return render_template("reports/parts.html", gross_profit_start=GROSS_PROFIT_START,
                           user=current_user, segment=request.path)


@blueprint.route(f"{report_url}/processing", methods=["POST"])
@login_required
def processing():
    """Data of the requested parts, read from the warehouse per request (D4.3, SQL-first)."""
    body = request.get_json(silent=True) or {}
    parts = [str(p) for p in body.get("parts", []) if str(p).strip()][:MAX_PARTS]
    if not parts:
        return jsonify({"error": "no parts"}), 400
    datatable, overview, breakdown = report.process(parts)
    return jsonify({"datatable": datatable, "overview": overview, "breakdown": breakdown})


@blueprint.route(f"{report_url}/suggest")
@login_required
def suggest():
    """Part numbers that start with ?q= (the single part search of the page)."""
    prefix = request.args.get("q", "").strip()
    if len(prefix) < MIN_PREFIX:
        return jsonify([])
    try:
        state = report_state(report.NAME, report.build)
    except ReportNotReady:
        return jsonify([]), 202          # the numbers load at the warm-up; no suggestions meanwhile
    return jsonify(report.suggestions(state, prefix))


def requested_part():
    part = request.args.get("part", "").strip()
    if not part:
        abort(400)
    return part


@blueprint.route(f"{report_url}/supersessions")
@login_required
def supersessions():
    """The supersession tree of ?part= (null for an unknown number)."""
    return jsonify(report.supersession_tree(requested_part()))


@blueprint.route(f"{report_url}/orders")
@login_required
def orders():
    """The sales and purchase orders of ?part=; the gross profit comes from the Sales report."""
    try:
        sales_daily = report_state(sales_report.NAME, sales_report.build).daily
    except (ReportNotReady, ReportBuildFailed):
        sales_daily = None
    return jsonify(report.orders(requested_part(), sales_daily))
