"""
Django settings for cc project.
"""
import importlib
import mimetypes
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

from django.core.exceptions import ImproperlyConfigured

# Register .webmanifest MIME type for PWA installability
mimetypes.add_type("application/manifest+json", ".webmanifest")


# --------------------------- helpers ---------------------------
def env_bool(key: str, default: bool = False) -> bool:
    v = os.environ.get(key)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


def env_csv(key: str, default: str = "") -> list[str]:
    raw = os.environ.get(key, default)
    return [x.strip() for x in raw.split(",") if x.strip()]


def env_int(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, "").strip())
    except Exception:
        return default


def _optional_app(app_label: str):
    """
    Return the app label if importable, else None.
    Keeps dev helpers (sslserver, django_extensions) from breaking startup.
    """
    try:
        importlib.import_module(app_label.replace("-", "_"))
        return app_label
    except Exception:
        return None


def _csrf_from_hosts(hosts: list[str]) -> list[str]:
    """
    Turn hostnames into CSRF trusted origins (https://host).
    Skips bare IPs already covered below.
    """
    out = []
    for h in hosts:
        h = h.strip()
        if not h or h in {"localhost", "127.0.0.1", "0.0.0.0"}:
            continue
        if h.startswith("."):
            # wildcard subdomains like .onrender.com
            out.append(f"https://*{h}")
        else:
            out.append(f"https://{h}")
    return out


# --------------------------- base & .env ---------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
try:
    from dotenv import load_dotenv  # type: ignore

    load_dotenv(BASE_DIR / ".env")
except Exception:
    pass

# --------------------------- security/debug ---------------------------
SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "django-insecure-w#o#i4apw-$iz-3sivw57n=2j6fgku@1pfqfs76@3@7)a0h$ys",
)

IS_RUNSERVER = any(arg in sys.argv for arg in ("runserver", "runserver_plus"))
_argv = " ".join(sys.argv).lower()
TESTING = (
    any(token in _argv for token in (" test", "pytest", "py.test")) or os.environ.get("PYTEST_CURRENT_TEST") is not None
)

# CI detection (GitHub Actions, CI=true, etc.)
CI = os.getenv("CI") == "true" or os.getenv("GITHUB_ACTIONS") == "true"

# Reliable Render detection (check multiple indicators)
IS_RENDER = bool(os.getenv("RENDER")) or bool(os.getenv("RENDER_SERVICE_ID")) or bool(os.getenv("RENDER_EXTERNAL_URL"))
ON_RENDER = IS_RENDER  # Keep alias for backwards compatibility

# DEBUG default: True for local dev, False for Render production
# Allow explicit override via DEBUG env var
DEBUG = env_bool("DEBUG", default=not IS_RENDER)

# Allow from env first, else sane defaults (Render host, localhost, etc.)
# NOTE: include staging host by default.
ALLOWED_HOSTS = env_csv(
    "ALLOWED_HOSTS",
    "emajinet.africa,"
    "www.emajinet.africa,"
    "emajinet-staging.onrender.com,"
    "localhost,127.0.0.1,0.0.0.0,.onrender.com",
)

# Render deployment support: add RENDER_EXTERNAL_HOSTNAME if present
RENDER_EXTERNAL_HOSTNAME = os.environ.get("RENDER_EXTERNAL_HOSTNAME", "").strip()
if RENDER_EXTERNAL_HOSTNAME and RENDER_EXTERNAL_HOSTNAME not in ALLOWED_HOSTS:
    ALLOWED_HOSTS = list({*ALLOWED_HOSTS, RENDER_EXTERNAL_HOSTNAME})

if ON_RENDER and ".onrender.com" not in ALLOWED_HOSTS and "*.onrender.com" not in ALLOWED_HOSTS:
    ALLOWED_HOSTS = list({*ALLOWED_HOSTS, ".onrender.com"})
if IS_RUNSERVER and "*" not in ALLOWED_HOSTS:
    ALLOWED_HOSTS = list({*ALLOWED_HOSTS, "localhost", "127.0.0.1", "0.0.0.0"})
if TESTING and "testserver" not in ALLOWED_HOSTS:
    ALLOWED_HOSTS = list({*ALLOWED_HOSTS, "testserver"})

# CSRF trusted origins
_default_csrf_fixed = [
    "http://localhost",
    "http://127.0.0.1",
    "http://0.0.0.0",
    "https://*.onrender.com",
    "https://*.ngrok-free.app",
    "https://*.trycloudflare.com",
    "https://emajinet.africa",
    "https://www.emajinet.africa",
    "https://emajinet-staging.onrender.com",
]

# Add RENDER_EXTERNAL_HOSTNAME to CSRF trusted origins
if RENDER_EXTERNAL_HOSTNAME:
    _default_csrf_fixed.append(f"https://{RENDER_EXTERNAL_HOSTNAME}")

