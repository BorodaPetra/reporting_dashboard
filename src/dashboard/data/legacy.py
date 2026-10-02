"""Adapter: warehouse views -> frames with the column names of the old MySQL
queries, so the legacy pandas code of the reports runs unchanged and
its results can be compared with the old pickles in stage D4.

Each function documents where a column comes from. Columns that the old code
derived in pandas from the dealer/vendor dictionaries of umap.py (removed in
D0) now come from the warehouse: DLR_META, DLR_FULL_NAME, VND_NAME.
"""

import pandas as pd

from dashboard.data import query_frame

LEGACY_START = "2017-01-01"          # the old daily query: ... >= 20170101


ORDER_LINES_SQL = """
SELECT now()                                       AS "TODAY",
       f.so_invoice_number                         AS "SO_INVOICE",
       f.so_invoice_date                           AS "SO_INV_DATE",
       f.so_number                                 AS "SO_NUM",
       f.so_status                                 AS "SO_PROGRESS_CODE",
       f.back_order_type::text                     AS "BO_CODE",        -- codes are text in the old frame
       f.dealer_code                               AS "DLR_CODE",
       f.so_order_type::text                       AS "SO_TYPE_CODE",
       f.entry_code                                AS "ENTRY_CODE",
       sl.customer_order_number                    AS "DLR_ORD_NUM",
       f.so_order_date                             AS "SO_DATE",
       coalesce(f.so_item_code, f.po_item_code)    AS "ITEM",
       coalesce(f.so_part_number, f.po_part_number) AS "PTS_NO",
       coalesce(sl.jv_code, pl.jv_code)            AS "JV",
       coalesce(sl.line_description, pl.line_description) AS "DESCR",
       coalesce(f.so_qty, f.po_qty)                AS "QTY",
       pf.weight_kg                                AS "WGT",
       pf.hid_code                                 AS "HID",
       f.so_net_price_usd                          AS "SP_USD",
       f.so_net_amount_usd                         AS "SA_USD",
       sl.net_price_rub                            AS "SP_RUB",
       f.so_net_amount_rub                         AS "SA_RUB",
       f.vendor_code                               AS "VND_CODE",
       f.shipping_date                             AS "SHIP_DATE",
       f.po_invoice_number                         AS "PO_INVOICE",
       f.po_status                                 AS "PO_PROGRESS_CODE",
       f.po_price_usd                              AS "PP_USD",
       f.po_amount_usd                             AS "PA_USD",
       f.po_qty                                    AS "PO_QTY",
       f.shipping_mode::text                       AS "SHIP_MODE",
       f.po_number                                 AS "PO_NUM",
       f.po_order_date                             AS "PO_DATE",
       f.po_order_type                             AS "PO_TYPE_CODE",
       sl.comment                                  AS "SO_COMMENT",
       pl.comment                                  AS "PO_COMMENT",
       CASE f.is_direct_shipment WHEN true THEN 'Y' WHEN false THEN 'N' END AS "DS_CODE",
       -- formerly mapped in pandas from umap.py dictionaries
       f.dealer_group                              AS "DLR_META",
       d.name                                      AS "DLR_FULL_NAME",
       v.supplier_code                             AS "VND_NAME",
       f.pnl                                       AS "PNL",
       d.short_name                                AS "DLR",
       d.is_stock_location                         AS "IS_STOCK_LOCATION"
FROM reporting.order_line_flow f
LEFT JOIN sales.sales_order_line sl
       ON sl.so_number = f.so_number AND sl.item_code = f.so_item_code
LEFT JOIN purchasing.purchase_order_line pl
       ON pl.vendor_code = f.vendor_code AND pl.po_number = f.po_number AND pl.item_code = f.po_item_code
LEFT JOIN ref.part_full pf ON pf.part_number = coalesce(f.so_part_number, f.po_part_number)
LEFT JOIN ref.dealer d     ON d.dealer_code = f.dealer_code
LEFT JOIN ref.vendor v     ON v.vendor_code = f.vendor_code
WHERE coalesce(f.so_order_date, f.po_order_date) >= CAST(:date_from AS date)
  AND (CAST(:groups AS text[]) IS NULL OR f.dealer_group = ANY (CAST(:groups AS text[])))
-- the key of the flow (ux_order_line_flow__pair): without it the rows come in the order of the
-- plan (parallel scans, hash joins), float sums changed in the last digit and a rounded
-- total could move by a cent between two builds of the same report
ORDER BY f.so_number, f.so_item_code, f.vendor_code, f.po_number, f.po_item_code
"""


def order_lines(date_from: str = LEGACY_START, groups: list[str] | None = None) -> pd.DataFrame:
    """The old `daily`: sales order lines matched with purchase order lines.

    Source: reporting.order_line_flow (SO<->PO pairs) + line details.
    Filter as in the old query: the SO date, or the PO date for lines without
    an SO. groups=None -> all dealer groups.
    """
    return query_frame("order_lines", ORDER_LINES_SQL, {"date_from": date_from, "groups": groups},
                       parse_dates=["SO_INV_DATE", "SO_DATE", "SHIP_DATE", "PO_DATE"])


