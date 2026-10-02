"""D4.4 reconciliation: stock quantities against the old pickles.

The old stock report never produced amounts (see reports/stock/report.py),
so only its inputs can be compared: stock_avl.pkl / stock_onh.pkl, available and
on-hand quantity per part at every month end (summed over JV), 2022-09 .. 2026-05.
"""

import pandas as pd

import common
from dashboard.data import query_frame
from dashboard.data.stock import month_last_dates

QUANTITIES_SQL = """
SELECT (date_trunc('month', snapshot_date) + interval '1 month - 1 day')::date AS "DATE",
       part_number AS "PTS_NO", sum(available) AS "AVL", sum(on_hand) AS "ONH"
FROM inventory.stock_snapshot
WHERE snapshot_date = ANY (CAST(:dates AS date[]))
GROUP BY 1, 2
"""

with common.app().app_context():
    new = query_frame("reconcile_stock", QUANTITIES_SQL, {"dates": month_last_dates("2022-09-01")},
                      parse_dates=["DATE"])

for pkl, column in (("stock_avl", "AVL"), ("stock_onh", "ONH")):
    common.section(f"{column}: {pkl}.pkl vs the last snapshot of each month")
    old = pd.read_pickle(common.PKL / f"{pkl}.pkl").fillna(0)
    months = old.columns.intersection(pd.DatetimeIndex(new["DATE"].unique()))
    common.row("months: old / new / both", len(old.columns), new["DATE"].nunique(), len(months))
    wide = new.pivot_table(index="PTS_NO", columns="DATE", values=column, aggfunc="sum").reindex(columns=months)
    old = old[months]
    old, wide = old.loc[(old != 0).any(axis=1)], wide.loc[(wide.fillna(0) != 0).any(axis=1)]
    parts, _, _ = common.compare_keys(old.index, wide.index, "parts with stock")
    common.compare_numbers(old.loc[parts].stack(), wide.loc[parts].fillna(0).stack(), f"{column} per part and month")
    per_month = (old.sum() - wide.fillna(0).sum()).abs() / old.sum()
    common.row("months with total off by > 0.1 %", int((per_month > 0.001).sum()), len(months))
    common.row("  which", ", ".join(f"{m:%Y-%m}" for m in per_month[per_month > 0.001].index))
    common.row("differing cells by month (top 3)",
               (old.loc[parts] != wide.loc[parts].fillna(0)).sum().nlargest(3).rename(lambda m: f"{m:%Y-%m}").to_dict())
