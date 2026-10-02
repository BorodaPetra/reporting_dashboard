"""Management commands: flask --app wsgi <command>."""

import click
from flask import Flask
from sqlalchemy import text

from dashboard import db

BASE_ROLES = ("Admin", "User")


def register_cli(app: Flask) -> None:
    @app.cli.command("init-db")
    def init_db():
        """Create schema app, its tables and the base roles (idempotent)."""
        from dashboard.authentication.models import SCHEMA, Role
        from dashboard.reports.sales import budget  # noqa: F401 - registers app.sales_budget
        from dashboard.stoplist import models  # noqa: F401 - registers app.stop_list

        with db.engine.begin() as conn:
            conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}"))
        db.create_all()
        for name in BASE_ROLES:
            if not db.session.scalar(db.select(Role).filter_by(name=name)):
                db.session.add(Role(name=name))
        db.session.commit()
        click.echo(f"schema {SCHEMA} ready, roles: {', '.join(BASE_ROLES)}")

    @app.cli.command("send-reports")
    @click.option("--date", "on_date", default=None, help="pretend today is YYYY-MM-DD (testing the schedule)")
    def send_reports(on_date):
        """Daily report + monthly breakdown on its dates; for cron.

        Exit code 1 on failure, so cron / systemd can alert.
        """
        import pandas as pd

        from dashboard.reports.sales import mailing, report

        today = pd.Timestamp(on_date or "today").normalize()
        state = report.build()          # a CLI process has no report state of the web workers
        mailing.send_monthly_breakdown(state, today)
        mailing.send_daily_report(state)
        click.echo(f"{today.date()}: reports sent")

    @app.cli.command("create-admin")
    @click.argument("username")
    @click.option("--email", prompt=True)
    @click.password_option()
    def create_admin(username, email, password):
        """Create an administrator; the password is asked interactively."""
        from dashboard.authentication.models import Role, User

        if db.session.scalar(db.select(User).filter_by(username=username)):
            raise click.ClickException(f"user {username} already exists")
        admin = db.session.scalar(db.select(Role).filter_by(name="Admin"))
        if admin is None:
            raise click.ClickException("run init-db first")
        user = User(username=username, email=email)
        user.set_password(password)
        user.roles = [admin]
        db.session.add(user)
        db.session.commit()
        click.echo(f"administrator {username} created")
