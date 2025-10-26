# cc/__init__.py
"""
Package init for the cc Django project.

We *optionally* expose `celery_app` if Celery is installed. This prevents
Django management commands from crashing on machines that don't have Celery
in the virtualenv (e.g., fresh local dev).

If Celery isn't available, `celery_app` will be None.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

try:
    # Tries to import cc/celery.py which imports Celery itself.
    # Missing Celery (or any import-time issue) should not break Django startup.
    from .celery import app as celery_app  # type: ignore  # noqa: F401
except Exception as exc:  # pragma: no cover
    celery_app = None  # type: ignore
    # Keep this at INFO so it shows once in dev logs without being noisy.
    logger.info("Celery not available; continuing without it: %s", exc)

__all__ = ("celery_app",)