_default_csrf = list({*_default_csrf_fixed, *_csrf_from_hosts(ALLOWED_HOSTS)})
CSRF_TRUSTED_ORIGINS = env_csv("CSRF_TRUSTED_ORIGINS", ",".join(_default_csrf))

# ---- SSL / cookie security (tighten automatically when not DEBUG) ----
USE_SSL = env_bool("USE_SSL", not DEBUG)
FORCE_SSL = env_bool("FORCE_SSL", not DEBUG)
SECURE_SSL_REDIRECT = FORCE_SSL
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG

# HSTS
SECURE_HSTS_SECONDS = 0 if DEBUG else env_int("SECURE_HSTS_SECONDS", 31536000)
SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG and env_bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", True)
SECURE_HSTS_PRELOAD = not DEBUG and env_bool("SECURE_HSTS_PRELOAD", True)

# Behind a proxy (Render/NGINX) - only in production
# These settings tell Django to trust the X-Forwarded-Proto header from the proxy
# Without this, Django doesn't detect HTTPS behind the proxy, causing redirect loops
# In production (DEBUG=False), we're behind Render's proxy, so we need these settings
# In development (DEBUG=True), we're not behind a proxy, so we don't use these settings
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    USE_X_FORWARDED_HOST = True
else:
    # In development, don't use proxy headers (we're not behind a proxy)
    SECURE_PROXY_SSL_HEADER = None
    USE_X_FORWARDED_HOST = False

# Extra hardening
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

# 🚧 Local dev: never force HTTPS on dev server
if IS_RUNSERVER:
    USE_SSL = False
    FORCE_SSL = False
    SECURE_SSL_REDIRECT = False
    SESSION_COOKIE_SECURE = False
    CSRF_COOKIE_SECURE = False
    SECURE_HSTS_SECONDS = 0
    SECURE_HSTS_INCLUDE_SUBDOMAINS = False
    SECURE_HSTS_PRELOAD = False
    # Also disable proxy headers in runserver
    SECURE_PROXY_SSL_HEADER = None
    USE_X_FORWARDED_HOST = False

# --------------------------- canonical host (SEO) ---------------------------
# Canonical host for production: www.emajinet.africa
# This is used by CanonicalURLMiddleware to enforce one canonical domain.
# Only set in production to avoid redirects in development/staging.
CANONICAL_HOST = "www.emajinet.africa" if not DEBUG else ""

# --------------------------- app version ---------------------------
APP_VERSION = os.environ.get("APP_VERSION", "1.1.0")

# --------------------------- session & csrf ---------------------------
SESSION_COOKIE_NAME = os.environ.get("SESSION_COOKIE_NAME", "cc_sessionid")
CSRF_COOKIE_NAME = os.environ.get("CSRF_COOKIE_NAME", "cc_csrftoken")
CSRF_COOKIE_HTTPONLY = True
SESSION_COOKIE_HTTPONLY = True
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_COOKIE_SAMESITE = os.environ.get("SESSION_COOKIE_SAMESITE", "Lax")
CSRF_COOKIE_SAMESITE = os.environ.get("CSRF_COOKIE_SAMESITE", "Lax")
SESSION_COOKIE_AGE = 60 * 60 * 4
SESSION_ENGINE = "django.contrib.sessions.backends.db"

# Canonical session key for active tenant (used by middleware/utils)
TENANT_SESSION_KEY = os.environ.get("TENANT_SESSION_KEY", "active_business_id")

# Branded CSRF failure view (replaces Django's default 403 CSRF page)
CSRF_FAILURE_VIEW = "core.views_csrf.csrf_failure"

# --------------------------- apps ---------------------------
INSTALLED_APPS = [
    # Django
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    # Local apps
    "circuitcity.accounts.apps.AccountsConfig",
    "tenants.apps.TenantsConfig",
    "core.apps.CoreConfig",
    "inventory",
    "sales",
    "dashboard",
    "simulator",
    # Billing
    "billing",
    "wallet.apps.WalletConfig",
    # Layby (TOP-LEVEL import, not circuitcity.layby)
    "layby.apps.LaybyConfig",
    "timelogs",
    "notifications",
    "hq",
    "reports",
    # NEW APPS
    "support",  # ticket system
    "audit",  # audit logs UI
    "staticpages",  # Public home page with hero section
    "backups",  # data backup & export system
    # Email backend
    "anymail",  # SendGrid email backend via django-anymail
]

# Optional dev/helper apps
INSTALLED_APPS += [
    a
    for a in (
        _optional_app("sslserver"),
        _optional_app("django_extensions"),
    )
    if a
]

print("[cc.settings] Final INSTALLED_APPS:", INSTALLED_APPS)

