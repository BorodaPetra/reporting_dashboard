"""Uploads of Excel files by administrators (tracing file to disk, budget to app.sales_budget)."""

import zipfile
from pathlib import Path

from werkzeug.datastructures import FileStorage

ALLOWED_SUFFIXES = {".xlsx"}          # what pandas.read_excel (openpyxl) actually reads


def check_excel_upload(file: FileStorage | None) -> str | None:
    """Return an error message, or None if the upload looks like an .xlsx workbook.

    - an .xlsx is a zip archive: a renamed .exe or .csv fails this check;
    - the size limit is MAX_CONTENT_LENGTH (Flask answers 413 before the view).
    """
    if file is None or not file.filename:
        return "No file selected."
    if Path(file.filename).suffix.lower() not in ALLOWED_SUFFIXES:
        return "Only .xlsx files are accepted."
    if not zipfile.is_zipfile(file.stream):
        return "The file is not a valid .xlsx workbook."
    file.stream.seek(0)
    return None


def save_excel_upload(file: FileStorage | None, target: Path) -> str | None:
    """Save an uploaded .xlsx under a FIXED name; return an error message or None.

    The name chosen by the user is never used as a path (no ../../ tricks, no
    second file next to the old one that the report might pick up).
    """
    error = check_excel_upload(file)
    if error:
        return error
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".uploading")
    file.save(tmp)
    tmp.replace(target)               # atomic swap: a reader never sees half a file
    return None
