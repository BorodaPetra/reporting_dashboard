"""WSGI entry point: gunicorn wsgi:app / flask --app wsgi run."""

from dashboard import create_app

app = create_app()