# --------------------------- middleware ---------------------------
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",  # must be right after SecurityMiddleware
    # ✅ SECURITY: Remove framework fingerprints (Server, X-Powered-By headers)
    "cc.middleware_security.RemoveServerHeaderMiddleware",
    # ✅ SECURITY: Add strict security headers (CSP, Permissions-Policy, etc.)
    "cc.middleware_security.SecurityHeadersMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "cc.middleware.RequestIDMiddleware",
    "cc.middleware.AccessLogMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    # HQ admins stay in HQ
    "cc.middleware.PreventHQFromClientUI",
    # Tenant resolution + compat alias
    "tenants.middleware.TenantResolutionMiddleware",
    "tenants.middleware.ActiveBusinessMiddleware",
    # ✅ CRITICAL: Role resolution (AFTER tenant, BEFORE views)
    # This ensures managers NEVER downgrade to agent scope on dashboard
    "tenants.middleware_roles.RoleResolutionMiddleware",
    # ✅ Subscription lockout enforcement (AFTER role resolution)
    # Blocks ALL users (agents + managers) when subscription is expired/canceled
    # Shows role-specific messaging
    "billing.middleware_subscription_gate.SubscriptionGateMiddleware",
    # ✅ SEO: noindex headers for private pages (Search Console indexing fix)
    "cc.middleware_seo.SEONoIndexMiddleware",
    # ✅ SEO: canonical domain enforcement (www → non-www redirect)
    "cc.middleware_seo.CanonicalURLMiddleware",
    # ✅ SEO: UTM tracking parameter cleanup (2025-12-25)
    "cc.middleware_seo.PublicQueryCleanupMiddleware",
    # ✅ Two-Factor Authentication enforcement (after auth)
    "cc.middleware_twofa.TwoFactorAuthMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # ✅ SECURITY: Safe error responses (no stack traces, generic messages)
    # Must be LAST to catch all exceptions
    "cc.middleware_security.SafeErrorResponseMiddleware",
]

print("[cc.settings] Final MIDDLEWARE:", MIDDLEWARE)
print(
    f"[cc.settings] SSL flags -> DEBUG={DEBUG} RUNSERVER={IS_RUNSERVER} "
    f"SECURE_SSL_REDIRECT={SECURE_SSL_REDIRECT} "
    f"SESSION_COOKIE_SECURE={SESSION_COOKIE_SECURE} CSRF_COOKIE_SECURE={CSRF_COOKIE_SECURE}"
)
print("[cc.settings] SECURE_PROXY_SSL_HEADER ->", SECURE_PROXY_SSL_HEADER)
print("[cc.settings] USE_X_FORWARDED_HOST ->", USE_X_FORWARDED_HOST)
print("[cc.settings] ALLOWED_HOSTS ->", ALLOWED_HOSTS)
print("[cc.settings] CSRF_TRUSTED_ORIGINS ->", CSRF_TRUSTED_ORIGINS)

ROOT_URLCONF = "cc.urls"

# --------------------------- templates ---------------------------
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [
            *(
                p
                for p in [
                    BASE_DIR / "templates",
                    BASE_DIR / "circuitcity" / "templates",
                ]
                if p.exists()
            )
        ],
        "APP_DIRS": True,
        "OPTIONS": {
            "debug": DEBUG,
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "cc.context_processors.build_meta",
                "cc.context_processors.app_version",
                "cc.context_processors.role_flags",
                "cc.context_processors.brand",
                "cc.context_processors.currency_config",
                "tenants.context_processors.tenant_context",
                "tenants.context_processors.notifications_context",
                "billing.context_processors.trial_banner",
                "billing.context_processors.pricing_context",
            ],
            "builtins": [
                "inventory.templatetags.money",
                "core.templatetags.cc_extras",
            ],
        },
    },
]
SILENCED_SYSTEM_CHECKS = ["templates.E003"]

WSGI_APPLICATION = "cc.wsgi.application"


# --------------------------- database ---------------------------
def _is_ci_environment() -> bool:
    """
    Robust CI detection: CI=true OR GITHUB_ACTIONS=true should be treated as CI.
    """
    return os.getenv("CI") == "true" or os.getenv("GITHUB_ACTIONS") == "true"


def _is_local_db_host(host: str) -> bool:
    """Check if a host is a local database host."""
    return host and host.lower() in ("localhost", "127.0.0.1", "::1", "0.0.0.0")


def _detect_local_db_from_config(db_dict: dict, database_url: str = None) -> bool:
    """
    Robust local-db detection:
    - Check if DATABASE_URL contains localhost, 127.0.0.1, or ::1
    - OR if DATABASES["default"]["HOST"] equals one of those (covers non-URL config)

    Args:
        db_dict: The database configuration dictionary
        database_url: Optional DATABASE_URL string (defaults to os.environ)
    """
    if database_url is None:
        database_url = os.environ.get("DATABASE_URL", "").strip()

    if database_url and any(h in database_url for h in ["localhost", "127.0.0.1", "::1"]):
        return True

    host = db_dict.get("HOST", "")
    return _is_local_db_host(host)


