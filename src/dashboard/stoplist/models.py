"""Stop list of parts in schema app (D5).

A part is stopped when an administrator added its number to app.stop_list OR the
warehouse marks it discontinued (ref.part.ds_status = OLD_DS / NEW_DS): the old
dashboard computed the flag from its uploaded list and then overwrote it with the
DS status, so in practice only the DS status worked (both count).
The flag belongs to the number itself, not to its supersession chain.

Uploads ADD numbers to the list; single numbers are removed on the stop list page.
"""

from datetime import datetime

import pandas as pd
from flask_login import current_user
from sqlalchemy.dialects.postgresql import insert

from dashboard import db
from dashboard.authentication.models import SCHEMA
from dashboard.data import query_frame


BATCH = 5000


class StopListItem(db.Model):
    __tablename__ = "stop_list"
    __table_args__ = {"schema": SCHEMA}

    part_number = db.Column(db.Text, primary_key=True)
    added_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
    added_by = db.Column(db.Text)


def parse_parts(frame: pd.DataFrame) -> list[str]:
    """First column of the uploaded sheet -> unique part numbers, in file order.

    Part numbers are text: Excel may read a numeric one as 12345.0, so whole floats
    lose the ".0". ValueError with a readable message if nothing is left.
    """
    if frame.shape[1] == 0:
        raise ValueError("stop list file: the sheet is empty")
    column = frame.iloc[:, 0].dropna()
    # PERF: a per-cell Python function; for a very large file, column.astype(str).str.replace(r"\.0$", "")
    #   does the same vectorized (fine here: stop lists are hundreds of rows)
    values = column.map(lambda v: str(int(v)) if isinstance(v, float) and v.is_integer() else str(v)).str.strip()
    parts = list(dict.fromkeys(v for v in values if v))
    if not parts:
        raise ValueError("stop list file: no part numbers in the first column")
    return parts


def add_parts(parts: list[str]) -> int:
    """Add numbers to the list; numbers already there keep their first date. Returns the new ones."""
    if not parts:
        return 0
    now, user = datetime.now(), getattr(current_user, "username", None)
    added = 0
    # batches: one INSERT takes at most 65 535 bind parameters (3 per row -> ~21 800 rows)
    # PERF: for very large files COPY into a temp table + one INSERT ... SELECT ... ON CONFLICT
    #   avoids building a statement per batch
    for start in range(0, len(parts), BATCH):
        rows = [{"part_number": p, "added_at": now, "added_by": user} for p in parts[start:start + BATCH]]
        statement = insert(StopListItem).values(rows).on_conflict_do_nothing(index_elements=["part_number"])
        added += len(db.session.execute(statement.returning(StopListItem.part_number)).scalars().all())
    db.session.commit()                  # one transaction: a failed batch leaves the list as it was
    return added


def remove_part(part_number: str) -> bool:
    result = db.session.execute(db.delete(StopListItem).where(StopListItem.part_number == part_number))
    db.session.commit()
    return result.rowcount > 0


def items() -> list[StopListItem]:
    # PERF: the whole list goes to the page and the report table pages it in the browser; fine for
    #   thousands of rows. For tens of thousands: server-side paging (LIMIT/OFFSET + search in SQL)
    return db.session.scalars(db.select(StopListItem).order_by(StopListItem.added_at.desc(),
                                                               StopListItem.part_number)).all()


UNKNOWN_SQL = """
SELECT s.part_number FROM app.stop_list s
WHERE NOT EXISTS (SELECT 1 FROM ref.part p WHERE p.part_number = s.part_number)
"""

STOPPED_SQL = """
SELECT p.part_number AS "PTS_NO"
FROM unnest(CAST(:parts AS text[])) AS p(part_number)
WHERE EXISTS (SELECT 1 FROM app.stop_list s WHERE s.part_number = p.part_number)
   OR EXISTS (SELECT 1 FROM ref.part r WHERE r.part_number = p.part_number AND r.ds_status IS NOT NULL)
"""


def unknown_parts() -> set[str]:
    """Numbers of the list the parts master does not know (typos, or parts not loaded yet)."""
    return set(query_frame("stop_list_unknown", UNKNOWN_SQL, cache=False)["part_number"])


def stopped(parts: list[str]) -> set[str]:
    """Which of these parts are stopped: in app.stop_list or discontinued in the warehouse.
    Not cached: the list changes with every upload."""
    if not parts:
        return set()
    return set(query_frame("stopped_parts", STOPPED_SQL, {"parts": parts}, cache=False)["PTS_NO"])
