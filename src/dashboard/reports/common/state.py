"""Report state: every report builds its data once, lazily, in the background.

    from dashboard.reports.common.state import report_state

    def build() -> DeliveryState:          # queries + pandas, may take minutes
        ...

    @blueprint.route(report_url)
    def index():
        state = report_state("delivery", build)

* The first request starts build() in a background thread and gets the
  "report is being prepared" page (202, auto-refresh). The build does not run
  inside the request: a minute-long request would hit the gunicorn timeout.
* The state is valid until the next REPORT_REFRESH_TIME (default 06:00, after
  the nightly warehouse load). An expired state is still served while the new
  one is built in the background (stale-while-revalidate).
* One build per report at a time: requests that arrive during a build wait
  for it instead of starting their own.
* invalidate(name) drops the state, e.g. after a file upload the report
  depends on. A build that was already running is discarded when it ends.
* REPORT_BUILD_SYNC = True (tests) builds inside the request.
* Warm-up (REPORT_WARMUP, default on): one background thread builds every
  registered report, one after another, when the worker starts and again at
  every REPORT_REFRESH_TIME, so nobody waits for "preparing" in the morning.
  Started by the gunicorn post_worker_init hook, or by the first request under
  `flask run`; never by CLI commands (they serve no requests).
"""

import logging
import threading
import time as clock
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Any, Callable

from flask import Flask, current_app

log = logging.getLogger(__name__)


class ReportNotReady(Exception):
    """The report is being built; the app shows the "preparing" page."""


class ReportBuildFailed(Exception):
    """The last build raised; shown once, the next request starts a new build."""


@dataclass
class _Entry:
    state: Any = None
    built_at: datetime | None = None
    building: bool = False
    error: BaseException | None = None
    generation: int = 0          # bumped by invalidate(): results of older builds are dropped


def next_refresh(built_at: datetime, refresh_at: time) -> datetime:
    """The first refresh moment strictly after built_at."""
    moment = datetime.combine(built_at.date(), refresh_at)
    return moment if moment > built_at else moment + timedelta(days=1)


class ReportStates:
    def __init__(self, app: Flask):
        self.app = app
        self.refresh_at = time.fromisoformat(app.config.get("REPORT_REFRESH_TIME", "06:00"))
        self._entries: dict[str, _Entry] = {}
        self._builders: dict[str, Callable[[], Any]] = {}
        self._lock = threading.Lock()
        self._warmup_started = False

    def get(self, name: str, builder: Callable[[], Any]) -> Any:
        with self._lock:
            entry = self._entries.setdefault(name, _Entry())
            if entry.state is not None and datetime.now() < next_refresh(entry.built_at, self.refresh_at):
                return entry.state
            if entry.error is not None and not entry.building:
                error, entry.error = entry.error, None
                raise ReportBuildFailed(name) from error
            start = not entry.building
            if start:
                entry.building = True
            generation, stale = entry.generation, entry.state

        if start:
            if self.app.config.get("REPORT_BUILD_SYNC"):
                self._build(name, builder, generation)
                return self.get(name, builder)
            threading.Thread(target=self._build, args=(name, builder, generation),
                             name=f"build-{name}", daemon=True).start()
        if stale is not None:
            return stale
        raise ReportNotReady(name)

    def register(self, name: str, builder: Callable[[], Any]) -> None:
        """Reports known to the warm-up (register_blueprints registers every report.py)."""
        self._builders[name] = builder

    def refresh_all(self) -> None:
        """Build every registered report, one after another (not in parallel: memory and
        database load); a report that is being built by a request is skipped."""
        for name, builder in list(self._builders.items()):
            with self._lock:
                entry = self._entries.setdefault(name, _Entry())
                if entry.building:
                    continue
                entry.building = True
                generation = entry.generation
            self._build(name, builder, generation)

    def start_warmup(self) -> bool:
        """Start the warm-up thread once per process; False if disabled or already running."""
        if self._warmup_started or not self.app.config.get("REPORT_WARMUP"):
            return False
        with self._lock:
            if self._warmup_started:
                return False
            self._warmup_started = True
        threading.Thread(target=self._warmup_loop, name="report-warmup", daemon=True).start()
        return True

    def _warmup_loop(self) -> None:
        while True:
            log.info("report warm-up: building %s", ", ".join(self._builders))
            self.refresh_all()
            wake = next_refresh(datetime.now(), self.refresh_at)
            clock.sleep(max(1.0, (wake - datetime.now()).total_seconds()))

    def invalidate(self, name: str) -> None:
        with self._lock:
            entry = self._entries.setdefault(name, _Entry())
            entry.state, entry.built_at, entry.error = None, None, None
            entry.generation += 1

    def info(self) -> dict[str, dict]:
        with self._lock:
            return {name: {"built_at": e.built_at, "building": e.building, "failed": e.error is not None}
                    for name, e in self._entries.items()}

    def _build(self, name: str, builder: Callable[[], Any], generation: int) -> None:
        started = clock.perf_counter()
        state, error = None, None
        try:
            with self.app.app_context():
                state = builder()
        except Exception as exc:        # noqa: BLE001 - any failure of a report must reach the page
            log.exception("report %s: build failed", name)
            error = exc
        with self._lock:
            entry = self._entries.setdefault(name, _Entry())
            entry.building = False
            if entry.generation != generation:          # invalidated while building: result is stale
                return
            if error is not None:
                entry.error = error
            else:
                entry.state, entry.built_at = state, datetime.now()
                log.info("report %s: built in %.1f s", name, clock.perf_counter() - started)


def init_app(app: Flask) -> None:
    app.extensions["report_states"] = ReportStates(app)


def report_state(name: str, builder: Callable[[], Any]) -> Any:
    """The built state of a report, or ReportNotReady / ReportBuildFailed."""
    return current_app.extensions["report_states"].get(name, builder)


def invalidate(name: str) -> None:
    current_app.extensions["report_states"].invalidate(name)
