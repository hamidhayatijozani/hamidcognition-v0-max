"""Compatibility entry point for WSGI servers and Flask tests.

The canonical Flask application lives in api.server. This module keeps the
stable api.app:app import path used by deployment tooling and tests.
"""
from .server import app

__all__ = ["app"]
