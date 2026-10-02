"""Configuration from the environment (.env next to wsgi.py is loaded automatically).

Required
  SECRET_KEY     signs the session cookie and CSRF tokens; must be the same
                 for all workers and survive restarts
Optional
  DATABASE_URL   default: postgresql+psycopg://dashboard_app@localhost:5432/hcmr_demo
                 no password in the URL: libpq reads it from pgpass.conf
  DEBUG          "True" for the development configuration
  URL_PREFIX, REPORTS_PREFIX, ASSETS_ROOT
  INSTANCE_PATH  runtime files (uploads); default: <project root>/instance
  REPORT_REFRESH_TIME       report states expire at this time of day (default 06:00)
  REPORT_WARMUP             build all reports at worker start and at REPORT_REFRESH_TIME (default True)
Dealer groups of the reports; real codes live only in the local .env
  STOCK_EXCLUDE_GROUPS      groups left out of the stock report, e.g. "G1,G2"
  BREAKDOWN_GROUP           the group of the monthly breakdown chart and mailing
  BREAKDOWN_SUBGROUPS       its sub-groups: "Label A:code1|code2,Label B:code3"
  DEALER_WAREHOUSE_LABELS   dealer code -> warehouse label, e.g. "100001:NORTH_WH,100002:SOUTH_WH"
  MINING_SUPPLIERS          parts of these suppliers are mining (PCLASS "M") whatever their HID
  DEMAND_WEIGHTS            weights of the last 12 / previous 12 / ... months in the weighted demand (0.5,0.3,0.2)
  HCMR_BUY_RATE             fixed buy rate coefficient shown in the parts report (commercial: local .env only)
  NVK_FALLBACK_MARKUP       stock report: markup on the fallback price of the second warehouse, e.g. 0.1 (local .env)
  SHARED_KEEP_MINUTES       how long the frames shared by the report builds stay in memory (30)
  STOCK_WAREHOUSE_NAMES     names of the main and the second warehouse in the stock charts: "Main WH,Second WH"
"""

import os

from dotenv import load_dotenv

load_dotenv()

DEFAULT_DATABASE_URL = "postgresql+psycopg://dashboard_app@localhost:5432/hcmr_demo"


def env_bool(name: str, default: bool = False) -> bool:
    """bool("False") is True in Python — parse the text instead."""
    value = os.getenv(name)
    return default if value is None else value.strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str) -> list[str]:
    return [item.strip() for item in os.getenv(name, "").split(",") if item.strip()]


def env_padded(name: str, default: list[str]) -> list[str]:
    """A list of exactly len(default) items: the given ones, the rest from the default."""
    given = env_list(name)[:len(default)]
    return given + default[len(given):]


def env_map(name: str) -> dict[str, str]:
    """ "k1:v1,k2:v2" -> {"k1": "v1", "k2": "v2"} """
    return dict(item.split(":", 1) for item in env_list(name) if ":" in item)


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY")

    URL_PREFIX = os.getenv("URL_PREFIX", "")
    REPORTS_PREFIX = os.getenv("REPORTS_PREFIX", "/report")
    ASSETS_ROOT = os.getenv("ASSETS_ROOT", "/static/assets")

    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}
    DATA_CACHE_TTL = int(os.getenv("DATA_CACHE_TTL", "900"))   # seconds (dashboard/data)
    REPORT_REFRESH_TIME = os.getenv("REPORT_REFRESH_TIME", "06:00")
    REPORT_WARMUP = env_bool("REPORT_WARMUP", True)

    STOCK_EXCLUDE_GROUPS = env_list("STOCK_EXCLUDE_GROUPS")
    BREAKDOWN_GROUP = os.getenv("BREAKDOWN_GROUP", "").strip() or None
    BREAKDOWN_SUBGROUPS = env_map("BREAKDOWN_SUBGROUPS")
    DEALER_WAREHOUSE_LABELS = env_map("DEALER_WAREHOUSE_LABELS")
    MINING_SUPPLIERS = env_list("MINING_SUPPLIERS")
    DEMAND_WEIGHTS = tuple(float(w) for w in env_list("DEMAND_WEIGHTS")) or (0.5, 0.3, 0.2)
    DEMAND_START = os.getenv("DEMAND_START", "2018-04-01")
    HCMR_BUY_RATE = float(os.getenv("HCMR_BUY_RATE", "").strip() or "nan")    # nan = not set -> "-"
    NVK_FALLBACK_MARKUP = float(os.getenv("NVK_FALLBACK_MARKUP", "").strip() or 0)
    SHARED_KEEP_MINUTES = float(os.getenv("SHARED_KEEP_MINUTES", "").strip() or 30)
    STOCK_WAREHOUSE_NAMES = env_padded("STOCK_WAREHOUSE_NAMES", ["Main WH", "Second WH"])

    MAX_CONTENT_LENGTH = 50 * 1024 * 1024       # uploads larger than 50 MB -> 413

    # e-mail (flask-mail); env_bool: the string "False" must not become True
    MAIL_SERVER = os.getenv("MAIL_SERVER", "").strip()
    MAIL_PORT = int(os.getenv("MAIL_PORT", "25") or 25)
    MAIL_USE_TLS = env_bool("MAIL_USE_TLS")
    MAIL_USE_SSL = env_bool("MAIL_USE_SSL")
    MAIL_USERNAME = os.getenv("MAIL_USERNAME", "").strip() or None
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD", "").strip() or None
    MAIL_DEFAULT_SENDER = os.getenv("MAIL_DEFAULT_SENDER", "").strip() or None

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_HTTPONLY = True


class ProductionConfig(Config):
    DEBUG = False
    SESSION_COOKIE_SECURE = True
    REMEMBER_COOKIE_SECURE = True


class DebugConfig(Config):
    DEBUG = True


def get_config():
    config = DebugConfig if os.getenv("DEBUG", "False") == "True" else ProductionConfig
    if not config.SECRET_KEY:
        raise RuntimeError("SECRET_KEY is not set (add it to .env)")
    return config
