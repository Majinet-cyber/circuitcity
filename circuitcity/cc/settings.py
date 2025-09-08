"""
Django settings for cc project.
"""

from pathlib import Path
from urllib.parse import urlparse
import os
import re
import logging
import sys

# -------------------------------------------------
# Helpers
# -------------------------------------------------
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


# -------------------------------------------------
# Base paths
# -------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent

# -------------------------------------------------
# .env loading (python-dotenv)
# -------------------------------------------------
try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv(BASE_DIR / ".env")
except Exception:
    pass

# -------------------------------------------------
# Security / Debug
# -------------------------------------------------
SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "django-insecure-w#o#i4apw-$iz-3sivw57n=2j6fgku@1pfqfs76@3@7)a0h$ys",  # dev fallback
)

DEBUG = env_bool("DEBUG", env_bool("DJANGO_DEBUG", True))
TESTING = any(arg in sys.argv for arg in ("test", "pytest"))

# Detect Render & its external URL (available on the platform)
RENDER = bool(os.environ.get("RENDER") or os.environ.get("RENDER_EXTERNAL_URL"))
RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL", "")

# Optional: custom domain + explicit live host (to be safe with CSRF)
APP_DOMAIN = os.environ.get("APP_DOMAIN", "").strip()            # e.g. app.circuitcity.mw
LIVE_HOST = os.environ.get("LIVE_HOST", "").strip()              # e.g. circuitcity-main.onrender.com

# Hosts (env override supported)
_default_hosts = "localhost,127.0.0.1,0.0.0.0,192.168.1.104,.ngrok-free.app,.trycloudflare.com,.onrender.com"
ALLOWED_HOSTS = env_csv("ALLOWED_HOSTS", os.environ.get("DJANGO_ALLOWED_HOSTS", _default_hosts))

# If Render gives us the full external URL, add its hostname explicitly
if RENDER_EXTERNAL_URL:
    parsed = urlparse(RENDER_EXTERNAL_URL)
    host = parsed.netloc
    if host and host not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(host)

# Always include the Render wildcard too
if ".onrender.com" not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(".onrender.com")

# Optional explicit hosts (handy if envs are set)
if LIVE_HOST and LIVE_HOST not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(LIVE_HOST)
if APP_DOMAIN and APP_DOMAIN not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(APP_DOMAIN)

# Force-SSL toggle (lets you run DEBUG=False on HTTP during LAN pilots)
FORCE_SSL = env_bool("FORCE_SSL", env_bool("DJANGO_FORCE_SSL", False))
USE_SSL = FORCE_SSL or not DEBUG  # enable SSL protections in prod by default

# Optional: allow /healthz to bypass HTTP->HTTPS for uptime checks (default off)
HEALTHZ_ALLOW_HTTP = env_bool("HEALTHZ_ALLOW_HTTP", False)

# -------------------------------------------------
# Security Headers
# -------------------------------------------------
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"

SECURE_SSL_REDIRECT = USE_SSL and not HEALTHZ_ALLOW_HTTP
SESSION_COOKIE_SECURE = USE_SSL
CSRF_COOKIE_SECURE = USE_SSL

if USE_SSL:
    SECURE_HSTS_SECONDS = env_int("SECURE_HSTS_SECONDS", 31536000)  # 1 year
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

# If you set HEALTHZ_ALLOW_HTTP, exempt the route from redirect
if HEALTHZ_ALLOW_HTTP:
    # Regex matched against request.path_info (no leading slash)
    SECURE_REDIRECT_EXEMPT = [r"^healthz$"]

# -------------------------------------------------
# Session & CSRF Settings
# -------------------------------------------------
SESSION_COOKIE_NAME = os.environ.get("SESSION_COOKIE_NAME", "cc_sessionid")
CSRF_COOKIE_NAME = os.environ.get("CSRF_COOKIE_NAME", "cc_csrftoken")

CSRF_COOKIE_HTTPONLY = True
SESSION_COOKIE_HTTPONLY = True
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_COOKIE_SAMESITE = os.environ.get("SESSION_COOKIE_SAMESITE", "Lax")
CSRF_COOKIE_SAMESITE = os.environ.get("CSRF_COOKIE_SAMESITE", "Lax")
SESSION_COOKIE_AGE = 60 * 60 * 4  # 4 hours

# Explicit default session engine (DB-backed)
SESSION_ENGINE = "django.contrib.sessions.backends.db"

