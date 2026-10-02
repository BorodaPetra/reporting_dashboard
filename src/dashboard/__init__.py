"""HCMR parts dashboard: Flask application factory.

    flask --app wsgi run --debug           # development server
    flask --app wsgi init-db               # create schema app, tables, base roles
    flask --app wsgi create-admin <login>  # first administrator (password prompt)

Configuration comes from the environment / .env (see config.py).
"""

import os
import pkgutil
import secrets
from importlib import import_module
from importlib.util import find_spec
from pathlib import Path

from flask import Flask, g, render_template
from flask_login import LoginManager
from flask_mail import Mail
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import CSRFProtect

db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()
mail = Mail()

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",          # the browser trusts Content-Type, no guessing
    "X-Frame-Options": "DENY",                    # no embedding in a foreign page (clickjacking)
    "Referrer-Policy": "same-origin",             # URLs with filters do not leak to CDNs
}

# Scripts only from this site or inline blocks carrying the nonce of the response.
# Styles stay 'unsafe-inline': style="" attributes in the templates, <style> injected by
# vega-embed. Google Fonts: the Inter font imported by volt.css.
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    "script-src 'self' 'nonce-{nonce}'; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src 'self' data: https://fonts.gstatic.com; "
    "img-src 'self' data: blob:; "
    "connect-src 'self'; "
    "object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
)


def csp_nonce() -> str:
    """One random value per response: templates put it on inline <script>, the header allows it."""
    if "csp_nonce" not in g:
        g.csp_nonce = secrets.token_urlsafe(16)
    return g.csp_nonce

REPORTS_PACKAGE = "dashboard.reports"


def register_blueprints(app: Flask) -> None:
    for module_name in ("authentication", "home", "stoplist"):
        module = import_module(f"dashboard.{module_name}.routes")
        app.register_blueprint(module.blueprint, url_prefix=app.config["URL_PREFIX"])

    # every sub-package of dashboard/reports with routes.blueprint is a report
    reports = import_module(REPORTS_PACKAGE)
    for info in pkgutil.iter_modules(reports.__path__):
        if not info.ispkg or info.name == "common":
            continue
        routes = import_module(f"{REPORTS_PACKAGE}.{info.name}.routes")
        if find_spec(f"{REPORTS_PACKAGE}.{info.name}.report") is not None:     # ported report: warm-up
            report = import_module(f"{REPORTS_PACKAGE}.{info.name}.report")
            if hasattr(report, "build"):         # parts: only the part numbers of its suggestions
                app.extensions["report_states"].register(report.NAME, report.build)
        blueprint = getattr(routes, "blueprint", None)
        if blueprint is not None:
            app.register_blueprint(blueprint, url_prefix=app.config["URL_PREFIX"] + app.config["REPORTS_PREFIX"])


def register_error_handlers(app: Flask) -> None:
    from dashboard.reports.common.state import ReportBuildFailed, ReportNotReady

    for code in (403, 404, 500):
        app.register_error_handler(code, lambda e, code=code: (render_template(f"pages/{code}.html"), code))

    @app.errorhandler(ReportNotReady)
    def report_not_ready(e):
        # 202 Accepted: the work has started; Refresh makes the browser ask again
        return render_template("pages/report-preparing.html"), 202, {"Refresh": "10"}

    @app.errorhandler(ReportBuildFailed)
    def report_build_failed(e):
        return render_template("pages/report-failed.html"), 500


def create_app(config_object=None) -> Flask:
    from dashboard.config import get_config

    # runtime files (uploads) live outside the package; Flask's default for a src layout is src/instance
    app = Flask(__name__, instance_path=os.getenv("INSTANCE_PATH") or str(Path(__file__).resolve().parents[2] / "instance"))
    app.config.from_object(config_object or get_config())

    db.init_app(app)
    csrf.init_app(app)
    mail.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "authentication_blueprint.login"

    from dashboard.reports.common import state as report_states

    report_states.init_app(app)

    from dashboard.authentication.models import User

    @login_manager.user_loader
    def load_user(user_id: str):
        user = db.session.get(User, int(user_id))
        return user if user is not None and user.active else None

    register_blueprints(app)
    register_error_handlers(app)

    @app.before_request
    def start_report_warmup():
        # under `flask run` the first request starts it; gunicorn starts it in post_worker_init
        app.extensions["report_states"].start_warmup()

    app.jinja_env.globals["csp_nonce"] = csp_nonce

    @app.after_request
    def security_headers(response):
        for name, value in SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        response.headers.setdefault("Content-Security-Policy", CONTENT_SECURITY_POLICY.format(nonce=csp_nonce()))
        return response

    from dashboard.cli import register_cli

    register_cli(app)
    return app
