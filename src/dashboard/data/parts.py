"""Queries of the parts report (D4.3, SQL-first): only the requested parts and
their supersession chains travel, never the whole parts master.

All functions take lists of part numbers (or chain heads, pnl) and return
frames with the column names of the old frames, so the legacy presentation
code (uframe_new.prettify_outupt) runs unchanged.
"""

import pandas as pd

from dashboard.data import query_frame

STOCK_START = "2022-09-01"          # first month of the stock snapshots used by the old report


def part_numbers() -> pd.DataFrame:
    """Every real part number (no placeholders), upper case as the page searches: the
    suggestions of the single part search. Not cached here: 2.4 M rows, the report state keeps them."""
    return query_frame("part_numbers", 'SELECT DISTINCT upper(part_number) AS "PTS_NO" FROM ref.part '
                                       "WHERE NOT is_placeholder", cache=False)


def previous_numbers(pnls: list[str]) -> pd.DataFrame:
    """Old numbers that lead to each chain head (old: supers_down, column PREV)."""
    return query_frame("parts_prev", """
        SELECT pnl AS "PTS_NO", array_agg(part_number ORDER BY part_number) AS "PREV"
        FROM ref.part_pnl
        WHERE pnl = ANY (CAST(:pnls AS text[])) AND part_number <> pnl
        GROUP BY pnl""", {"pnls": pnls})


DEMAND_SQL = """
SELECT d.pnl              AS "PNL",
       d.month_end        AS "DATE",
       dl.group_code      AS "DLR_META",
       d.qty              AS "QTY",
       d.orders           AS "ORDERS",
       d.last_order_date  AS "LAST_ORDER"
FROM reporting.part_demand_monthly d
JOIN ref.dealer dl ON dl.dealer_code = d.dealer_code
WHERE d.month_end >= CAST(:start AS date)
  AND dl.group_code = ANY (CAST(:groups AS text[]))
  AND (CAST(:pnls AS text[]) IS NULL OR d.pnl = ANY (CAST(:pnls AS text[])))
"""


def demand(groups: list[str], start: str, pnls: list[str] | None = None) -> pd.DataFrame:
    """Monthly demand of the dealers of these groups per chain (reporting.part_demand_monthly).
    pnls=None -> every chain (ranks for the sales and stock reports)."""
    return query_frame("parts_demand", DEMAND_SQL, {"groups": groups, "start": start, "pnls": pnls},
                       parse_dates=["DATE", "LAST_ORDER"])


MONTH_LAST_CTE = """
-- the last snapshot date of every month: a loose index scan on the primary key
-- (snapshot_date, ...) -- one index probe per distinct date instead of reading
-- every row since the start (see the PERF note in legacy.STOCK_MONTHLY_SQL)
WITH RECURSIVE dates AS (
    SELECT min(snapshot_date) AS d FROM inventory.stock_snapshot WHERE snapshot_date >= CAST(:start AS date)
    UNION ALL
    SELECT (SELECT min(snapshot_date) FROM inventory.stock_snapshot WHERE snapshot_date > dates.d)
    FROM dates WHERE dates.d IS NOT NULL
),
month_last AS (
    SELECT max(d) AS snapshot_date FROM dates WHERE d IS NOT NULL GROUP BY date_trunc('month', d)
)
"""

STOCK_SQL = MONTH_LAST_CTE + """
SELECT (date_trunc('month', s.snapshot_date) + interval '1 month - 1 day')::date AS "DATE",
       s.part_number     AS "PTS_NO",
       sum(s.available)  AS "AVAILABLE",
       sum(s.incoming)   AS "INCOMING",
       sum(s.ordered)    AS "ORDERED"
FROM inventory.stock_snapshot s
JOIN month_last m USING (snapshot_date)
WHERE s.part_number = ANY (CAST(:parts AS text[]))
GROUP BY 1, 2
"""


def stock_months(start: str = STOCK_START) -> pd.DatetimeIndex:
    """Month ends that have stock snapshots: the grid of the stock tables (a part
    missing on the last snapshot of a month had no stock that month)."""
    frame = query_frame("stock_months", MONTH_LAST_CTE + """
        SELECT (date_trunc('month', snapshot_date) + interval '1 month - 1 day')::date AS "DATE"
        FROM month_last ORDER BY 1""", {"start": start}, parse_dates=["DATE"])
    return pd.DatetimeIndex(frame["DATE"])


def stock(parts: list[str], start: str = STOCK_START) -> pd.DataFrame:
    """Stock at the last snapshot of each month, summed over JV. A part without a row
    on that date had no stock (old code: unstack + fillna(0))."""
    return query_frame("parts_stock", STOCK_SQL, {"parts": parts, "start": start}, parse_dates=["DATE"])


