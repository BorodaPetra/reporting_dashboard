import pandas as pd
from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from dashboard.authentication.decorators import roles_required
from dashboard.uploads import check_excel_upload

from . import blueprint
from . import models

URL = "/stop-list"


@blueprint.route(URL)
@login_required
def index():
    items = models.items()
    unknown = models.unknown_parts() if items else set()
    # the rows of the report table (ReusableDataTable, as {columns, data}); Remove: the form of an admin
    admin = current_user.has_role("Admin")
    table = {"columns": ["Part number", "In parts master", "Added", "By"] + (["Remove"] if admin else []),
             "data": [[i.part_number, "no" if i.part_number in unknown else "yes",
                       i.added_at.strftime("%Y-%m-%d %H:%M"), i.added_by or "-"] + ([i.part_number] if admin else [])
                      for i in items]}
    return render_template("pages/stop-list.html", items=items, unknown=unknown, table=table,
                           update_date=max((i.added_at for i in items), default=None),
                           user=current_user, segment=request.path)


@blueprint.route(URL, methods=["POST"])
@roles_required("Admin")
def upload():
    """.xlsx, part numbers in the first column -> added to app.stop_list."""
    file = request.files.get("file")
    error = check_excel_upload(file)
    if not error:
        try:
            parts = models.parse_parts(pd.read_excel(file.stream, dtype=object))
            added = models.add_parts(parts)
        except ValueError as exc:
            error = str(exc)
    if error:
        flash(error, "danger")
    else:
        flash(f"Stop list: {added} numbers added, {len(parts) - added} were already there.", "success")
    return redirect(url_for("stoplist_blueprint.index"))           # POST -> redirect -> GET


@blueprint.route(f"{URL}/remove", methods=["POST"])
@roles_required("Admin")
def remove():
    # the number comes in the form, not in the URL: part numbers may contain "/"
    part = (request.form.get("part_number") or "").strip()
    if models.remove_part(part):
        flash(f"{part} removed from the stop list.", "success")
    else:
        flash(f"{part} is not in the stop list.", "danger")
    return redirect(url_for("stoplist_blueprint.index"))
