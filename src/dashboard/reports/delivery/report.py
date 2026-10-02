"""Parts delivery report: containers on the way (tracing.xlsx) + supplier and
amount of their purchase invoices from the warehouse (D4).

Before D4 the report loaded the whole `daily` frame (640 k rows) to look up a
handful of invoices; now only those invoices are queried.
"""

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd
from flask import current_app

from dashboard.data import legacy

from .charts import MODES, delivery_chart
from .status import prepare_delivery_status_frame

NAME = "delivery"
INVOICE_COLUMN = 3          # 4th column of the tracing file: purchase invoice number
# the table next to the chart: the fields of the chart tooltip (frame column -> header)
TABLE_COLUMNS = {"CONT_NUM": "Container", "MODE": "Mode", "ETD": "ETD", "ETA": "ETA", "UPD_ETA": "Updated ETA",
                 "DONE": "Done, %", "LEFT_DAYS": "Days left", "DELAY": "Delay, days", "INVOICE": "Invoice",
                 "VND_NAME": "Supplier", "AMOUNT": "PO amount, USD", "COMMENTS": "Comments"}
DATE_COLUMNS = ("ETD", "ETA", "UPD_ETA")


@dataclass(frozen=True)
class DeliveryState:
    chart_spec: dict | None      # Vega-Lite spec; None when no tracing file was uploaded
    file_date: date | None
    table: dict | None = None    # the containers as {columns, data} for the report table


def delivery_frame(tracing: pd.DataFrame) -> pd.DataFrame:
    invoices = tracing.iloc[:, INVOICE_COLUMN].dropna().astype(str).unique().tolist()
    return prepare_delivery_status_frame(legacy.po_invoices(invoices), tracing.copy())


def delivery_table(frame: pd.DataFrame) -> dict:
    """The rows of the chart, in its order (by departure), with its clipped completion."""
    rows = frame.assign(MODE=frame["DELIVERY_TYPE"].map(MODES).fillna(frame["DELIVERY_TYPE"]),
                        DONE=(frame["COMPLITION"].clip(0, 1) * 100).round(),
                        AMOUNT=frame["AMOUNT"].astype(float).round())
    rows = rows.sort_values(["ETD", "CONT_NUM"])[list(TABLE_COLUMNS)]
    for column in DATE_COLUMNS:
        rows[column] = rows[column].dt.strftime("%Y-%m-%d")
    rows = rows.astype(object).where(rows.notna(), None)      # JSON null, not NaN
    return {"columns": list(TABLE_COLUMNS.values()), "data": rows.values.tolist()}


def tracing_file() -> Path:
    return Path(current_app.instance_path) / "delivery" / "tracing.xlsx"


def build() -> DeliveryState:
    path = tracing_file()
    if not path.exists():
        return DeliveryState(chart_spec=None, file_date=None)
    frame = delivery_frame(pd.read_excel(path))
    return DeliveryState(
        chart_spec=delivery_chart(frame),
        table=delivery_table(frame),
        file_date=date.fromtimestamp(path.stat().st_mtime),
    )