def initial_stock_age(parts: list[str]) -> pd.DataFrame:
    return query_frame("parts_initial_age", 'SELECT part_number AS "PTS_NO", age_days AS "DAYS" '
                                            "FROM inventory.initial_stock_age "
                                            "WHERE part_number = ANY (CAST(:parts AS text[]))", {"parts": parts})


def unit_cost_rub(parts: list[str]) -> pd.DataFrame:
    return query_frame("parts_cost_rub", 'SELECT part_number AS "PTS_NO", month_end AS "DATE", cost_rub AS "COST_RUB" '
                                         "FROM pricing.unit_cost_rub WHERE part_number = ANY (CAST(:parts AS text[]))",
                       {"parts": parts}, parse_dates=["DATE"])


LATEST_PRICES_SQL = """
SELECT p.part_number AS "PTS_NO",
       (SELECT pp.price_usd FROM pricing.purchase_price pp
         WHERE pp.part_number = p.part_number AND pp.price_usd > 0
         ORDER BY pp.month_end DESC LIMIT 1)                               AS "PP_USD",
       (SELECT f.po_price_usd FROM reporting.order_line_flow f
         WHERE f.part_number = p.part_number
           AND f.so_number IS NULL AND f.shipping_date IS NOT NULL AND f.po_price_usd > 0.01
         ORDER BY f.shipping_date DESC LIMIT 1)                            AS "SHIPPED_PP_USD",
       (SELECT a.avg_price_usd FROM pricing.avg_purchase_price a
         WHERE a.part_number = p.part_number
         ORDER BY a.month_end DESC LIMIT 1)                                AS "AVG_PP"
FROM unnest(CAST(:parts AS text[])) AS p(part_number)
"""


def latest_prices(parts: list[str]) -> pd.DataFrame:
    """Last known purchase price, last price of a stock (replenishment) shipment and
    the 12-month average purchase price. Old frames: pp_usd, shipped_pp_usd, avg_pp."""
    return query_frame("parts_latest_prices", LATEST_PRICES_SQL, {"parts": parts})


MONTHLY_PURCHASE_SQL = """
SELECT part_number AS "PTS_NO", month_end AS "DATE", pp.price_usd AS "PP_USD", a.avg_price_usd AS "AVG_PP"
FROM (SELECT part_number, month_end, price_usd FROM pricing.purchase_price
      WHERE part_number = ANY (CAST(:parts AS text[])) AND month_end >= CAST(:start AS date)) pp
FULL JOIN (SELECT part_number, month_end, avg_price_usd FROM pricing.avg_purchase_price
           WHERE part_number = ANY (CAST(:parts AS text[])) AND month_end >= CAST(:start AS date)) a
     USING (part_number, month_end)
"""


def monthly_purchase_prices(parts: list[str], start: str) -> pd.DataFrame:
    """Purchase price and 12-month average purchase price per part and month,
    for the price table of the page."""
    return query_frame("parts_monthly_purchase", MONTHLY_PURCHASE_SQL, {"parts": parts, "start": start},
                       parse_dates=["DATE"])


# The supersession tree of the Supersessions tab: every number of the chain of a part (the
# numbers with its chain head in ref.part_pnl) with the number it leads to directly. That
# step follows the rules of ref.part_pnl (the warehouse view): an override (LHR before HSP), then
# a local number of a full-analog link, then the full-analog next number (icc 1 / 4); a number
# without a step of its own joins the chain through the full-analog prev link of a number that
# names it (resolved_by prev_complement). The chain head is added by name: in ~6.7 k chains of
# ref.part_pnl the head itself resolves to another chain, so it has no row of its own there
# (by design: the walk stops after a local number or an override).
SUPERSESSION_FAMILY_SQL = """
WITH head AS (
    SELECT pnl FROM ref.part_pnl WHERE part_number = :part
), fam AS (
    SELECT part_number, pnl FROM ref.part_pnl WHERE pnl = (SELECT pnl FROM head)
    UNION
    SELECT pnl, pnl FROM head
), ovr AS (
    SELECT DISTINCT ON (o.part_number) o.part_number, o.leading_part_number AS target,
           'override ' || o.source AS link
    FROM ref.supersession_override o JOIN fam USING (part_number)
    ORDER BY o.part_number, o.source = 'LHR' DESC
), nxt AS (
    SELECT l.part_number, l.target_part_number AS target, l.icc
    FROM ref.part_link l JOIN fam USING (part_number)
    WHERE l.link_type = 'next' AND l.icc IN ('1', '4') AND l.target_part_number <> l.part_number
), loc AS (
    SELECT l.part_number, l.target_part_number AS target
    FROM ref.part_link l JOIN nxt USING (part_number)
    WHERE l.link_type = 'local' AND l.target_part_number <> l.part_number
      AND l.target_part_number NOT IN ('BUY@CUMMINS', 'PURCUMMINS')
), prv AS (
    SELECT DISTINCT ON (l.target_part_number) l.target_part_number AS part_number, l.part_number AS target
    FROM ref.part_link l
    JOIN fam f ON f.part_number = l.target_part_number
    JOIN fam s ON s.part_number = l.part_number
    WHERE l.link_type = 'prev' AND l.icc IN ('1', '4') AND l.part_number <> l.target_part_number
    ORDER BY l.target_part_number, l.part_number
)
SELECT f.part_number                                    AS "PTS_NO",
       f.pnl                                            AS "PNL",
       coalesce(o.target, c.target, n.target, v.target) AS "PARENT",
       CASE WHEN o.target IS NOT NULL THEN o.link
            WHEN c.target IS NOT NULL THEN 'local'
            WHEN n.target IS NOT NULL THEN 'next'
            WHEN v.target IS NOT NULL THEN 'prev' END    AS "LINK",
       n.icc                                            AS "ICC",
       p.description                                    AS "DESCR",
       p.hs_code                                        AS "TNVED",
       p.supplier_code                                  AS "VENDOR"
FROM fam f
LEFT JOIN ovr o USING (part_number)
LEFT JOIN loc c USING (part_number)
LEFT JOIN nxt n USING (part_number)
LEFT JOIN prv v USING (part_number)
LEFT JOIN ref.part_full p USING (part_number)
"""