def _force_db_sslmode(db_dict: dict, mode: str) -> None:
    """
    Force SSL mode in database OPTIONS. This is a final override that cannot be bypassed.

    Args:
        db_dict: The database configuration dictionary (DATABASES["default"])
        mode: Either "disable" or "require"

    This function:
    - Ensures db_dict["OPTIONS"] exists
    - Sets OPTIONS["sslmode"] = mode
    - Removes any cert keys that can force SSL behavior (sslrootcert, sslcert, sslkey)
    """
    if "OPTIONS" not in db_dict:
        db_dict["OPTIONS"] = {}

    opts = db_dict["OPTIONS"]
    opts["sslmode"] = mode

    # Remove any cert keys that can force SSL behavior
    for key in ("sslrootcert", "sslcert", "sslkey", "sslmode"):
        # Keep sslmode, remove others
        if key != "sslmode" and key in opts:
            del opts[key]


def _apply_final_ssl_override(databases: dict, database_url: str = None) -> tuple[str | None, bool, bool]:
    """
    Apply final SSL mode override to database configuration.

    This function enforces SSL mode rules regardless of what was set earlier:
    - CI + local DB → sslmode=disable
    - Production → sslmode=require

    Args:
        databases: The DATABASES dictionary (will be modified in place)
        database_url: Optional DATABASE_URL string for detection (defaults to os.environ)

    Returns:
        Tuple of (final_sslmode, ci_detected, local_db_detected)
    """
    if database_url is None:
        database_url = os.environ.get("DATABASE_URL", "").strip()

    ci_detected = _is_ci_environment()
    default_db = databases.get("default", {})
    local_db_detected = _detect_local_db_from_config(default_db, database_url)

    # Only apply SSL rules to PostgreSQL (skip SQLite)
    if default_db.get("ENGINE", "").endswith("postgresql"):
        if ci_detected or local_db_detected:
            _force_db_sslmode(default_db, "disable")
            final_sslmode = "disable"
        else:
            _force_db_sslmode(default_db, "require")
            final_sslmode = "require"

        databases["default"] = default_db
        return (final_sslmode, ci_detected, local_db_detected)

    # Not PostgreSQL, return None to indicate no SSL mode was set
    return (None, ci_detected, local_db_detected)


DATABASES: dict = {}
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()

USE_LOCAL_SQLITE = env_bool("USE_LOCAL_SQLITE", default=not bool(DATABASE_URL))
REQUIRE_DATABASE_URL = env_bool("REQUIRE_DATABASE_URL", False)
PGCONNECT_TIMEOUT = env_int("PGCONNECT_TIMEOUT", 5)

# DB connection resiliency
DB_CONN_MAX_AGE = env_int("DB_CONN_MAX_AGE", 120)  # seconds
DB_CONN_HEALTH_CHECKS = env_bool("DB_CONN_HEALTH_CHECKS", True)

# SQLite timeout (seconds) to reduce "database is locked" during dev/Cypress
SQLITE_TIMEOUT = env_int("SQLITE_TIMEOUT", 20)

# Detect CI and local DB to disable SSL (Postgres service containers don't support SSL)
# CI variable is already defined above (line 85)
IS_LOCAL_DB = any(h in (DATABASE_URL or "") for h in ["localhost", "127.0.0.1", "::1"])

if TESTING:
    DATABASES["default"] = {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
        "OPTIONS": {
            "timeout": SQLITE_TIMEOUT,
        },
    }
elif DATABASE_URL:
    try:
        import dj_database_url  # type: ignore
    except Exception as e:
        raise ImproperlyConfigured("dj-database-url must be installed") from e

    # Only require SSL when NOT CI and NOT local (production on Render)
    cfg = dj_database_url.parse(
        DATABASE_URL,
        conn_max_age=DB_CONN_MAX_AGE,
        ssl_require=not (CI or IS_LOCAL_DB),
    )
    # OPTIONS & health checks
    opts = dict(cfg.get("OPTIONS") or {})
    opts.setdefault("connect_timeout", PGCONNECT_TIMEOUT)
    # Force-disable SSL for CI/local to prevent psycopg2 "SSL required" failures
    if CI or IS_LOCAL_DB:
        opts["sslmode"] = "disable"
    cfg["OPTIONS"] = opts
    cfg["CONN_HEALTH_CHECKS"] = DB_CONN_HEALTH_CHECKS
    DATABASES["default"] = cfg
elif USE_LOCAL_SQLITE:
    sqlite_path = str(BASE_DIR / "db.sqlite3")
    DATABASES["default"] = {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": sqlite_path,
        "OPTIONS": {
            "timeout": SQLITE_TIMEOUT,
        },
    }
