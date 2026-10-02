"""TOP-10 parts of the sales and stock reports: the parts with the largest
amount in USD, with the description and category of the parts master. Drawn as a ranked
list with bars (includes/top_parts.html); the xlsx is written on the server, because the
xlsx writer of ReusableDataTable is private to its file (a copy of the reference)."""

from dataclasses import dataclass
from datetime import datetime
from io import BytesIO

import pandas as pd
from flask import send_file

from dashboard.data import parts as parts_data

TOP = 10
COLUMNS = {"PTS_NO": "Part number", "DESCR": "Description", "CAT": "Category",
           "QTY": "Qty", "AMOUNT": "Amount, USD"}
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@dataclass
class TopParts:
    frame: pd.DataFrame         # COLUMNS keys: the TOP parts, largest amount first
    total: float                # the amount of all parts, for the share of the TOP
    period: str                 # "FY-26", "2026-09-25": the title of the card

    @property
    def share(self) -> float:
        return float(self.frame["AMOUNT"].sum()) / self.total if self.total else 0.0

    def rows(self) -> list[dict]:
        """The rows of the list; BAR: the amount in % of the first."""
        lead = self.frame["AMOUNT"].max()
        return self.frame.assign(BAR=(self.frame["AMOUNT"] / lead * 100).round(1)).to_dict("records")

    def xlsx(self, name: str):
        buffer = BytesIO()
        self.frame.rename(columns=COLUMNS).to_excel(buffer, index=False, sheet_name=self.period)
        buffer.seek(0)
        return send_file(buffer, mimetype=XLSX, as_attachment=True,
                         download_name=f"{name}_{self.period} {datetime.now():%Y%m%d_%H%M%S}.xlsx")


def top_parts(amounts: pd.DataFrame, period: str) -> TopParts:
    """amounts: PTS_NO, QTY, AMOUNT, one row per part. Parts with no positive amount (returns)
    are not ranked but count in the total; equal amounts in the order of the number."""
    top = (amounts[amounts["AMOUNT"] > 0]
           .sort_values(["AMOUNT", "PTS_NO"], ascending=[False, True]).head(TOP))
    labels = parts_data.part_labels(top["PTS_NO"].tolist())
    frame = (top.merge(labels, on="PTS_NO", how="left")[list(COLUMNS)]
             .fillna({"DESCR": "", "CAT": ""}).reset_index(drop=True))
    return TopParts(frame, float(amounts["AMOUNT"].sum()), period)