# ---- CSRF Trusted Origins (must include scheme) ----
_default_csrf = ",".join(
    [
        "http://localhost",
        "http://127.0.0.1",
        "http://0.0.0.0",
        "http://192.168.1.104",
        "https://*.ngrok-free.app",
        "https://*.trycloudflare.com",
        "https://*.onrender.com",
    ]
)
_csrf_from_primary = os.environ.get("CSRF_TRUSTED_ORIGINS")
_csrf_from_legacy = os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", _default_csrf)
CSRF_TRUSTED_ORIGINS = env_csv("CSRF_TRUSTED_ORIGINS", _csrf_from_primary or _csrf_from_legacy)

# Helper to append an origin safely
def _add_origin(url: str):
    if url and url not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS.append(url)

# 1) Add the Render external origin (scheme + host) if present
if RENDER_EXTERNAL_URL:
    parsed = urlparse(RENDER_EXTERNAL_URL)
    if parsed.scheme and parsed.netloc:
        _add_origin(f"{parsed.scheme}://{parsed.netloc}")

# 2) Explicitly add your live host (e.g., circuitcity-main.onrender.com) if provided
if LIVE_HOST:
    _add_origin(f"https://{LIVE_HOST}")

# 3) Add custom domain origin if provided
if APP_DOMAIN:
    _add_origin(f"https://{APP_DOMAIN}")

# -------------------------------------------------
# Safer uploads & request size limits
# -------------------------------------------------
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10 MB
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024  # 5 MB
FILE_UPLOAD_HANDLERS = [
    "django.core.files.uploadhandler.MemoryFileUploadHandler",
    "django.core.files.uploadhandler.TemporaryFileUploadHandler",
]
FILE_UPLOAD_PERMISSIONS = 0o640
FILE_UPLOAD_DIRECTORY_PERMISSIONS = 0o750

# -------------------------------------------------
# Applications
# -------------------------------------------------
INSTALLED_APPS = [
    # Django apps
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Helpful (optional)
    "django.contrib.humanize",
    # Your apps
    "accounts.apps.AccountsConfig",  # ✅ enables signals & auth views
    "inventory",
    "sales",
    "dashboard",
    # 'reports' is a plain Python package (helpers only).
]

# -------------------------------------------------
# Middleware
# -------------------------------------------------
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # WhiteNoise: serve versioned static files when DEBUG=False
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    # ---- Observability middlewares (you created cc/middleware.py) ----
    "cc.middleware.RequestIDMiddleware",
    "cc.middleware.AccessLogMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    # ---- Phase 6: enforce Auditor read-only on POST/PUT/PATCH/DELETE ----
    "inventory.middleware.AuditorReadOnlyMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "cc.urls"

# -------------------------------------------------
# Templates
# -------------------------------------------------
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "cc.wsgi.application"

# -------------------------------------------------
# Database — production requires Postgres via DATABASE_URL
# -------------------------------------------------
DATABASES: dict = {}

# NEW: explicit override to force SQLite (even if DATABASE_URL is set)
FORCE_SQLITE = env_bool("FORCE_SQLITE", False)

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
USE_LOCAL_SQLITE = env_bool("USE_LOCAL_SQLITE", default=DEBUG)

# In production (Render or DEBUG=False), require DATABASE_URL so we never fall back to SQLite.
REQUIRE_DATABASE_URL = env_bool("REQUIRE_DATABASE_URL", (RENDER or not DEBUG))

if FORCE_SQLITE:
    # Highest precedence: always use SQLite if explicitly requested
    sqlite_path = str(BASE_DIR / "db.sqlite3")
    DATABASES["default"] = {"ENGINE": "django.db.backends.sqlite3", "NAME": sqlite_path}

elif USE_LOCAL_SQLITE and not DATABASE_URL:
    # Dev-friendly default: use SQLite when developing and no DB URL provided
    sqlite_path = str(BASE_DIR / "db.sqlite3")
    DATABASES["default"] = {"ENGINE": "django.db.backends.sqlite3", "NAME": sqlite_path}

elif DATABASE_URL:
    # Respect DATABASE_URL when provided (typical for prod/hosted DBs)
    try:
        import dj_database_url  # type: ignore
    except Exception as e:
        raise RuntimeError("dj-database-url must be installed to use DATABASE_URL") from e

    DATABASES["default"] = dj_database_url.parse(
        DATABASE_URL,
        conn_max_age=600,
        ssl_require=USE_SSL,  # enforce SSL in prod
    )

elif REQUIRE_DATABASE_URL and not USE_LOCAL_SQLITE:
    # Hard fail to avoid ephemeral SQLite in prod
    raise RuntimeError("DATABASE_URL must be set in production (Render/DEBUG=False).")

