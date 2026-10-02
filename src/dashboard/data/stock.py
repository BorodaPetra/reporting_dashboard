"""Queries of the stock report (D4.4): the stock at every month end with the unit
prices it is valued with, and the value of every snapshot day (weekly candles).

Only the last snapshot of each month is read. The dates are found first (a loose
index scan, parts.MONTH_LAST_CTE) and passed as an array: with the values known
at planning time PostgreSQL looks them up in the primary key (EXPLAIN: ~0.3 M
index entries) - 1.4 s instead of 50 s for a JOIN with the CTE, which scans the
whole yearly partitions it cannot rule out (EXPLAIN: ~7 M rows of 2025 and 2026).
"""

import pandas as pd

from dashboard.data import query_frame
from dashboard.data.parts import MONTH_LAST_CTE


def month_last_dates(start: str) -> list[str]:
    frame = query_frame("stock_month_last", MONTH_LAST_CTE + "SELECT snapshot_date FROM month_last ORDER BY 1",
                        {"start": start})
    return frame["snapshot_date"].astype(str).tolist()


STOCK_VALUES_SQL = """
WITH stock AS (             -- the last snapshot of each month, summed over JV
    SELECT (date_trunc('month', s.snapshot_date) + interval '1 month - 1 day')::date AS month_end,
           s.part_number,
           sum(s.on_hand) AS on_hand, sum(s.available) AS available,
           sum(s.incoming) AS incoming, sum(s.ordered) AS ordered
    FROM inventory.stock_snapshot s
    WHERE s.snapshot_date = ANY (CAST(:dates AS date[]))
    GROUP BY 1, 2
    HAVING sum(s.on_hand) <> 0 OR sum(s.available) <> 0 OR sum(s.incoming) <> 0 OR sum(s.ordered) <> 0
),
second_wh AS (              -- the second warehouse: its own monthly table and unit cost
    SELECT month_end, part_number, qty, cost_rub
    FROM inventory.nvk_stock
    WHERE month_end = ANY (CAST(:months AS date[]))
),
keys AS (
    SELECT month_end, part_number FROM stock
    UNION
    SELECT month_end, part_number FROM second_wh
)
SELECT k.month_end                          AS "DATE",
       k.part_number                        AS "PTS_NO",
       coalesce(pp.pnl, k.part_number)      AS "PNL",
       pf.product_class                     AS "PCLASS",
       pf.supplier_code                     AS "VND_NAME",
       coalesce(s.on_hand, 0)               AS "ON_HAND",
       coalesce(s.available, 0)             AS "AVAILABLE",
       coalesce(s.incoming, 0)              AS "INCOMING",
       coalesce(s.ordered, 0)               AS "ORDERED",
       coalesce(w.qty, 0)                   AS "WH2",
       w.cost_rub                           AS "WH2_COST_RUB",
       -- prices as of the month end: past months keep their values after new purchases
       -- PERF: three correlated subqueries per row, ~750 k index probes, most of the 22 s. One pass
       --   instead: read the price history of these parts once (purchase_price, avg_purchase_price,
       --   shipped PO prices) and join "as of" in pandas with pd.merge_asof(by="PTS_NO").
       (SELECT p.price_usd FROM pricing.purchase_price p
         WHERE p.part_number = k.part_number AND p.month_end <= k.month_end
         ORDER BY p.month_end DESC LIMIT 1)                                   AS "PP_USD",
       (SELECT a.avg_price_usd FROM pricing.avg_purchase_price a
         WHERE a.part_number = k.part_number AND a.month_end <= k.month_end
         ORDER BY a.month_end DESC LIMIT 1)                                   AS "AVG_PP",
       -- PERF: order_line_flow has an index on part_number only; (part_number, shipping_date)
       --   for the rows without SO would make this an index-only backward scan.
       (SELECT f.po_price_usd FROM reporting.order_line_flow f
         WHERE f.part_number = k.part_number AND f.so_number IS NULL
           AND f.shipping_date <= k.month_end AND f.po_price_usd > 0.01
         ORDER BY f.shipping_date DESC LIMIT 1)                               AS "SHIPPED_PP_USD"
FROM keys k
LEFT JOIN stock s         USING (month_end, part_number)
LEFT JOIN second_wh w     USING (month_end, part_number)
LEFT JOIN ref.part_pnl pp ON pp.part_number = k.part_number
LEFT JOIN ref.part_full pf ON pf.part_number = k.part_number
"""


