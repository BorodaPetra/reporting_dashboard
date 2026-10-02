from flask import render_template, request
from flask_login import current_user, login_required

from dashboard.reports.common.state import report_state

from . import blueprint
from .report import NAME, build

report_url = "/stock"


@blueprint.route(report_url, methods=["GET"])
@login_required
def index():
    state = report_state(NAME, build)
    return render_template(
        "reports/stock.html",
        user=current_user,
        segment=request.path,
        last_month=state.last_month,
        plates=list(zip(state.plates["USD"], state.plates["RUB"])),
        charts=state.charts,
        top_parts=state.top_parts,
    )


@blueprint.route(f"{report_url}/top_parts.xlsx")
@login_required
def top_parts_xlsx():
    return report_state(NAME, build).top_parts.xlsx("top_parts_free_stock")
