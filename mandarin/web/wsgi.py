"""WSGI entry point for gunicorn / production servers."""

from . import create_app

app = create_app()
