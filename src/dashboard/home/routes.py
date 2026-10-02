from flask import render_template, request
from flask_login import current_user, login_required

from dashboard.home import blueprint


@blueprint.route("/")
@login_required
def index():
    return render_template("pages/index.html", user=current_user, segment=request.path)
