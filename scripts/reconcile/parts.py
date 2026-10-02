"""D4.3 reconciliation: parts report (SQL-first) against the old pickles.

1. RANK of the prepared daily vs daily.pkl (the old demand model wrote it there),
   common lines, months before the snapshot.
2. Part card fields: parts_master() vs partsmaster.pkl, common parts.
3. Monthly unit cost: uframe.handle_prices on the warehouse vs cost_rub.pkl / cost_usd.pkl.
"""

import pandas as pd

import common
from common import keyed
from dashboard.reports.common.daily import cost_prices, prepared_daily
from dashboard.reports.parts.report import parts_master

old_daily = common.old_daily()
cut = common.snapshot(old_daily)

with common.app().app_context():
    common.section("1. RANK on common daily lines (months before the snapshot)")
    new_daily = prepared_daily()
    o, n = keyed(old_daily), keyed(new_daily)
    both = o.index.intersection(n.index)
    ob, nb = o.loc[both, ["RANK", "DATE_YM"]], n.loc[both, ["RANK"]]
    months = ob["DATE_YM"] < cut.strftime("%Y-M%m")
    old_rank, new_rank = ob.loc[months, "RANK"].fillna("F"), nb.loc[months, "RANK"].fillna("F")
    common.row("lines compared", int(months.sum()))
    common.row("same rank", f"{(old_rank == new_rank).mean():.1%}")
    common.row("one step apart (A-B, B-C, ...)",
               f"{((old_rank != new_rank) & (abs(old_rank.map(ord) - new_rank.map(ord)) == 1)).mean():.1%}")
    pairs = pd.crosstab(old_rank, new_rank)
    print("    rows: old rank, columns: new rank\n" +"\n".join("    " + line for line in pairs.to_string().splitlines()))

    common.section("2. part card: partsmaster.pkl vs parts_master()")
    old_pm = pd.read_pickle(common.PKL / "partsmaster.pkl").drop_duplicates("PTS_NO", keep="last").set_index("PTS_NO")
    sample = old_pm.index[:20000]              # the per-request code path, on a large sample
    new_pm = parts_master(pd.Index(sample)).drop_duplicates("PTS_NO", keep="last").set_index("PTS_NO")
    common_parts = sample.intersection(new_pm.index)
    common.row("parts: sample / found", len(sample), len(common_parts))
    for col in ["JV", "DESCR", "VND_NAME", "PCLASS", "HID", "TNVED", "CAT", "PNL", "COO"]:
        common.compare_labels(old_pm.loc[common_parts, col], new_pm.loc[common_parts, col], col)
    common.compare_numbers(old_pm.loc[common_parts, "WEIGHT"], new_pm.loc[common_parts, "WEIGHT"], "WEIGHT", tol=0.001)
    common.compare_numbers(old_pm.loc[common_parts, "DLP"], new_pm.loc[common_parts, "DLP"], "DLP")

    common.section("3. monthly unit cost vs cost_rub.pkl / cost_usd.pkl")
    price = cost_prices()
    for currency in ("RUB", "USD"):
        old = pd.read_pickle(common.PKL / f"cost_{currency.lower()}.pkl")
        old = old[old["DATE"] < cut].set_index(["PTS_NO", "DATE_YM"])[f"COST_{currency}"]
        new = getattr(price, f"cost_{currency.lower()}").set_index(["PTS_NO", "DATE_YM"])[f"COST_{currency}"]
        keys = old.index.intersection(new.index)
        common.row(f"{currency}: old / new / both", len(old), len(new), len(keys))
        common.compare_numbers(old.loc[keys], new.loc[keys], f"COST_{currency}", tol=0.01 if currency == "USD" else 0.5)
