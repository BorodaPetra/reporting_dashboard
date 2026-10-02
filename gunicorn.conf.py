"""gunicorn settings, read from the working directory by default: gunicorn wsgi:app (Docker).

One worker: report states live in the worker's memory, every worker would build
and hold its own copy. Threads serve requests in parallel inside that worker; a report
that is still building answers "being prepared" instead of blocking (reports/state.py).
"""

bind = "0.0.0.0:8000"
workers = 1
worker_class = "gthread"
threads = 8
timeout = 120                 # heartbeat of the worker process, not a limit per request
accesslog = "-"
loglevel = "info"
capture_output = True         # print() of the legacy code goes to the log
enable_stdio_inheritance = True


def post_worker_init(worker):
    """Build all reports in the background as soon as the worker is up (warm-up):
    the first user of the day does not wait for "The report is being prepared"."""
    worker.wsgi.extensions["report_states"].start_warmup()