PO_INVOICES_SQL = """
-- PERF: no index on po_invoice_number -> parallel seq scan of the view, ~0.2 s.
--   Fine for a report built once a day; an index on (po_invoice_number) in
--   22_order_line_flow.sql would make the lookup of a few invoices ~1 ms.
SELECT f.po_invoice_number    AS "PO_INVOICE",
       max(v.supplier_code)   AS "VND_NAME",
       sum(f.po_amount_usd)   AS "PA_USD"
FROM reporting.order_line_flow f
LEFT JOIN ref.vendor v ON v.vendor_code = f.vendor_code
WHERE f.po_invoice_number IS NOT NULL
  AND coalesce(f.so_order_date, f.po_order_date) >= CAST(:date_from AS date)
  AND (CAST(:invoices AS text[]) IS NULL OR f.po_invoice_number = ANY (CAST(:invoices AS text[])))
GROUP BY f.po_invoice_number
"""


def po_invoices(invoices: list[str] | None = None, date_from: str = LEGACY_START) -> pd.DataFrame:
    """Supplier and USD amount per purchase invoice.

    Old code: daily.groupby("PO_INVOICE") -> VND_NAME.last(), PA_USD.sum()
    over the whole `daily` frame; here only the invoices asked for travel.
    """
    return query_frame("po_invoices", PO_INVOICES_SQL, {"invoices": invoices, "date_from": date_from})


def gtd() -> pd.DataFrame:
    """Customs declaration per purchase invoice (old: gtd.INVOICES split by comma, handle_gtd)."""
    return query_frame("gtd", 'SELECT i.invoice_number AS "PO_INVOICE", i.gtd_number AS "GTD", '
                              'c.declaration_date AS "DATE" '
                              "FROM logistics.customs_declaration_invoice i "
                              "JOIN logistics.customs_declaration c USING (gtd_number) "
                              "ORDER BY c.declaration_date, i.gtd_number",
                       parse_dates=["DATE"])


def warehouse_receipts() -> pd.DataFrame:
    """Arrival at the warehouse per invoice (old: kwe_inbound PREADVICEID, FINISHDATE)."""
    return query_frame("warehouse_receipts", 'SELECT invoice_number AS "PREADVICEID", finish_date AS "FINISHDATE" '
                                             "FROM logistics.warehouse_receipt",
                       parse_dates=["FINISHDATE"])


def unit_cost_rub() -> pd.DataFrame:
    """Unit cost in RUB per part and month (old table cost_rub; duplicates collapsed by max in the load)."""
    return query_frame("unit_cost_rub", 'SELECT part_number AS "PTS_NO", month_end AS "DATE", cost_rub AS "COST_RUB" '
                                        "FROM pricing.unit_cost_rub",
                       parse_dates=["DATE"])


PARTS_SQL = """
SELECT pf.part_number        AS "PTS_NO",
       pf.jv_code            AS "JV",
       pf.description        AS "DESCR",
       pf.vendor_code        AS "VND_CODE",
       coalesce(pf.customs_weight_kg, pf.weight_kg) AS "WEIGHT",   -- old adjust_partsmaster: artmaximum weight first
       pf.dlp_usd            AS "DLP",
       pf.is_prohibited      AS "PROHIBITION_CODE",
       pf.country_of_origin  AS "COO",
       pf.qty_per_machine    AS "QPM",
       pf.hid_code           AS "HID",
       pf.model_code         AS "MDLCODE_PM",
       pf.models             AS "MDLS",
       pf.model_count        AS "MDL_COUNT",
       pf.hid_codes          AS "HIDS",
       pf.hid_source         AS "HID_SOURCE",
       pf.supplier_code      AS "VND_NAME",
       pf.product_class      AS "PCLASS",
       h.description         AS "HID_FULL",
       pf.hs_code            AS "TNVED",
       pf.customs_price      AS "CUSTOMS_PRC",
       pf.pnl                AS "PNL",
       pf.category_name      AS "CAT"
FROM ref.part_full pf
LEFT JOIN ref.hid_group h ON h.hid_code = pf.hid_code
WHERE CAST(:parts AS text[]) IS NULL OR pf.part_number = ANY (CAST(:parts AS text[]))
"""


def parts(parts: list[str] | None = None) -> pd.DataFrame:
    """The old `partsmaster` (ref.part_full). parts=None -> every part (2.4 M rows)."""
    return query_frame("parts", PARTS_SQL, {"parts": parts})


