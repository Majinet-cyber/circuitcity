"""
Guardrail: verify the `reports` Django app is importable.

This test exists to catch the case where reports/ is accidentally
gitignored or deleted. If this test is missing from the repo, the
CI run will silently skip it — but if it is present and the app is
not importable, the test suite fails before Render deployment.
"""
import importlib

import pytest
from django.apps import apps


@pytest.mark.critical
def test_reports_app_is_installed():
    """reports must be in INSTALLED_APPS and registered with Django."""
    assert apps.is_installed("reports"), (
        "The 'reports' app is missing from INSTALLED_APPS or cannot be imported. "
        "Check that reports/ exists in the repo and is not gitignored."
    )


@pytest.mark.critical
def test_reports_modules_importable():
    """Core reports modules must be importable (catches missing files)."""
    for module_name in (
        "reports",
        "reports.apps",
        "reports.urls",
        "reports.views",
        "reports.kpis",
        "reports.services",
        "reports.services.context_defaults",
    ):
        mod = importlib.import_module(module_name)
        assert mod is not None, f"Could not import {module_name}"
