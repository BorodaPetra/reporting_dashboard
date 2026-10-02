# Dashboard image: uv installs the locked dependencies, gunicorn serves wsgi:app.
#   docker compose up -d --build
FROM python:3.12-slim

# the uv of the lock file (uv_build >=0.12.18,<0.13 in pyproject.toml)
COPY --from=ghcr.io/astral-sh/uv:0.12.18 /uv /bin/uv

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# dependencies first: this layer is rebuilt only when pyproject.toml / uv.lock change
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .
RUN uv sync --frozen --no-dev

# not root: the instance folder (uploads, a volume in compose) is the only writable place
RUN useradd --create-home --uid 1000 app && mkdir /app/instance && chown app /app/instance
USER app

EXPOSE 8000
ENTRYPOINT ["sh", "/app/docker-entrypoint.sh"]
CMD ["gunicorn", "wsgi:app"]         # settings: ./gunicorn.conf.py, read by default
