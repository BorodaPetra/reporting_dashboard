"""D4.2 reconciliation: the prepared `daily` (reports/daily.py) vs the old daily.pkl.

Rows are matched on (SO_NUM, ITEM, PO_NUM) + running number within the key.
Only lines ordered before the pickle snapshot are compared.
"""

import common
from common import KEY, differ, keyed

from dashboard.reports.common.daily import prepared_daily

SKIP = {"TODAY", "RANK"}          # compared separately (RANK: scripts/reconcile/parts.py)

old = common.old_daily()
cut = common.snapshot(old)
with common.app().app_context():
    new = prepared_daily()
started = new["SO_DATE"].fillna(new["PO_DATE"])
new = new[started < cut]
print(f"old {len(old):,} rows, new {len(new):,} rows ordered before {cut.date()}")

common.section("rows")
o, n = keyed(old), keyed(new)
both, only_old, only_new = common.compare_keys(o.index, n.index, "lines")

common.section("columns on common lines: differ / total")
cols = [c for c in old.columns if c in new.columns and c not in SKIP and c not in KEY]
missing = [c for c in old.columns if c not in new.columns and c not in SKIP]
ob, nb = o.loc[both, cols], n.loc[both, cols]
res = {c: differ(ob[c], nb[c]) for c in cols}
for c, bad in sorted(res.items(), key=lambda kv: -kv[1]):
    if bad:
        common.row(c, bad, len(both))
common.row("identical columns", sum(v == 0 for v in res.values()), "of", len(res))
common.row("columns missing in new", missing)

common.section("sales by group and invoice month (SA_USD, K USD), months before the snapshot")
groups = [g for g in old["DLR_META"].dropna().unique() if (old["DLR_META"] == g).sum() > 50_000]
def monthly(frame):
    frame = frame[frame["DLR_META"].isin(groups) & (frame["SO_INV_DATE"] < cut.replace(day=1))]
    return frame.groupby(["DLR_META", "SO_INV_DATE_YM"])["SA_USD"].sum().astype(float) / 1000
mo, mn = monthly(old), monthly(new)
idx = mo.index.union(mn.index)
mo, mn = mo.reindex(idx, fill_value=0), mn.reindex(idx, fill_value=0)
diff = (mo - mn).abs()
common.row("group-months", len(idx))
common.row("  differ > 0.5 K USD", int((diff > 0.5).sum()))
common.row("  total old / new (K USD)", f"{mo.sum():,.1f}", f"{mn.sum():,.1f}")
by_year = (mo - mn).groupby(mo.index.get_level_values(1).str[:4]).sum().round(1)
common.row("  old - new by year", by_year.to_dict())