else:
    NAME = os.environ.get("POSTGRES_DB") or os.environ.get("DB_NAME", "circuitcity")
    USER = os.environ.get("POSTGRES_USER") or os.environ.get("DB_USER", "ccuser")
    PASSWORD = os.environ.get("POSTGRES_PASSWORD") or os.environ.get("DB_PASSWORD", "")
    HOST = os.environ.get("POSTGRES_HOST") or os.environ.get("DB_HOST", "127.0.0.1")
    PORT = os.environ.get("POSTGRES_PORT") or os.environ.get("DB_PORT", "5432")
    # Detect local DB for fallback config
    IS_LOCAL_HOST = HOST in ("localhost", "127.0.0.1", "::1", "0.0.0.0")
    DATABASES["default"] = {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": NAME,
        "USER": USER,
        "PASSWORD": PASSWORD,
        "HOST": HOST,
        "PORT": PORT,
        "CONN_MAX_AGE": DB_CONN_MAX_AGE,
        "CONN_HEALTH_CHECKS": DB_CONN_HEALTH_CHECKS,
        "OPTIONS": {
            "connect_timeout": PGCONNECT_TIMEOUT,
            **({"sslmode": "disable"} if (CI or IS_LOCAL_HOST) else {"sslmode": "require"}),
        },
    }

# Ensure SQLite always has a sensible timeout, even if config changes later
default_db = DATABASES.get("default", {})
if default_db.get("ENGINE") == "django.db.backends.sqlite3":
    opts = dict(default_db.get("OPTIONS") or {})
    opts.setdefault("timeout", SQLITE_TIMEOUT)
    default_db["OPTIONS"] = opts
    DATABASES["default"] = default_db

# ===== FINAL SSL MODE OVERRIDE (cannot be bypassed) =====
# This runs AFTER all database configuration (including dj_database_url.parse)
# and enforces SSL mode rules regardless of what was set earlier.
# This ensures CI/local DBs always use sslmode=disable, and production uses sslmode=require.
_final_sslmode, _ci_detected, _local_db_detected = _apply_final_ssl_override(DATABASES, DATABASE_URL)
if _final_sslmode:
    # Log the final decision (redact DATABASE_URL to avoid printing secrets)
    print(f"[cc.settings] DB sslmode -> {_final_sslmode} " f"(CI={_ci_detected} IS_LOCAL_DB={_local_db_detected})")

# ===== RENDER GUARD: Prevent SQLite in production =====
# On Render, we must use PostgreSQL. Fail fast if misconfigured.
if os.getenv("RENDER") and DATABASES.get("default", {}).get("ENGINE", "").endswith("sqlite3"):
    raise ImproperlyConfigured(
        "SQLite is not allowed on Render. Please set DATABASE_URL to a valid PostgreSQL connection string."
    )

# --------------------------- cache ---------------------------
CACHE_TTL_DEFAULT = env_int("CACHE_TTL_DEFAULT", 60)
REDIS_URL = os.environ.get("REDIS_URL", "")
if REDIS_URL:
    CACHES = {
        "default": {
            "BACKEND": "django_redis.cache.RedisCache",
            "LOCATION": REDIS_URL,
            "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
            "TIMEOUT": CACHE_TTL_DEFAULT,
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "cc-local-cache",
            "TIMEOUT": CACHE_TTL_DEFAULT,
        }
    }

# --------------------------- auth / i18n ---------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    # Strong password policy: 12+ chars, upper, lower, digit, symbol
    # This applies to all password creation/change flows (agent invites, user registration, password reset)
    {"NAME": "tenants.validators.StrongPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
# Use faster password hashing in CI for speed
if CI:
    PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
else:
    PASSWORD_HASHERS = ["django.contrib.auth.hashers.PBKDF2PasswordHasher"]
AUTHENTICATION_BACKENDS = ["django.contrib.auth.backends.ModelBackend"]
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Africa/Blantyre"
USE_I18N = True
USE_TZ = True
# Celery timezone
CELERY_TIMEZONE = "Africa/Blantyre"

# Celery Beat Schedule - Gym Email Automation
try:
    from celery.schedules import crontab

    CELERY_BEAT_SCHEDULE = {
        # Daily inactivity reminders at 3:00 PM Malawi time
        "gym-daily-inactivity-reminders": {
            "task": "inventory.tasks_gym_emails.send_gym_inactivity_reminders",
            "schedule": crontab(hour=15, minute=0, day_of_week="*"),
            "options": {"timezone": "Africa/Blantyre"},
        },
        # Weekly manager summary every Monday at 3:00 PM Malawi time
        "gym-weekly-manager-summary": {
            "task": "inventory.tasks_gym_emails.send_gym_weekly_manager_summary",
            "schedule": crontab(hour=15, minute=0, day_of_week="monday"),
            "options": {"timezone": "Africa/Blantyre"},
        },
    }
except ImportError:
    # Celery not installed (e.g., in CI or minimal environments)
    CELERY_BEAT_SCHEDULE = {}

# Celery eager mode in CI (no external broker needed)
if CI:
    CELERY_TASK_ALWAYS_EAGER = True
    CELERY_TASK_EAGER_PROPAGATES = True

# --------------------------- static / media ---------------------------
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [
    *(
        p
        for p in [
            BASE_DIR / "static",
            BASE_DIR / "circuitcity" / "static",
        ]
        if p.exists()
    )
]
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# Django 4.2+ STORAGES API
_force_plain_static = os.environ.get("DJANGO_TEST_FORCE_PLAIN_STATIC") == "1"
if DEBUG or TESTING or _force_plain_static:
    _static_backend = "django.contrib.staticfiles.storage.StaticFilesStorage"
else:
    _static_backend = "whitenoise.storage.CompressedManifestStaticFilesStorage"

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": _static_backend},
}

