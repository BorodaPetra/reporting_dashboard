# HCMR Parts Dashboard

[![lint](https://github.com/BorodaPetra/hcmr-dashboard/actions/workflows/lint.yml/badge.svg)](https://github.com/BorodaPetra/hcmr-dashboard/actions/workflows/lint.yml)

[Русский](README.ru.md) · **English**

A Flask reporting dashboard for a spare parts business: sales against budget, stock valuation, deliveries, a part card. The reports are built from queries to the views of a normalized PostgreSQL warehouse (`reporting.order_line_flow`, `ref.part_full`, `ref.part_pnl`, …). The screenshots show the demo database: anonymized data continued with synthetic data.

**Background.** The dashboard started as a pet project. It was then adopted into the daily work of the department and grew as new needs came up, running on a remote server inside the corporate network for about 30–50 users.

| Sales: sales against budget | Stock: stock valuation |
|---|---|
| [![Sales](docs/screenshots/sales.png)](docs/screenshots/sales.png) | [![Stock](docs/screenshots/stock.png)](docs/screenshots/stock.png) |
| **Parts Data: part card** | **Parts Data: supersession tree** |
| [![Parts Data](docs/screenshots/parts.png)](docs/screenshots/parts.png) | [![Supersessions](docs/screenshots/parts_tree.png)](docs/screenshots/parts_tree.png) |

**Stack:** Python 3.12 · Flask 3 (Flask-Login, Flask-WTF) · SQLAlchemy 2 + psycopg 3 · pandas 3 · Altair 6 / Vega-Lite 6 · Bootstrap 5 · gunicorn + nginx · Docker · uv

## What it does

- **Sales:** sales and orders by dealer group against the fiscal-year budget, accumulated outstanding orders, monthly gross profit, an interactive chart filtered by period, dealer, demand rank and product class, TOP-10 parts with an xlsx export. Budget upload (xlsx) by an administrator.
- **Mailing:** a daily report and a monthly breakdown by e-mail, by cron through the CLI or by an administrator's button.
- **Stock:** stock value in USD and RUB by month and demand rank, months on hand, weekly candles of the main warehouse, arrivals and dispatches, TOP-10 parts on free stock.
- **Delivery:** an uploaded container tracing file gets the supplier and the invoice amounts from the warehouse; a delivery status chart and table.
- **Parts Data:** look up one number (with suggestions), a list or an xlsx file. Part card with prices, demand, rank model, stock and replenishment; the supersession tree of the whole chain; the sales and purchase orders of the part.
- **Stop List:** upload of a part list and a flag in Parts Data.
- **Users and roles:** login, registration as an access request that an administrator approves, user and role management.

## How it works

- **Report state.** A report is built once in the background and lives in the process memory until the nightly load (`REPORT_REFRESH_TIME`). A warm-up at worker start builds every report in turn; the frames shared by Sales and Stock are built once per warm-up. During a rebuild the previous state stays visible. → [`reports/common/state.py`](src/dashboard/reports/common/state.py)
- **A report is a package.** Every report is a package in `reports/`: `register_blueprints` finds it, the page lives at `/report/<package>`.
- **Security.** Login required, CSRF on every POST, a CSP allowing only own scripts and nonces, upload checks (format, size, fixed file name), security headers. The database password is a Docker secret, not an environment variable.

## Endpoints

Every route except `/login` and `/register` needs a login; ✱ marks the ones for the Admin role. Every POST carries a CSRF token.

| Method | Path | What it does |
|---|---|---|
| GET, POST | `/login`, `/register`; GET `/logout` | sign in, access request, sign out |
| GET, POST | `/profile` | own profile |
| GET | `/users`, `/roles` ✱ | user and role tables; create, edit and delete under `/user-*`, `/role-*` ✱ |
| GET | `/` | home page with the report cards |
| GET | `/report/sales` | Sales report |
| POST | `/report/sales/process` | JSON: the detailed chart for the chosen period and dealers |
| POST | `/report/sales/upload` ✱ | budget xlsx of the fiscal year |
| POST | `/report/sales/send/<daily\|breakdown>` ✱ | send the mailing now |
| GET | `/report/sales/top_parts.xlsx`, `/report/stock/top_parts.xlsx` | TOP-10 as xlsx |
| GET | `/report/stock` | Stock report |
| GET, POST | `/report/delivery` | Delivery report; POST ✱ uploads the tracing file |
| GET | `/report/parts` | Parts Data page |
| POST | `/report/parts/processing` | JSON: data of the requested parts (`{"parts": [...]}`, up to 500) |
| GET | `/report/parts/suggest?q=` | JSON: part numbers starting with `q` |
| GET | `/report/parts/supersessions?part=` | JSON: supersession tree of the part |
| GET | `/report/parts/orders?part=` | JSON: sales and purchase orders of the part |
| GET, POST | `/stop-list`; POST `/stop-list/remove` | stop list; POST ✱ uploads or removes numbers |

## Running

**Requires:** Python 3.12, [uv](https://docs.astral.sh/uv/), PostgreSQL with the demo database `hcmr_demo` (the warehouse schema with anonymized and synthetic data; the database itself is not part of this repository).

```powershell
uv sync
# .env: SECRET_KEY=<random string>
#       DATABASE_URL=postgresql+psycopg://dashboard_app@localhost:5432/hcmr_demo  (password in pgpass.conf)
#       the other settings: see .env.example
uv run flask --app wsgi init-db
uv run flask --app wsgi create-admin admin
uv run flask --app wsgi run --debug

# mailing (cron on the server); by hand: the buttons on the Sales page (Admin)
uv run flask --app wsgi send-reports
```
Docker (gunicorn + nginx, database outside): [docs/deploy.md](docs/deploy.md) (in Russian).

> Demo data caveat: about 46 synthetic back-order lines to suppliers have no purchase price. Their cost counts as zero, so the gross profit of the synthetic period (after 2026-06-11) is about 40k USD too high.

## Layout
```
src/dashboard/
  __init__.py config.py cli.py    app factory, settings from the environment, flask commands
  uploads.py utils.py             shared by the whole app: upload checks, redirects
  authentication/ home/ stoplist/ app sections (blueprints)
  data/                           queries to the warehouse views, cache
  reports/
    common/                       shared by the reports: state and warm-up, shared frames,
                                  daily, dealer groups, prices, chart theme
    sales/ stock/ delivery/ parts/  one package per report: routes, report (build), charts, own frames
  templates/ static/
scripts/                          demo budget, reconciliation scripts (reconcile/)
instance/                         runtime files (uploads), not in git and not in the image
```

## License

[MIT](LICENSE). The UI is based on [Volt](https://themesberg.com/product/admin-dashboard/volt-bootstrap-5-dashboard) by Themesberg (MIT); its copyright notice is kept in `static/assets/css/volt.css`.