def stock_values(start: str) -> pd.DataFrame:
    """One row per month end and part with any stock: quantities of both warehouses and
    the unit prices the report values them with (reports/stock/valuation.py)."""
    dates = month_last_dates(start)
    months = sorted({str((pd.Timestamp(d) + pd.offsets.MonthEnd(0)).date()) for d in dates})
    return query_frame("stock_values", STOCK_VALUES_SQL, {"dates": dates, "months": months},
                       parse_dates=["DATE"])


def last_snapshot_date() -> pd.Timestamp:
    frame = query_frame("stock_last_snapshot", "SELECT max(snapshot_date) AS d FROM inventory.stock_snapshot", {})
    return pd.Timestamp(frame["d"].iloc[0])


DAILY_AMOUNTS_SQL = """
-- unit prices come from pandas (valuation.unit_prices) as parallel arrays;
-- the database multiplies every snapshot row and returns one row per day
WITH price AS (
    SELECT * FROM unnest(CAST(:parts AS text[]), CAST(:months AS date[]),
                         CAST(:avl_usd AS float8[]), CAST(:avl_rub AS float8[]),
                         CAST(:inc_usd AS float8[]), CAST(:inc_rub AS float8[]),
                         CAST(:ord_usd AS float8[]), CAST(:ord_rub AS float8[]))
        AS p(part_number, month_end, avl_usd, avl_rub, inc_usd, inc_rub, ord_usd, ord_rub)
)
SELECT s.snapshot_date                  AS "DATE",
       sum(s.available * p.avl_usd)     AS "AVAILABLE_USD_AMT",
       sum(s.available * p.avl_rub)     AS "AVAILABLE_RUB_AMT",
       sum(s.incoming * p.inc_usd)      AS "INCOMING_USD_AMT",
       sum(s.incoming * p.inc_rub)      AS "INCOMING_RUB_AMT",
       sum(s.ordered * p.ord_usd)       AS "ORDERED_USD_AMT",
       sum(s.ordered * p.ord_rub)       AS "ORDERED_RUB_AMT"
FROM inventory.stock_snapshot s
JOIN price p ON p.part_number = s.part_number
            AND p.month_end = (date_trunc('month', s.snapshot_date) + interval '1 month - 1 day')::date
WHERE s.snapshot_date BETWEEN CAST(:start AS date) AND CAST(:end AS date)
GROUP BY 1
ORDER BY 1
"""


def daily_amounts(prices: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    """Value of the main warehouse on every snapshot day. prices: PTS_NO, DATE (month end) and
    the unit prices AVAILABLE_USD, AVAILABLE_RUB, INCOMING_*, ORDERED_* of that month. A part
    without a price in its month (not in stock at any month end) counts 0."""
    prices = prices.fillna(0)
    params = {"parts": prices["PTS_NO"].tolist(), "months": prices["DATE"].dt.strftime("%Y-%m-%d").tolist(),
              "start": start, "end": end}
    for kind, key in (("AVAILABLE", "avl"), ("INCOMING", "inc"), ("ORDERED", "ord")):
        for currency in ("USD", "RUB"):
            params[f"{key}_{currency.lower()}"] = prices[f"{kind}_{currency}"].astype(float).tolist()
    return query_frame("stock_daily_amounts", DAILY_AMOUNTS_SQL, params, parse_dates=["DATE"], cache=False)