else:
    # Optional: discrete Postgres vars for local setups without DATABASE_URL
    NAME = os.environ.get("POSTGRES_DB") or os.environ.get("DB_NAME", "circuitcity")
    USER = os.environ.get("POSTGRES_USER") or os.environ.get("DB_USER", "ccuser")
    PASSWORD = os.environ.get("POSTGRES_PASSWORD") or os.environ.get("DB_PASSWORD", "")
    HOST = os.environ.get("POSTGRES_HOST") or os.environ.get("DB_HOST", "127.0.0.1")
    PORT = os.environ.get("POSTGRES_PORT") or os.environ.get("DB_PORT", "5432")
    DATABASES["default"] = {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": NAME,
        "USER": USER,
        "PASSWORD": PASSWORD,
        "HOST": HOST,
        "PORT": PORT,
        "CONN_MAX_AGE": 600,
        "OPTIONS": {
            "connect_timeout": 5,
            **({"sslmode": "require"} if USE_SSL and HOST not in ("localhost", "127.0.0.1") else {}),
        },
    }

# -------------------------------------------------
# Caching (60s default; Redis if REDIS_URL provided)
# -------------------------------------------------
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

# -------------------------------------------------
# Password validation & hashing
# -------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 12}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# TEMPORARILY force PBKDF2 only (avoid Argon2 env/package mismatch while fixing login)
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]

# Be explicit (default backend) to avoid surprises
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
]

# -------------------------------------------------
# I18N / TZ
# -------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Africa/Blantyre"
USE_I18N = True
USE_TZ = True

# -------------------------------------------------
# Static / Media files
# -------------------------------------------------
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# WhiteNoise storages: manifest only in prod/tests off
_static_backend = (
    "django.contrib.staticfiles.storage.StaticFilesStorage"
    if (DEBUG or TESTING)
    else "whitenoise.storage.CompressedManifestStaticFilesStorage"
)

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": _static_backend},
}
WHITENOISE_AUTOREFRESH = DEBUG
# WHITENOISE_KEEP_ONLY_HASHED_FILES = True  # enable if desired

# -------------------------------------------------
# Auth redirects
# -------------------------------------------------
# Point to our accounts views (we also expose global hard aliases in cc.urls)
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "dashboard:agent_dashboard"  # namespaced url name
LOGOUT_REDIRECT_URL = "accounts:login"

# -------------------------------------------------
# Email / Admins
# -------------------------------------------------
ADMINS = [("Ops", os.environ.get("ADMIN_EMAIL", "ops@example.com"))]
EMAIL_SUBJECT_PREFIX = "[CC] "

USE_SMTP_IN_DEBUG = os.environ.get("FORCE_SMTP_IN_DEBUG") == "1"

if DEBUG and not USE_SMTP_IN_DEBUG:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
    DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "noreply@example.com")
else:
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST = os.environ.get("EMAIL_HOST", "smtp.gmail.com")
    EMAIL_PORT = env_int("EMAIL_PORT", 587)
    EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
    EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
    EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
    DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", EMAIL_HOST_USER or "noreply@example.com")
    EMAIL_TIMEOUT = env_int("EMAIL_TIMEOUT", 10)

# Recipients for the daily low-stock digest (Phase 6)
LOW_STOCK_ALERT_RECIPIENTS = [
    e.strip()
    for e in os.environ.get("LOW_STOCK_ALERT_RECIPIENTS", os.environ.get("ADMIN_EMAIL", "")).split(",")
    if e.strip()
]

# -------------------------------------------------
# Logging (with IMEI redaction) — JSON logs in prod
# -------------------------------------------------
class RedactIMEIFilter(logging.Filter):
    """Scrub 15-digit sequences that look like IMEIs from log messages."""
    IMEI_RE = re.compile(r"(?<!\d)\d{15}(?!\d)")

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
            if msg and self.IMEI_RE.search(msg):
                redacted = self.IMEI_RE.sub("[IMEI-REDACTED]", msg)
                record.msg = redacted
                record.args = ()
        except Exception:
            pass
        return True


USE_JSON_LOGS = env_bool("USE_JSON_LOGS", True) and not DEBUG

_json_formatter = {
    "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
    "fmt": "%(asctime)s %(levelname)s %(name)s %(message)s",
}

