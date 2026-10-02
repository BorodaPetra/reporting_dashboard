"""D4.1 reconciliation: delivery report.

1. Every purchase invoice of the old `daily` (up to the pickle date): supplier
   and amount from the old frame vs legacy.po_invoices() on the warehouse.
2. End to end: the report frame for tracing.xlsx, old input vs new input,
   through the same legacy function prepare_delivery_status_frame.
"""

import pandas as pd

import common
from dashboard.data import query_frame
from dashboard.data import legacy
from dashboard.reports.delivery import report
from dashboard.reports.delivery.status import prepare_delivery_status_frame

daily = common.old_daily()
cut = common.snapshot(daily)
print(f"old pickle: {len(daily):,} rows, snapshot {cut.date()}")

with common.app().app_context():
    common.section("1. invoices: old daily.groupby(PO_INVOICE) vs legacy.po_invoices()")
    old = daily.dropna(subset=["PO_INVOICE"]).groupby("PO_INVOICE").agg(VND_NAME=("VND_NAME", "last"),
                                                                       PA_USD=("PA_USD", "sum"))
    new = legacy.po_invoices().set_index("PO_INVOICE")
    both, only_old, only_new = common.compare_keys(old.index, new.index, "invoices")

    # invoices only in the warehouse: created after the snapshot?
    first = query_frame("reconcile_invoice_dates",
                        "SELECT po_invoice_number AS inv, min(po_order_date) AS first_po "
                        "FROM reporting.order_line_flow WHERE po_invoice_number IS NOT NULL GROUP BY 1")
    first = first.set_index("inv")["first_po"]
    later = first.reindex(only_new) >= cut
    common.row("  only new, first PO after snapshot", int(later.sum()))
    common.row("  only new, older (to explain)", int((~later).sum()))

    common.compare_labels(old.loc[both, "VND_NAME"], new.loc[both, "VND_NAME"], "supplier")
    common.compare_numbers(old.loc[both, "PA_USD"], new.loc[both, "PA_USD"], "amount USD")

    common.section("2. report frame for tracing.xlsx")
    if not report.TRACING_FILE.exists():
        print("    no tracing.xlsx, skipped")
    else:
        tracing = pd.read_excel(report.TRACING_FILE)
        old_frame = prepare_delivery_status_frame(daily, tracing.copy())
        new_frame = report.delivery_frame(tracing.copy())
        common.row("rows old / new", len(old_frame), len(new_frame))
        common.compare_labels(old_frame["VND_NAME"], new_frame["VND_NAME"], "VND_NAME")
        common.compare_numbers(old_frame["AMOUNT"], new_frame["AMOUNT"], "AMOUNT")
        other = [c for c in old_frame.columns if c not in ("VND_NAME", "AMOUNT", "TODAY", "xaxis")]
        same = all(old_frame[c].equals(new_frame[c]) for c in other)
        common.row("other columns identical", same)