# WhiteNoise tuning
WHITENOISE_AUTOREFRESH = DEBUG
WHITENOISE_MAX_AGE = 60 * 60 * 24 * 365
WHITENOISE_INDEX_FILE = False
# DO NOT hard-fail on manifest mismatches during rolling deploys.
WHITENOISE_MANIFEST_STRICT = False

# --------------------------- auth redirects ---------------------------
LOGIN_URL = "/accounts/login/"
# Send users directly to inventory dashboard after login
LOGIN_REDIRECT_URL = "/inventory/dashboard/"
LOGOUT_REDIRECT_URL = "/accounts/login/"

# --------------------------- email ---------------------------
ADMINS = [("Ops", os.environ.get("ADMIN_EMAIL", "ops@example.com"))]
EMAIL_SUBJECT_PREFIX = "[CC] "

# ==============================================================================
# Email backend selection (deterministic)
# ==============================================================================
# Rule:
# 1. If USE_CONSOLE_EMAIL is explicitly true (1/true/yes) => use console backend
# 2. Else if SENDGRID_API_KEY exists => use anymail SendGrid backend
# 3. Else => use console backend (safe fallback)
# ==============================================================================

# Safe env parsing for USE_CONSOLE_EMAIL
USE_CONSOLE_EMAIL_RAW = os.getenv("USE_CONSOLE_EMAIL", "").strip()
USE_CONSOLE_EMAIL = USE_CONSOLE_EMAIL_RAW in ("1", "true", "True", "yes", "YES", "on", "ON")

# SendGrid configuration
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY", "").strip()
HAS_SENDGRID_KEY = bool(SENDGRID_API_KEY)

DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "Emajinet <no-reply@emajinet.africa>")
SERVER_EMAIL = DEFAULT_FROM_EMAIL

# Configure email backend based on deterministic rule
# In CI, always use in-memory backend (no external calls)
if CI:
    EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    ANYMAIL = {}
elif USE_CONSOLE_EMAIL:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
    ANYMAIL = {}
elif HAS_SENDGRID_KEY:
    EMAIL_BACKEND = "anymail.backends.sendgrid.EmailBackend"
    ANYMAIL = {
        "SENDGRID_API_KEY": SENDGRID_API_KEY,
    }
else:
    # Fallback: console backend (safe default)
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
    ANYMAIL = {}

# Print startup configuration
print(
    f"[cc.settings] EMAIL_BACKEND={EMAIL_BACKEND} "
    f"USE_CONSOLE_EMAIL={USE_CONSOLE_EMAIL} "
    f"HAS_SENDGRID_KEY={HAS_SENDGRID_KEY}"
)

# ==============================================================================
# PRODUCTION SAFETY: Prevent console backend in production
# ==============================================================================
# Only enforce production email guard on REAL production (Render + DEBUG=False)
# Local dev and CI should never block startup even if DEBUG accidentally false
if IS_RENDER and not DEBUG and not CI:
    if USE_CONSOLE_EMAIL:
        raise ImproperlyConfigured(
            "CRITICAL: USE_CONSOLE_EMAIL=True is not allowed in production (Render + DEBUG=False). "
            "Set USE_CONSOLE_EMAIL=0 and SENDGRID_API_KEY in production environment."
        )
    if not SENDGRID_API_KEY:
        raise ImproperlyConfigured(
            "CRITICAL: SENDGRID_API_KEY is required in production (Render + DEBUG=False). "
            "Set SENDGRID_API_KEY in your Render environment variables."
        )

# ==============================================================================
# SendGrid configuration validation (for non-console backend)
# ==============================================================================
# Only validate if explicitly using SendGrid (not console backend)
if not USE_CONSOLE_EMAIL and HAS_SENDGRID_KEY:
    # SendGrid backend is configured, no validation needed
    pass
elif not USE_CONSOLE_EMAIL and not HAS_SENDGRID_KEY:
    # Trying to use SendGrid but no key - warn or fail
    # Skip validation in CI (uses locmem backend)
    if CI:
        pass  # CI uses locmem backend, no validation needed
    elif not IS_RENDER:
        import logging

        logger = logging.getLogger(__name__)
        logger.warning(
            "USE_CONSOLE_EMAIL is not set but SENDGRID_API_KEY not found. "
            "Falling back to console backend. Set SENDGRID_API_KEY for real email sending."
        )
    else:
        # On Render, require SendGrid key if not using console
        raise ImproperlyConfigured(
            "SENDGRID_API_KEY is required in production (Render + DEBUG=False). "
            "Either set USE_CONSOLE_EMAIL=1 to use console backend, "
            "or set SENDGRID_API_KEY in your environment variables."
        )

