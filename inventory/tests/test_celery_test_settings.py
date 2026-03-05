"""
Verify that Celery is configured for eager (synchronous) execution in the test environment.

CELERY_TASK_ALWAYS_EAGER = True  → tasks run synchronously inline (no broker needed)
CELERY_TASK_EAGER_PROPAGATES = True → exceptions propagate rather than being swallowed

These settings are set in cc/settings.py when CI=true.  In the local test suite they
are forced on by the conftest fixture below, ensuring task tests are reliable everywhere.
"""
import pytest
from django.conf import settings


@pytest.fixture(autouse=True)
def _force_celery_eager(settings):
    """Ensure Celery runs tasks eagerly for every test in this module."""
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CELERY_TASK_EAGER_PROPAGATES = True


class TestCeleryEagerModeSettings:
    """Assert that Celery eager-mode flags are active during test runs."""

    def test_celery_task_always_eager_is_true(self, settings):
        assert getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False) is True, (
            "CELERY_TASK_ALWAYS_EAGER must be True in the test environment so that "
            "Celery tasks execute synchronously without requiring a broker."
        )

    def test_celery_task_eager_propagates_is_true(self, settings):
        assert getattr(settings, "CELERY_TASK_EAGER_PROPAGATES", False) is True, (
            "CELERY_TASK_EAGER_PROPAGATES must be True so that task exceptions are "
            "re-raised and not silently swallowed during test runs."
        )

    def test_both_flags_are_true_together(self, settings):
        """Combined assertion — both flags must be set simultaneously."""
        always_eager = getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False)
        eager_propagates = getattr(settings, "CELERY_TASK_EAGER_PROPAGATES", False)
        assert always_eager and eager_propagates, (
            f"Expected both Celery eager flags to be True. "
            f"Got: CELERY_TASK_ALWAYS_EAGER={always_eager}, "
            f"CELERY_TASK_EAGER_PROPAGATES={eager_propagates}"
        )
