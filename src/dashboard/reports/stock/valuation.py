"""Valuation of the stock (D4.4): quantity x unit price, per month and part.

Each kind of stock has its own price, as in the old
get_group_stock; when it is missing or 0 the next price of the chain is used:

| stock                        | quantity           | own price               | then                         |
|------------------------------|--------------------|-------------------------|------------------------------|
| on hand, available           | snapshot           | unit cost               | purchase price -> avg PP     |
| incoming                     | snapshot           | last shipped PO price   | unit cost -> PP -> avg PP    |
| ordered                      | snapshot `ordered` | purchase price          | unit cost -> avg PP          |
| second warehouse             | its own table      | its own unit cost (RUB) | (unit cost -> PP -> avg PP)  |
|                              |                    |                         | x (1 + WH2_FALLBACK_MARKUP)  |

Prices are those of the month (purchase prices as of the month end), so a past
month keeps its value. RUB: the RUB unit cost, other prices x the average rate of
the month; the second warehouse in USD: RUB / that rate (as the old code).
"""

import numpy as np
import pandas as pd

KINDS = ("ON_HAND", "AVAILABLE", "INCOMING", "ORDERED")


def first_positive(frame: pd.DataFrame, columns: list[str]) -> pd.Series:
    """Row by row, the first value of the columns that is > 0 (NaN when none is)."""
    values = frame[columns].to_numpy(dtype=float, copy=True)   # Copy-on-Write: without copy, a read-only view
    values[~(values > 0)] = np.nan
    return pd.DataFrame(values, index=frame.index).bfill(axis=1).iloc[:, 0]


def unit_prices(frame: pd.DataFrame, markup: float = 0.0) -> pd.DataFrame:
    """Unit price per kind of stock and currency. frame: COST_USD, COST_RUB, PP_USD, AVG_PP,
    SHIPPED_PP_USD, WH2_COST_RUB, RATE (USD/RUB of the month)."""
    f = frame.assign(PP_RUB=frame["PP_USD"] * frame["RATE"],
                     AVG_RUB=frame["AVG_PP"] * frame["RATE"],
                     SHIPPED_RUB=frame["SHIPPED_PP_USD"] * frame["RATE"])
    usd = {"cost": "COST_USD", "pp": "PP_USD", "avg": "AVG_PP", "shipped": "SHIPPED_PP_USD"}
    rub = {"cost": "COST_RUB", "pp": "PP_RUB", "avg": "AVG_RUB", "shipped": "SHIPPED_RUB"}
    chains = {"ON_HAND": ["cost", "pp", "avg"],
              "AVAILABLE": ["cost", "pp", "avg"],
              "INCOMING": ["shipped", "cost", "pp", "avg"],
              "ORDERED": ["pp", "cost", "avg"]}
    prices = pd.DataFrame(index=frame.index)
    for kind, chain in chains.items():
        prices[f"{kind}_USD"] = first_positive(f, [usd[c] for c in chain])
        prices[f"{kind}_RUB"] = first_positive(f, [rub[c] for c in chain])
    fallback = first_positive(f, ["COST_RUB", "PP_RUB", "AVG_RUB"]) * (1 + markup)
    own = f["WH2_COST_RUB"].where(f["WH2_COST_RUB"] > 0)
    prices["WH2_RUB"] = own.fillna(fallback)
    prices["WH2_USD"] = prices["WH2_RUB"] / f["RATE"]
    return prices


def stock_amounts(frame: pd.DataFrame, markup: float = 0.0) -> pd.DataFrame:
    """frame + {KIND}_{USD|RUB}_AMT and NVK_{USD|RUB}_AMT (the column names of the old
    charts; NVK_* is the second warehouse). A quantity without any price counts 0."""
    prices = unit_prices(frame, markup)
    out = frame.copy()
    for currency in ("USD", "RUB"):
        for kind in KINDS:
            out[f"{kind}_{currency}_AMT"] = (frame[kind] * prices[f"{kind}_{currency}"]).fillna(0)
        out[f"NVK_{currency}_AMT"] = (frame["WH2"] * prices[f"WH2_{currency}"]).fillna(0)
    return out


def monthly_summary(amounts: pd.DataFrame, sales: pd.DataFrame, rates: pd.Series,
                    currency: str) -> pd.DataFrame:
    """Old get_stock_sum: totals per month, invoiced sales of the stock locations (fact and
    12-month rolling mean), rate, months / days on hand. sales: DATE, SA_USD, SA_RUB;
    rates: daily USD/RUB indexed by date."""
    columns = [f"{kind}_{currency}_AMT" for kind in KINDS] + [f"NVK_{currency}_AMT"]
    summary = amounts.groupby("DATE")[columns].sum()
    invoiced = sales.set_index("DATE")[f"SA_{currency}"].astype(float)
    summary["INVOICED_FACT"] = invoiced
    summary["INVOICED_ROLLING"] = invoiced.rolling(12).mean().round(0)
    monthly = rates.resample("ME").agg(["mean", "last"])
    summary["RATE_AVG"] = monthly["mean"]
    summary["RATE_LAST"] = monthly["last"]
    stock = summary[[f"AVAILABLE_{currency}_AMT", f"INCOMING_{currency}_AMT", f"NVK_{currency}_AMT"]].sum(axis=1)
    summary["MOH"] = stock / summary["INVOICED_ROLLING"]
    summary["DOH"] = (summary["MOH"] * 30).round()
    summary = summary.reset_index()
    summary["DATE_YM"] = summary["DATE"].dt.strftime("%Y-M%m")
    return summary


def available_by_rank(amounts: pd.DataFrame, currency: str) -> pd.DataFrame:
    """Old frames['rank_pclass_1']: available stock per month, product class and rank."""
    frame = (amounts.groupby(["DATE_YM", "PCLASS", "RANK"], as_index=False)[f"AVAILABLE_{currency}_AMT"].sum()
             .rename(columns={"PCLASS": "Product Class", "RANK": "Rank", f"AVAILABLE_{currency}_AMT": "AMOUNT"})
             .sort_values("DATE_YM"))
    frame.insert(3, "type", "3. Available")
    return frame