SUPERSESSIONS_SQL = """
SELECT pp.part_number      AS "PTS_NO",
       p.primary_jv_code   AS "JV",
       pp.pnl              AS "PNL",
       n.primary_jv_code   AS "JVN"
FROM ref.part_pnl pp
JOIN ref.part p      ON p.part_number = pp.part_number
LEFT JOIN ref.part n ON n.part_number = pp.pnl
WHERE CAST(:parts AS text[]) IS NULL OR pp.part_number = ANY (CAST(:parts AS text[]))
"""


def supersessions(parts: list[str] | None = None) -> pd.DataFrame:
    """Part -> latest number of its supersession chain (ref.part_pnl)."""
    return query_frame("supersessions", SUPERSESSIONS_SQL, {"parts": parts})


def usd_rate() -> pd.DataFrame:
    """USD/RUB for every calendar day, as-of the last official CBR rate (no look-ahead)."""
    return query_frame("usd_rate", 'SELECT rate_date AS "DATE", usd_rub AS "CURRENCY_RATE" '
                                   "FROM pricing.v_usd_rate_daily ORDER BY rate_date",
                       parse_dates=["DATE"])


def avg_purchase_price(date_from: str = LEGACY_START) -> pd.DataFrame:
    """The old table avg_pp, now the view pricing.avg_purchase_price."""
    return query_frame("avg_pp", 'SELECT month_end AS "DATE", part_number AS "PTS_NO", avg_price_usd AS "AVG_PP" '
                                 "FROM pricing.avg_purchase_price WHERE month_end >= CAST(:date_from AS date)",
                       {"date_from": date_from}, parse_dates=["DATE"])


STOCK_MONTHLY_SQL = """
-- PERF: month_last reads every row since date_from (~25 M) just to find ~40 dates.
--   PostgreSQL has no "loose index scan"; a recursive CTE emulates it on the
--   (snapshot_date, ...) primary key: one index probe per distinct date:
--     WITH RECURSIVE d AS (SELECT min(snapshot_date) AS s FROM inventory.stock_snapshot WHERE ...
--                          UNION ALL SELECT (SELECT min(snapshot_date) FROM inventory.stock_snapshot
--                                            WHERE snapshot_date > d.s) FROM d WHERE d.s IS NOT NULL)
--   Faster still: a materialized view inventory.stock_month_end with the result
--   (~1 M rows), refreshed with the nightly load -> this query becomes a plain SELECT.
WITH month_last AS (          -- the last snapshot of every month (old: resample('M').last())
    SELECT max(snapshot_date) AS snapshot_date
    FROM inventory.stock_snapshot
    WHERE snapshot_date >= CAST(:date_from AS date)
    GROUP BY date_trunc('month', snapshot_date)
)
SELECT (date_trunc('month', s.snapshot_date) + interval '1 month - 1 day')::date AS "DATE",
       s.snapshot_date   AS "SNAPSHOT_DATE",
       s.part_number     AS "PTS_NO",
       sum(s.available)  AS "AVL",
       sum(s.on_hand)    AS "ONH",
       sum(s.incoming)   AS "INCOMING",
       sum(s.ordered)    AS "ORDERED"
FROM inventory.stock_snapshot s
JOIN month_last m USING (snapshot_date)
GROUP BY 1, 2, 3
"""


def stock_monthly(date_from: str = "2022-09-01") -> pd.DataFrame:
    """Stock per part at the last snapshot of each month, long format (summed over JV)."""
    return query_frame("stock_monthly", STOCK_MONTHLY_SQL, {"date_from": date_from},
                       parse_dates=["DATE", "SNAPSHOT_DATE"])


def outstanding_orders_history() -> pd.DataFrame:
    """Month-end snapshots of the open dealer orders, K USD per group (old table
    outstanding_orders, which the dashboard used to append to). Wide: DATE + groups."""
    frame = query_frame("outstanding_orders", 'SELECT month_end AS "DATE", group_code, amount_usd_k '
                                              "FROM reporting.outstanding_orders_snapshot",
                        parse_dates=["DATE"])
    wide = frame.pivot_table(index="DATE", columns="group_code", values="amount_usd_k", aggfunc="sum")
    wide.columns.name = None
    return wide.astype(float).reset_index()


def dealer_groups() -> list[str]:
    """Dealer groups of the reports: replaces the hard-coded group lists."""
    frame = query_frame("dealer_groups", "SELECT group_code FROM ref.dealer_group "
                                         "WHERE group_code NOT IN ('OTHER', 'DEPOT') ORDER BY group_code")
    return frame["group_code"].tolist()


def dealers() -> pd.DataFrame:
    return query_frame("dealers", 'SELECT d.dealer_code AS "DLR_CODE", d.name AS "DLR_FULL_NAME", '
                                  'd.short_name AS "DLR", d.group_code AS "DLR_META", '
                                  'd.is_stock_location AS "IS_STOCK_LOCATION" FROM ref.dealer d')
