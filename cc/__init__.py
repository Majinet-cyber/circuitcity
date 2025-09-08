# cc/__init__.py
from __future__ import annotations

# Expose the Celery app on package import
from .celery import app as celery_app  # noqa: F401

__all__ = ("celery_app",)
