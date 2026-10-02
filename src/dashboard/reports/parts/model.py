"""Demand model of the parts report (D4.3).

Pure functions over small frames (the requested parts, or every chain for the
ranks of the sales / stock reports). Rules of the old uframe_new.handle_demand /
get_demand_stats, with these changes:
* wavg: weighted by recency (last 12 months, the 12 before, the 12 before
  those) instead of fixed weights per calendar year;
* DEAD / ZOMBIE fixed (see stock_health).

"""

import numpy as np
import pandas as pd
from scipy.stats import norm

YM = "%Y-M%m"                         # the month label of the old frames: 2026-M09
SERVICE_LEVEL = 0.95                  # target service rate of the stock levels
LEAD_TIME_MONTHS = 3
RANK_LABELS = [(10, "A"), (6, "B"), (3, "C"), (1, "D")]     # months with demand in the previous 12


def month_range(start: str, end: pd.Timestamp) -> pd.DatetimeIndex:
    return pd.date_range(pd.Timestamp(start) + pd.offsets.MonthEnd(0), end + pd.offsets.MonthEnd(0), freq="ME")


def demand_matrix(demand: pd.DataFrame, start: str, today: pd.Timestamp) -> pd.DataFrame:
    """PNL x month ("2026-M09") quantities, every month from start to the current one (old: demand.m)."""
    months = month_range(start, today)
    matrix = (demand.groupby(["PNL", "DATE"])["QTY"].sum().unstack("DATE")
              .reindex(columns=months, fill_value=0).fillna(0))
    matrix.columns = matrix.columns.strftime(YM)
    return matrix


def label_rank(hits: float) -> str:
    for threshold, label in RANK_LABELS:
        if hits >= threshold:
            return label
    return "E"


def rank_table(matrix: pd.DataFrame) -> pd.DataFrame:
    """Rank per PNL and month: months with demand in the PREVIOUS 12 months (the month
    itself not included) -> A 10-12, B 6-9, C 3-5, D 1-2, E 0. Includes next month, as
    the old table did; the first 12 months (no full history) are left out."""
    hits = (matrix > 0).astype(int)
    next_month = (pd.Period(matrix.columns[-1].replace("-M", "-"), "M") + 1).strftime(YM)
    hits[next_month] = 0
    rolled = hits.T.shift(1).rolling(12).sum().T.iloc[:, 12:]
    # PERF: label_rank runs in Python for every cell - ~3 M cells for the ranks of all chains
    # (daily.demand_ranks). Vectorised: np.select([v >= 10, v >= 6, v >= 3, v >= 1], list("ABCD"), "E")
    # on rolled.to_numpy(), then a DataFrame with the same index / columns.
    return rolled.apply(lambda col: col.map(label_rank))


def weighted_average(matrix: pd.DataFrame, weights: tuple[float, ...]) -> pd.Series:
    """Recency-weighted monthly average: mean of the last 12 months x w1, of the 12 before
    x w2, ... (replaces the fixed weights per calendar year)."""
    parts = []
    for i, weight in enumerate(weights):
        window = matrix.iloc[:, max(0, matrix.shape[1] - 12 * (i + 1)):matrix.shape[1] - 12 * i]
        parts.append(window.mean(axis=1) * weight)
    return (sum(parts) / sum(weights)).round(2)


