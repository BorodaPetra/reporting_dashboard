"""E-mail reports of the sales report, run by cron through the CLI:

    flask --app wsgi send-reports            # daily report + monthly breakdown on its dates

Before D2 this was an HTTP endpoint (/send-report) without login: anyone who
could reach the server could trigger the mailing. Now the Sales page offers the
same mailing on demand, to administrators only (POST with CSRF token).
"""

import io
import logging
import os

import pandas as pd

from flask_mail import Message

from dashboard.reports.sales import frames
from dashboard import mail

log = logging.getLogger(__name__)
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def env_list(name: str) -> list[str]:
    """Comma-separated e-mail list from the environment (.env); D3 moves it to app.report_recipients."""
    return [x.strip() for x in os.getenv(name, "").split(",") if x.strip()]


def send_email(subject: str, recipients: list[str], html: str = "", text: str = "",
               attachment: tuple[str, bytes] | None = None):
    """attachment: (file name, content of an .xlsx workbook)."""
    if not recipients:
        raise ValueError(f"no recipients for '{subject}'")
    msg = Message(subject, bcc=recipients, body=text, html=html)   # bcc: recipients do not see each other
    if attachment:
        name, content = attachment
        msg.attach(name, XLSX, content)
    mail.send(msg)


def send_monthly_breakdown(state, today: pd.Timestamp) -> bool:
    """Parts sales breakdown of the previous month, sent only on the scheduled dates."""
    # 3rd working day of every month (the old code had the year 2026 hard-coded)
    schedule = {pd.Timestamp(d) for d in frames.get_days_for_breakdown_report(today.year)}
    if today not in schedule:
        log.info("monthly breakdown: %s is not a scheduled date", today.date())
        return False
    send_breakdown(state, today - pd.DateOffset(months=1))
    return True


def send_breakdown(state, month: pd.Timestamp) -> None:
    """Parts sales breakdown of the given month; the Sales page sends it on any date."""
    start = month.replace(day=1)
    end = start + pd.offsets.MonthEnd()
    breakdown = frames.get_sales_breakdown(state.daily, start.strftime("%Y-%m-%d"),
                                           end.strftime("%Y-%m-%d"), state.parts)
    # the workbook is only an attachment: built in memory, no file left on disk
    content = io.BytesIO()
    breakdown.to_excel(content)
    name = f"parts_sales_breakdown_{month:%m_%Y}.xlsx"
    send_email(f"Parts Sales Breakdown ({month:%m_%Y})", env_list("MONTHLY_BREAKDOWN_RECIPIENTS"),
               attachment=(name, content.getvalue()))
    log.info("monthly breakdown sent: %s", name)


def send_daily_report(state) -> None:
    send_email("Parts Daily Report", env_list("DAILY_REPORT_RECIPIENTS"), html=state.report_html)
    log.info("daily report sent")