_plain_formatter = {"format": "%(levelname)s %(name)s: %(message)s"}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "redact_imei": {"()": "cc.settings.RedactIMEIFilter"},
    },
    "formatters": {
        "json": _json_formatter,
        "plain": _plain_formatter,
    },
    "handlers": {
        "console_json": {
            "class": "logging.StreamHandler",
            "filters": ["redact_imei"],
            "formatter": "json" if USE_JSON_LOGS else "plain",
        },
        "mail_admins": {
            "level": "ERROR",
            "class": "django.utils.log.AdminEmailHandler",
            "include_html": True,
            "filters": ["redact_imei"],
        },
    },
    "loggers": {
        # Access logs from cc.middleware.AccessLogMiddleware
        "access": {"handlers": ["console_json"], "level": "INFO", "propagate": False},
        # Django internals
        "django.request": {"handlers": ["mail_admins", "console_json"], "level": "ERROR", "propagate": False},
        "django.security": {"handlers": ["console_json"], "level": "WARNING", "propagate": False},
        # Root logger
        "": {"handlers": ["console_json"], "level": "INFO"},
    },
}

# -------------------------------------------------
# Default PK type
# -------------------------------------------------
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# -------------------------------------------------
# Audit logging
# -------------------------------------------------
AUDIT_LOG_SETTINGS = {
    "ENABLED": True,
    "AUDIT_MODEL": "inventory.AuditLog",
    "TRACK_DELETES": True,
    "TRACK_EDITS": True,
    "INCLUDE_USER": True,
}

# -------------------------------------------------
# V1 feature flags / Warranty checker
# -------------------------------------------------
V1_SIMPLE_DASHBOARD = True
WARRANTY_CHECK_ENABLED = env_bool("WARRANTY_CHECK_ENABLED", False)

WARRANTY_ENFORCE_COUNTRY = env_bool("WARRANTY_ENFORCE_COUNTRY", True)
ACTIVATION_ALERT_MINUTES = env_int("ACTIVATION_ALERT_MINUTES", 15)
WARRANTY_REQUEST_TIMEOUT = env_int("WARRANTY_REQUEST_TIMEOUT", 12)

# ---- Phase 6 feature toggles (optional; handy for pilots) ----
FEATURES = {
    "CSV_EXPORTS": os.environ.get("FEATURE_CSV_EXPORTS", "1") == "1",
    "CSV_IMPORT": os.environ.get("FEATURE_CSV_IMPORT", "1") == "1",
    "LOW_STOCK_DIGEST": os.environ.get("FEATURE_LOW_STOCK_DIGEST", "1") == "1",
    "ROLE_ENFORCEMENT": os.environ.get("FEATURE_ROLE_ENFORCEMENT", "1") == "1",
}

# Max safe expansion (units) per CSV row when quantity is given without serials
DATA_IMPORT_MAX_EXPANSION = env_int("DATA_IMPORT_MAX_EXPANSION", 5000)

# -------------------------------------------------
# Sentry (optional; enabled only if SENTRY_DSN is set)
# -------------------------------------------------
SENTRY_DSN = os.environ.get("SENTRY_DSN", "")
if SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[DjangoIntegration()],
        traces_sample_rate=float(os.environ.get("SENTRY_TRACES_SAMPLE_RATE", 0.0)),
        send_default_pii=True,
        environment=os.environ.get("SENTRY_ENV", "dev" if DEBUG else "prod"),
        release=os.environ.get("GIT_COMMIT", "local"),
    )

# -------------------------------------------------
# App metadata (optional, handy in feedback mailto)
# -------------------------------------------------
APP_NAME = os.environ.get("APP_NAME", "Circuit City")
APP_ENV = os.environ.get("APP_ENV", "dev" if DEBUG else "beta")
BETA_FEEDBACK_MAILTO = os.environ.get("BETA_FEEDBACK_MAILTO", "beta@circuitcity.example")

# -------------------------------------------------
# Accounts / Auth feature knobs (used by utils.reset & views)
# -------------------------------------------------
# OTP expiry (5 minutes), send window & max sends per window
ACCOUNTS_RESET_CODE_TTL_SECONDS = env_int("ACCOUNTS_RESET_CODE_TTL_SECONDS", 5 * 60)
ACCOUNTS_RESET_SEND_WINDOW_MINUTES = env_int("ACCOUNTS_RESET_SEND_WINDOW_MINUTES", 45)
ACCOUNTS_RESET_MAX_SENDS_PER_WINDOW = env_int("ACCOUNTS_RESET_MAX_SENDS_PER_WINDOW", 3)

# Staged login lockout policy (documentational; model implements same logic)
ACCOUNTS_LOGIN_LOCKOUT = {
    "STAGE0_FAILS": 3,
    "STAGE0_LOCK_SECONDS": 5 * 60,
    "STAGE1_FAILS": 2,
    "STAGE1_LOCK_SECONDS": 45 * 60,
    "STAGE2_FAILS": 2,
    "HARD_BLOCK": True,
}
