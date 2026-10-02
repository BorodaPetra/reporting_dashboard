from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from dashboard.authentication.decorators import roles_required
from dashboard.reports.common.state import invalidate, report_state
from dashboard.uploads import save_excel_upload

from . import blueprint
from .report import NAME, build, tracing_file

report_url = "/delivery"


@blueprint.route(report_url)
@login_required
def index():
    state = report_state(NAME, build)
    return render_template(
        "reports/delivery.html",
        update_date=state.file_date.isoformat() if state.file_date else None,
        chart_spec=state.chart_spec,
        table=state.table,
        chart_id="chart_1",
        user=current_user,
        segment=request.path,
    )


@blueprint.route(report_url, methods=["POST"])
@roles_required("Admin")
def upload_files():
    error = save_excel_upload(request.files.get("file"), tracing_file())
    if not error:
        invalidate(NAME)
    flash(error or "Tracing file uploaded.", "danger" if error else "success")
    return redirect(url_for("delivery.index"))
