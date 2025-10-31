# conftest.py — pytest config to make tests stable & fast

import os
import pytest

# Ensure Django settings are discoverable for pytest
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cc.settings")


# --- Use syncdb-style DB setup (no migrations) -------------------------------
# This prevents duplicate-index errors like "sale_created_at_idx already exists".
@pytest.fixture(scope="session")
def django_db_use_migrations():
    return False  # tell pytest-django to skip migrations and create tables directly


# You can also skip keepdb so a fresh transient DB is used each run.
@pytest.fixture(scope="session")
def django_db_keepdb():
    return False


# --- Give every test DB access by default ------------------------------------
@pytest.fixture(autouse=True)
def _enable_db_for_all_tests(db):
    # Depending on the db fixture is enough to trigger DB setup
    # (tables created once per session in syncdb mode).
    pass


# --- Relax settings so Client() requests are resilient in tests --------------
@pytest.fixture(autouse=True)
def _relaxed_test_settings(settings):
    settings.SECURE_SSL_REDIRECT = False
    settings.ALLOWED_HOSTS = ["*", "testserver", "localhost", "127.0.0.1"]
    # Avoid needing hashed-manifest during template/static lookups
    settings.STATICFILES_STORAGE = "django.contrib.staticfiles.storage.StaticFilesStorage"
    # Speed up password hashing in tests
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
