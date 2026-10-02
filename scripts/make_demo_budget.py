"""Demo sales budget from the real budget.xlsx, without real data in the demo database.

    uv run python scripts/make_demo_budget.py N:/path/to/budget.xlsx

* Real and demo dealer groups are paired by their rank in sales of the last full
  fiscal year (largest with largest): the demo codes are anonymised, so
  there is no key to map them, and the pairing is never printed or stored.
* Every group's amounts are multiplied by a random factor 0.75..1.25 (the price
  factors of the anonymisation) and rounded: the demo budget has the shape of a
  real one, not its values.
* Written to app.sales_budget of the DEMO database for the current fiscal year.
"""

import random
import sys

import pandas as pd
from sqlalchemy import create_engine, text

sys.path.insert(0, "tests")
from conftest import TestConfig  # noqa: E402  (DATABASE_URL of .env = the demo database)

from dashboard import create_app, db  # noqa: E402
from dashboard.reports.sales import budget  # noqa: E402

REAL_URL = "postgresql+psycopg://dashboard_app@localhost:5432/hcmr"
SALES_BY_GROUP = text("""
    SELECT dealer_group, sum(so_net_amount_usd) AS amount
    FROM reporting.order_line_flow
    WHERE so_invoice_date >= :start AND so_invoice_date < :end
      AND dealer_group NOT IN ('OTHER', 'DEPOT') AND so_status <> 'A'
    GROUP BY dealer_group
""")


def ranked_groups(engine, start, end) -> list[str]:
    with engine.connect() as conn:
        rows = conn.execute(SALES_BY_GROUP, {"start": start, "end": end}).all()
    return [group for group, _ in sorted(rows, key=lambda r: r.amount or 0, reverse=True)]


def main(path: str) -> None:
    fy = budget.current_fy()
    start, end = f"{fy - 1}-04-01", f"{fy}-04-01"                  # the last full fiscal year
    real_budget = budget.parse_budget(pd.read_excel(path))
    app = create_app(TestConfig)
    real = ranked_groups(create_engine(REAL_URL), start, end)
    with app.app_context():
        demo = ranked_groups(db.engine, start, end)
        missing = set(real_budget["group_code"]) - set(real)
        if missing or len(real) != len(demo):
            raise SystemExit(f"cannot pair groups: {len(real)} real, {len(demo)} demo, {len(missing)} budget groups without sales")
        pairing = dict(zip(real, demo))
        rng = random.SystemRandom()
        factors = {group: rng.uniform(0.75, 1.25) for group in real}
        demo_budget = real_budget.assign(
            amount_k_usd=[round(a * factors[g]) for g, a in zip(real_budget["group_code"], real_budget["amount_k_usd"])],
            group_code=real_budget["group_code"].map(pairing),
        )
        with app.test_request_context():
            count = budget.replace_budget(demo_budget, fy)
        db.session.execute(db.update(budget.SalesBudget).where(budget.SalesBudget.fy == fy)
                           .values(uploaded_by="scripts/make_demo_budget.py"))
        db.session.commit()
    print(f"demo budget FY{fy}: {count} values for groups {sorted(demo_budget['group_code'].unique())}")


if __name__ == "__main__":
    main(sys.argv[1])