def supersession_family(part: str) -> pd.DataFrame:
    """The numbers of the chain of a part and the number each one leads to (empty: unknown part)."""
    return query_frame("parts_supersession_family", SUPERSESSION_FAMILY_SQL, {"part": part})


# The Orders tab: one row per order and invoice of a part, cancelled lines
# left out, the whole history, amounts in USD (the purchase orders have no other currency)
SALES_ORDERS_SQL = """
SELECT to_char(so.order_date, 'YYYY-MM-DD')    AS "Order date",
       l.so_number                             AS "Order number",
       d.name                                  AS "Dealer",
       sum(l.qty)                              AS "Qty",
       round(sum(l.net_amount_usd), 2)::float8 AS "Amount, USD",
       l.invoice_number                        AS "Invoice number",
       to_char(max(l.invoice_date), 'YYYY-MM-DD') AS "Invoice date"
FROM sales.sales_order_line l
JOIN sales.sales_order so USING (so_number)
LEFT JOIN ref.dealer d ON d.dealer_code = so.dealer_code
WHERE l.part_number = :part AND l.status_code <> 'A'
GROUP BY so.order_date, l.so_number, d.name, l.invoice_number
ORDER BY so.order_date DESC, l.so_number, l.invoice_number
"""

PURCHASE_ORDERS_SQL = """
SELECT to_char(min(l.order_date), 'YYYY-MM-DD')  AS "Order date",
       l.po_number                               AS "Order number",
       -- the demo suppliers have no names, the code is the name (as VND_NAME in the old reports)
       coalesce(s.name, v.supplier_code)         AS "Vendor",
       sum(l.qty)                                AS "Qty",
       round(sum(l.amount_usd), 2)::float8       AS "Amount, USD",
       l.invoice_number                          AS "Invoice number",
       to_char(max(l.shipping_date), 'YYYY-MM-DD') AS "Ship date"
FROM purchasing.purchase_order_line l
LEFT JOIN ref.vendor v USING (vendor_code)
LEFT JOIN ref.supplier s USING (supplier_code)
WHERE l.part_number = :part AND l.status_code <> 'A'
GROUP BY l.vendor_code, v.supplier_code, s.name, l.po_number, l.invoice_number
ORDER BY min(l.order_date) DESC NULLS LAST, l.po_number, l.invoice_number
"""


def part_labels(parts: list[str]) -> pd.DataFrame:
    """Description and category of the parts master (the TOP-10 lists of the reports)."""
    return query_frame("part_labels", """
        SELECT part_number AS "PTS_NO", description AS "DESCR", category_name AS "CAT"
        FROM ref.part_full WHERE part_number = ANY (CAST(:parts AS text[]))""", {"parts": parts})


# Available (1.Now) of the Stock tab: the last snapshot of the last month is the last snapshot
AVAILABLE_NOW_SQL = """
SELECT coalesce(sum(available), 0) AS "AVAILABLE"
FROM inventory.stock_snapshot
WHERE part_number = :part
  AND snapshot_date = (SELECT max(snapshot_date) FROM inventory.stock_snapshot)
"""


def available_now(part: str) -> int:
    """Free stock of a part now, summed over JV."""
    return int(query_frame("parts_available_now", AVAILABLE_NOW_SQL, {"part": part})["AVAILABLE"][0])


def sales_orders(part: str) -> pd.DataFrame:
    return query_frame("parts_sales_orders", SALES_ORDERS_SQL, {"part": part})


def purchase_orders(part: str) -> pd.DataFrame:
    return query_frame("parts_purchase_orders", PURCHASE_ORDERS_SQL, {"part": part})