# ==============================================================================
# DEFAULT_FROM_EMAIL validation and warning
# ==============================================================================
if not DEFAULT_FROM_EMAIL or "@" not in DEFAULT_FROM_EMAIL:
    import logging

    logger = logging.getLogger(__name__)
    logger.warning("DEFAULT_FROM_EMAIL is not properly configured. " "Falling back to safe default.")
    DEFAULT_FROM_EMAIL = "Emajinet <no-reply@emajinet.africa>"
    SERVER_EMAIL = DEFAULT_FROM_EMAIL

# Extract email domain for validation
_from_email_domain = ""
try:
    # Extract domain from "Name <email@domain.com>" or "email@domain.com"
    email_part = DEFAULT_FROM_EMAIL.split("<")[-1].split(">")[0].strip()
    if "@" in email_part:
        _from_email_domain = email_part.split("@")[1].lower()
except Exception:
    pass

# Warn if from-email domain is not emajinet.africa (deliverability concern)
if _from_email_domain and _from_email_domain != "emajinet.africa":
    import logging

    logger = logging.getLogger(__name__)
    logger.warning(
        f"DEFAULT_FROM_EMAIL domain ({_from_email_domain}) is not emajinet.africa. "
        f"This may affect email deliverability. Ensure the domain is verified in SendGrid."
    )

# --------------------------- twilio (2FA SMS OTP) ---------------------------
# Twilio Verify API for SMS-based Two-Factor Authentication
# All credentials must be in environment variables (never in git)
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_VERIFY_SERVICE_SID = os.environ.get("TWILIO_VERIFY_SERVICE_SID", "")

# Enable Twilio Verify only if all required credentials are present
TWILIO_VERIFY_ENABLED = bool(TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_VERIFY_SERVICE_SID)

if TWILIO_VERIFY_ENABLED:
    print("[cc.settings] Twilio Verify enabled for SMS 2FA")
else:
    print("[cc.settings] Twilio Verify disabled (missing credentials)")

# --------------------------- billing ---------------------------
BILLING = {
    "PROVIDER": os.environ.get("BILLING_PROVIDER", "stripe"),
    "DEFAULT_CURRENCY": os.environ.get("BILLING_CURRENCY", "MWK"),
    "TRIAL_DAYS": env_int("BILLING_TRIAL_DAYS", 30),
    "GRACE_DAYS": env_int("BILLING_GRACE_DAYS", 30),
    "INVOICE_FROM": os.environ.get(
        "BILLING_INVOICE_FROM",
        os.environ.get("DEFAULT_FROM_EMAIL", "noreply@example.com"),
    ),
}
# Import centralized pricing configuration
try:
    from billing.pricing import PLANS as BILLING_PLANS_CONFIG

    BILLING_PLANS = {
        code: {
            "code": plan.code,
            "name": plan.name,
            "amount": float(plan.amount),
            "currency": plan.currency,
            "max_agents": plan.max_agents if plan.max_agents != -1 else None,
            "max_stores": plan.max_stores if plan.max_stores != -1 else None,
        }
        for code, plan in BILLING_PLANS_CONFIG.items()
    }
except ImportError:
    # Fallback during initial setup before billing app is ready
    BILLING_PLANS = {
        "starter": {
            "code": "starter",
            "name": "Starter",
            "amount": 20000,
            "currency": "MWK",
            "max_agents": 3,
            "max_stores": 1,
        },
        "growth": {
            "code": "growth",
            "name": "Growth",
            "amount": 60000,
            "currency": "MWK",
            "max_agents": 15,
            "max_stores": 5,
        },
        "pro": {
            "code": "pro",
            "name": "Pro",
            "amount": 120000,
            "currency": "MWK",
            "max_agents": None,
            "max_stores": None,
        },
    }

REPORTS_DEFAULT_CURRENCY = BILLING["DEFAULT_CURRENCY"]
BILLING_TRIAL_DAYS = BILLING["TRIAL_DAYS"]
BILLING_GRACE_DAYS = BILLING["GRACE_DAYS"]

# --------------------------- payment providers ---------------------------
# Stripe (card payments)
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_PUBLISHABLE_KEY = os.environ.get("STRIPE_PUBLISHABLE_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")

if STRIPE_SECRET_KEY:
    try:
        import stripe  # type: ignore

        stripe.api_key = STRIPE_SECRET_KEY
    except ImportError:
        pass

# Pesapal (mobile money + cards for Africa)
PESAPAL_CONSUMER_KEY = os.environ.get("PESAPAL_CONSUMER_KEY", "")
PESAPAL_CONSUMER_SECRET = os.environ.get("PESAPAL_CONSUMER_SECRET", "")
PESAPAL_BASE_URL = os.environ.get("PESAPAL_BASE_URL", "https://cybqa.pesapal.com/pesapalv3/api/")  # sandbox default
PESAPAL_IPN_ID = os.environ.get("PESAPAL_IPN_ID", "")

