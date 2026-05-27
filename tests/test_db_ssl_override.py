"""
Test for database SSL mode override logic.

This test ensures that the final SSL override logic correctly enforces:
- CI + local DB → sslmode=disable
- Production → sslmode=require
- SQLite configs are not affected
- Overrides cannot be bypassed (even if DATABASE_URL contains ?sslmode=require in CI)
"""
import os
import pytest
from unittest.mock import patch

# Import the helper functions from settings
# We use a try/except to handle cases where settings might not be fully importable
# If that fails, we'll use pytest.mark.skip to skip these tests
try:
    from cc.settings import (
        _is_ci_environment,
        _is_local_db_host,
        _detect_local_db_from_config,
        _force_db_sslmode,
        _apply_final_ssl_override,
    )
except ImportError:
    # Fallback: define locally if import fails (shouldn't happen in normal test runs)
    pytest.skip("Could not import SSL override functions from cc.settings", allow_module_level=True)


class TestSSLOverride:
    """Test cases for SSL mode override logic."""
    
    def test_ci_localhost_db_gets_disable(self):
        """CI + localhost DB → result sslmode == 'disable'"""
        with patch.dict(os.environ, {"CI": "true"}, clear=False):
            databases = {
                "default": {
                    "ENGINE": "django.db.backends.postgresql",
                    "HOST": "localhost",
                    "NAME": "test_db",
                }
            }
            final_sslmode, ci_detected, local_db_detected = _apply_final_ssl_override(
                databases, "postgres://user:pass@localhost:5432/test_db"
            )
            
            assert final_sslmode == "disable"
            assert ci_detected is True
            assert local_db_detected is True
            assert databases["default"]["OPTIONS"]["sslmode"] == "disable"
    
    def test_non_ci_production_host_gets_require(self):
        """non-CI + production host → sslmode == 'require'"""
        with patch.dict(os.environ, {}, clear=True):
            # Ensure CI is not set
            if "CI" in os.environ:
                del os.environ["CI"]
            if "GITHUB_ACTIONS" in os.environ:
                del os.environ["GITHUB_ACTIONS"]
            
            databases = {
                "default": {
                    "ENGINE": "django.db.backends.postgresql",
                    "HOST": "prod-db.example.com",
                    "NAME": "prod_db",
                }
            }
            final_sslmode, ci_detected, local_db_detected = _apply_final_ssl_override(
                databases, "postgres://user:pass@prod-db.example.com:5432/prod_db"
            )
            
            assert final_sslmode == "require"
            assert ci_detected is False
            assert local_db_detected is False
            assert databases["default"]["OPTIONS"]["sslmode"] == "require"
    
    def test_ci_with_sslmode_require_in_url_still_gets_disable(self):
        """If DATABASE_URL includes ?sslmode=require in CI → still ends with 'disable'"""
        with patch.dict(os.environ, {"CI": "true"}, clear=False):
            databases = {
                "default": {
                    "ENGINE": "django.db.backends.postgresql",
                    "HOST": "localhost",
                    "NAME": "test_db",
                    "OPTIONS": {
                        "sslmode": "require",  # This should be overridden
                    },
                }
            }
            final_sslmode, ci_detected, local_db_detected = _apply_final_ssl_override(
                databases, "postgres://user:pass@localhost:5432/test_db?sslmode=require"
            )
            
            assert final_sslmode == "disable"
            assert ci_detected is True
            assert databases["default"]["OPTIONS"]["sslmode"] == "disable"
    
    def test_sqlite_db_config_not_affected(self):
        """SQLite db config → logic doesn't crash / doesn't add OPTIONS unnecessarily"""
        with patch.dict(os.environ, {}, clear=True):
            databases = {
                "default": {
                    "ENGINE": "django.db.backends.sqlite3",
                    "NAME": "db.sqlite3",
                }
            }
            final_sslmode, ci_detected, local_db_detected = _apply_final_ssl_override(databases)
            
            assert final_sslmode is None  # SQLite doesn't get SSL mode set
            assert "OPTIONS" not in databases["default"]  # No OPTIONS added
    
    def test_github_actions_environment_detected_as_ci(self):
        """GITHUB_ACTIONS=true should be treated as CI"""
        with patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}, clear=False):
            databases = {
                "default": {
                    "ENGINE": "django.db.backends.postgresql",
                    "HOST": "localhost",
                    "NAME": "test_db",
                }
            }
            final_sslmode, ci_detected, local_db_detected = _apply_final_ssl_override(
                databases, "postgres://user:pass@localhost:5432/test_db"
            )
            
            assert ci_detected is True
            assert final_sslmode == "disable"
            assert databases["default"]["OPTIONS"]["sslmode"] == "disable"
    
    def test_local_db_detected_from_host(self):
        """Local DB detected from HOST field even without DATABASE_URL"""
        with patch.dict(os.environ, {}, clear=True):
            databases = {
                "default": {
                    "ENGINE": "django.db.backends.postgresql",
                    "HOST": "127.0.0.1",
                    "NAME": "test_db",
                }
            }
            final_sslmode, ci_detected, local_db_detected = _apply_final_ssl_override(
                databases, ""  # No DATABASE_URL
            )
            
            assert local_db_detected is True
            assert final_sslmode == "disable"
            assert databases["default"]["OPTIONS"]["sslmode"] == "disable"
    
    def test_force_sslmode_removes_cert_keys(self):
        """_force_db_sslmode should remove SSL cert keys that force SSL behavior"""
        db_dict = {
            "ENGINE": "django.db.backends.postgresql",
            "OPTIONS": {
                "sslmode": "prefer",
                "sslrootcert": "/path/to/cert",
                "sslcert": "/path/to/client-cert",
                "sslkey": "/path/to/key",
            },
        }
        
        _force_db_sslmode(db_dict, "disable")
        
        assert db_dict["OPTIONS"]["sslmode"] == "disable"
        assert "sslrootcert" not in db_dict["OPTIONS"]
        assert "sslcert" not in db_dict["OPTIONS"]
        assert "sslkey" not in db_dict["OPTIONS"]
    
    def test_local_db_detected_from_ipv6_localhost(self):
        """Local DB detected from ::1 (IPv6 localhost)"""
        with patch.dict(os.environ, {}, clear=True):
            databases = {
                "default": {
                    "ENGINE": "django.db.backends.postgresql",
                    "HOST": "::1",
                    "NAME": "test_db",
                }
            }
            final_sslmode, ci_detected, local_db_detected = _apply_final_ssl_override(
                databases, "postgres://user:pass@::1:5432/test_db"
            )
            
            assert local_db_detected is True
            assert final_sslmode == "disable"
            assert databases["default"]["OPTIONS"]["sslmode"] == "disable"