def demand_stats(demand: pd.DataFrame, matrix: pd.DataFrame, weights: tuple[float, ...],
                 stop_flags: pd.Series, today: pd.Timestamp) -> pd.DataFrame:
    """Statistics per PNL (old: get_demand_stats), columns as prettify_outupt expects."""
    z = round(-1 * norm.ppf(1 - SERVICE_LEVEL), 3)
    lt = LEAD_TIME_MONTHS
    stats = pd.DataFrame(index=matrix.index)
    stats["sum"] = matrix.sum(axis=1)
    stats = stats[stats["sum"] > 0]
    m = matrix.loc[stats.index]
    stats["sum_12"] = m.iloc[:, -12:].sum(axis=1)
    stats["sum_24"] = m.iloc[:, -24:].sum(axis=1)
    stats["avg_12"] = m.iloc[:, -12:].mean(axis=1)
    stats["avg_24"] = m.iloc[:, -24:].mean(axis=1)
    stats["std_24"] = m.iloc[:, -24:].std(axis=1, ddof=1)
    stats["wavg"] = weighted_average(m, weights)
    hits = (m > 0).sum(axis=1)
    stats["hits"] = hits
    stats["adi"] = m.shape[1] / hits                                  # average interval between demand months
    stats["freq"] = demand.groupby("PNL")["ORDERS"].sum()
    last = demand.groupby("PNL")["LAST_ORDER"].max()
    stats["dmd_last"] = last
    stats["dmd_recency"] = ((today - last).dt.days / 30).round(2)
    stats["dmd_once"] = np.where(hits == 1, "Y", "N")
    ranks = rank_table(matrix).loc[stats.index]
    # PERF: DataFrame.mode(axis=1) goes row by row; for thousands of chains count the labels
    # instead: ranks.stack().groupby(level=0).agg(lambda s: s.value_counts().idxmax()) or a crosstab + idxmax.
    # reindex: without a part with demand the mode has no column 0 (the request of one
    # part without demand answered 500)
    stats["rank_most"] = ranks.mode(axis=1).reindex(columns=[0])[0]
    stats["rank_end"] = ranks.iloc[:, -1]
    stats["stop_proc"] = stats.index.map(stop_flags).fillna("N")
    consumers = demand.groupby(["PNL", "DLR_META"])["QTY"].sum().unstack("DLR_META")
    stats["MC"] = consumers.idxmax(axis=1)
    stats["stock_flag"] = np.where((stats["dmd_once"] == "N") & (stats["dmd_recency"] <= 24)
                                   & (stats["stop_proc"] == "N"), "Y", "N")
    stats["AMC"] = (stats["sum_24"] / 24).round(1)
    stats["SL"], stats["LT"] = SERVICE_LEVEL, lt
    for suffix, avg in (("", stats["avg_24"]), ("_wavg", stats["wavg"])):
        # as in the old code: z x (the root rounded and truncated), not round(z x root)
        ss = z * np.sqrt(stats["std_24"].fillna(0) ** 2 * lt + (avg * lt * 0.1) ** 2).round(1).astype(int)
        ltd = avg * lt
        rop = np.where(ltd > 1, ss + ltd, ss + 1)
        stats[f"SS{suffix}"], stats[f"LTD{suffix}"], stats[f"ROP{suffix}"] = ss, ltd, rop
        stats[f"SMAX{suffix}"] = np.where(avg > 1, rop + avg, rop).round(0).astype(int)
    return stats


def demand_age_frame(demand: pd.DataFrame) -> pd.DataFrame:
    """Rows (PNL, SO_DATE) for uframe_new.get_demand_age: the last order of each month
    stands for the orders of that month (the function only needs the latest date)."""
    return demand.groupby(["PNL", "DATE"], as_index=False)["LAST_ORDER"].max().rename(columns={"LAST_ORDER": "SO_DATE"})


def stock_health(extended: pd.DataFrame) -> pd.DataFrame:
    """The two bugs of the old DEAD / ZOMBIE flags, fixed:
    * DEAD: the old rule is right, but it got the classes AFTER first_adjustments
      recoded them (C -> CE, CM -> C/M), so construction parts were never dead. The
      rule of uframe_new.get_extended_stock is kept; it just gets the classes of the
      warehouse (M / C / CM / OTHER) - see report.py, nothing to do here;
    * ZOMBIE compared the flag 'Y'/'N' with 1 and was never set: now "in the stop list
      and not dead" (the stop list arrives in D5; until then every flag is 'N')."""
    extended = extended.copy()
    extended["ZOMBIE"] = ((extended["STOP_FLAG"] == "Y") & (extended["DEAD"] == 0)).astype(int)
    return extended