# --------------------------- PayChangu (Mobile Money for Malawi) ---------------------------
PAYCHANGU_MODE = os.environ.get("PAYCHANGU_MODE", "test").strip().lower()
PAYCHANGU_PUBLIC_KEY = os.environ.get("PAYCHANGU_PUBLIC_KEY", "")
PAYCHANGU_SECRET_KEY = os.environ.get("PAYCHANGU_SECRET_KEY", "")
PAYCHANGU_WEBHOOK_SECRET = os.environ.get("PAYCHANGU_WEBHOOK_SECRET", "")
PAYCHANGU_WEBHOOK_DEBUG = env_bool("PAYCHANGU_WEBHOOK_DEBUG", False)
PAYCHANGU_API_BASE = os.environ.get("PAYCHANGU_API_BASE", "https://api.paychangu.com")

# Production guard: prevent test mode in production
if not DEBUG and PAYCHANGU_MODE == "test":
    raise ImproperlyConfigured(
        "PAYCHANGU_MODE cannot be 'test' when DEBUG=False. "
        "Set PAYCHANGU_MODE=live in production or enable DEBUG for local testing."
    )

# --------------------------- whatsapp notifications ---------------------------
WHATSAPP_API_BASE_URL = os.environ.get("WHATSAPP_API_BASE_URL", "https://graph.facebook.com/v21.0/")
WHATSAPP_PHONE_NUMBER_ID = os.environ.get("WHATSAPP_PHONE_NUMBER_ID", "")
WHATSAPP_ACCESS_TOKEN = os.environ.get("WHATSAPP_ACCESS_TOKEN", "")
WHATSAPP_DEFAULT_COUNTRY_CODE = os.environ.get("WHATSAPP_DEFAULT_COUNTRY_CODE", "+265")  # Malawi

# --------------------------- global UI ---------------------------
UI = {
    "SIDEBAR_COLLAPSIBLE": False,
    "TOPBAR_SHOW_LOGOUT": True,
}

# --------------------------- misc ---------------------------
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUDIT_LOG_SETTINGS = {
    "ENABLED": True,
    "AUDIT_MODEL": "inventory.AuditLog",
    "TRACK_DELETES": True,
    "TRACK_EDITS": True,
    "INCLUDE_USER": True,
}
WARRANTY_CHECK_ENABLED = env_bool("WARRANTY_CHECK_ENABLED", False)
WARRANTY_ENFORCE_COUNTRY = env_bool("WARRANTY_ENFORCE_COUNTRY", True)
ACTIVATION_ALERT_MINUTES = env_int("ACTIVATION_ALERT_MINUTES", 15)
WARRANTY_REQUEST_TIMEOUT = env_int("WARRANTY_REQUEST_TIMEOUT", 12)

APP_NAME = os.environ.get("APP_NAME", "Emajinet")
APP_ENV = os.environ.get("APP_ENV", "dev" if DEBUG else "beta")
BETA_FEEDBACK_MAILTO = os.environ.get("BETA_FEEDBACK_MAILTO", "beta@emajinet.africa")

# --------------------------- OTP / password reset ---------------------------
EMAIL_OTP_TTL_MINUTES = env_int("EMAIL_OTP_TTL_MINUTES", 10)

# --------------------------- safety toggles ---------------------------
DISABLE_SALES_AUTOCREATE = env_bool("DISABLE_SALES_AUTOCREATE", True)

# Make template exceptions bubble loudly in dev
DEBUG_PROPAGATE_EXCEPTIONS = DEBUG
DEFAULT_EXCEPTION_REPORTER_FILTER = "django.views.debug.SafeExceptionReporterFilter"

# Minimal logging so template errors are obvious in console
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "django.template": {
            "handlers": ["console"],
            "level": "DEBUG" if DEBUG else "INFO",
            "propagate": True,
        },
    },
}

# --------------------------- feature flags for templates (optional) ---------------------------
CC_SHOW_ADMIN_TIP = env_bool("CC_SHOW_ADMIN_TIP", False)
CC_PUBLIC_ERROR_PAGE = env_bool("CC_PUBLIC_ERROR_PAGE", True)

# --------------------------- phone pricing guardrails ---------------------------
MIN_PHONE_SELLING_PRICE_MK = env_int("MIN_PHONE_SELLING_PRICE_MK", 10000)

# ===========================================================================================
# DEV tunnel hosts (MUST stay at very end; prevents DisallowedHost)
# This MUST be the absolute last code in settings.py - nothing after this block
# ===========================================================================================
if DEBUG or IS_RUNSERVER:
    ALLOWED_HOSTS = ["*"]
    print("[cc.settings] FINAL ALLOWED_HOSTS ->", ALLOWED_HOSTS)
