"""
Django settings for cc project (local minimal).
"""

from pathlib import Path
from urllib.parse import urlparse
import os
import re
import logging
import sys
import importlib

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
        return int((os.environ.get(key) or "").strip())
    except Exception:
        return default

def feature_enabled(code: str, *, default: bool) -> bool:
    """
    Single source of truth for feature flags.
    Reads FEATURE_<CODE> from env; falls back to `default`.
    Example: FEATURE_LAYBY=1, FEATURE_SIMULATOR=0
    """
    return env_bool(f"FEATURE_{code.upper()}", default)

def _maybe(dotted_path: str) -> str | None:
    """
    Return dotted_path if it can be imported; else None.
    Useful for optional middleware.
    """
    try:
        mod_path, attr = dotted_path.rsplit(".", 1)
        mod = importlib.import_module(mod_path)
        getattr(mod, attr)
        return dotted_path
    except Exception:
        return None

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
    "django-insecure-w#o#i4apw-$iz-3sivw57n=2j6fgku@1pfqfs76@3@7)a0h$ys",
)

# Default to DEBUG=True locally unless overridden
DEBUG = env_bool("DJANGO_DEBUG", env_bool("DEBUG", True))
TESTING = any(arg in sys.argv for arg in ("test", "pytest"))

RENDER = bool(os.environ.get("RENDER") or os.environ.get("RENDER_EXTERNAL_URL"))
RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL", "")

APP_DOMAIN = os.environ.get("APP_DOMAIN", "").strip()
LIVE_HOST = os.environ.get("LIVE_HOST", "").strip()

_default_hosts = "localhost,127.0.0.1,0.0.0.0,192.168.1.104,.ngrok-free.app,.trycloudflare.com,.onrender.com"
ALLOWED_HOSTS = env_csv("ALLOWED_HOSTS", os.environ.get("DJANGO_ALLOWED_HOSTS", _default_hosts))

if RENDER_EXTERNAL_URL:
    parsed = urlparse(RENDER_EXTERNAL_URL)
    host = parsed.netloc
    if host and host not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(host)

if ".onrender.com" not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(".onrender.com")
if LIVE_HOST and LIVE_HOST not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(LIVE_HOST)
if APP_DOMAIN and APP_DOMAIN not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(APP_DOMAIN)

FORCE_SSL = env_bool("FORCE_SSL", env_bool("DJANGO_FORCE_SSL", False))
HEALTHZ_ALLOW_HTTP = env_bool("HEALTHZ_ALLOW_HTTP", False)

# Use SSL if explicitly forced OR (not DEBUG and not explicitly allowing http for healthz)
USE_SSL = FORCE_SSL or (not DEBUG)

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

# Optional local-HTTP override even with DEBUG=False
if os.environ.get("ALLOW_HTTP_LOCAL") == "1":
    SECURE_SSL_REDIRECT = False

if USE_SSL:
    SECURE_HSTS_SECONDS = env_int("SECURE_HSTS_SECONDS", 31536000)
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

if HEALTHZ_ALLOW_HTTP:
    SECURE_REDIRECT_EXEMPT = [r"^healthz$"]

# -------------------------------------------------
# Session & CSRF
# -------------------------------------------------
SESSION_COOKIE_NAME = os.environ.get("SESSION_COOKIE_NAME", "cc_sessionid")
CSRF_COOKIE_NAME = os.environ.get("CSRF_COOKIE_NAME", "cc_csrftoken")

CSRF_COOKIE_HTTPONLY = True
SESSION_COOKIE_HTTPONLY = True
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_COOKIE_SAMESITE = os.environ.get("SESSION_COOKIE_SAMESITE", "Lax")
CSRF_COOKIE_SAMESITE = os.environ.get("CSRF_COOKIE_SAMESITE", "Lax")
SESSION_COOKIE_AGE = 60 * 60 * 4  # 4 hours

SESSION_ENGINE = "django.contrib.sessions.backends.db"

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

def _add_origin(url: str):
    if url and url not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS.append(url)

if RENDER_EXTERNAL_URL:
    parsed = urlparse(RENDER_EXTERNAL_URL)
    if parsed.scheme and parsed.netloc:
        _add_origin(f"{parsed.scheme}://{parsed.netloc}")

if LIVE_HOST:
    _add_origin(f"https://{LIVE_HOST}")
if APP_DOMAIN:
    _add_origin(f"https://{APP_DOMAIN}")

# -------------------------------------------------
# Applications (LOCAL MINIMAL ONLY)
# -------------------------------------------------
INSTALLED_APPS = [
    # Django
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",

    # Your apps
    "circuitcity.accounts.apps.AccountsConfig",
    "tenants",
    "inventory",
    "sales",
    "dashboard",
    "layby",

    # Wallet (agent/admin money views)
    "wallet",
]

print("[cc.settings] Final INSTALLED_APPS:", INSTALLED_APPS)

# -------------------------------------------------
# Middleware
# -------------------------------------------------
MIDDLEWARE = [
    # Security & static
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",

    # Sessions (needed by everything below)
    "django.contrib.sessions.middleware.SessionMiddleware",

    # Observability
    "cc.middleware.RequestIDMiddleware",
    "cc.middleware.AccessLogMiddleware",

    # Core Django
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",

    # ---------- Multi-tenant + active context (correct order) ----------
    # 1) Resolve which tenant this request belongs to.
    "tenants.middleware.TenantResolutionMiddleware",

    # 2) If the user has exactly one business/location, auto-select it.
    "cc.middleware.AutoSelectBusinessMiddleware",

    # 3) Single Source of Truth for business/location:
    #    - sets request.business / request.active_location / *_id
    #    - syncs legacy session keys
    #    - adds ?biz=&loc= to list/dashboard when missing
    "inventory.middleware.ActiveContextMiddleware",
    # -------------------------------------------------------------------

    # Read-only protections for auditors (must run after context is known)
    "inventory.middleware.AuditorReadOnlyMiddleware",

    # Messages / clickjacking
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

# Optional friendly error catcher (only include if present)
_opt_friendly = _maybe("cc.middleware.FriendlyErrorsMiddleware")
if _opt_friendly:
    MIDDLEWARE.append(_opt_friendly)

# Let middleware handle exceptions in non-DEBUG environments
DEBUG_PROPAGATE_EXCEPTIONS = False

ROOT_URLCONF = "cc.urls"

# -------------------------------------------------
# Templates
# -------------------------------------------------
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [
            *(p for p in [BASE_DIR / "templates", BASE_DIR / "circuitcity" / "templates"] if p.exists())
        ],
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
# Database
# -------------------------------------------------
DATABASES: dict = {}

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()

# Strong, explicit switches for local dev:
FORCE_SQLITE = env_bool("FORCE_SQLITE", False)
USE_LOCAL_SQLITE = FORCE_SQLITE or env_bool("USE_LOCAL_SQLITE", default=DEBUG)

# Only require DATABASE_URL when we're truly in a non-local mode
# (i.e., not DEBUG and not explicitly told to use SQLite)
REQUIRE_DATABASE_URL = env_bool(
    "REQUIRE_DATABASE_URL",
    (RENDER or (not DEBUG and not USE_LOCAL_SQLITE))
)

if DATABASE_URL and not USE_LOCAL_SQLITE:
    try:
        import dj_database_url  # type: ignore
    except Exception as e:
        raise RuntimeError("dj-database-url must be installed") from e
    DATABASES["default"] = dj_database_url.parse(
        DATABASE_URL, conn_max_age=600, ssl_require=USE_SSL
    )
elif REQUIRE_DATABASE_URL and not USE_LOCAL_SQLITE:
    # Strict in prod/Render without explicit local override
    raise RuntimeError("DATABASE_URL must be set in production.")
elif USE_LOCAL_SQLITE or not DATABASE_URL:
    # Local/dev default — SQLite
    sqlite_path = str(BASE_DIR / "db.sqlite3")
    DATABASES["default"] = {"ENGINE": "django.db.backends.sqlite3", "NAME": sqlite_path}
else:
    # Manual Postgres config (optional path for local PG without DATABASE_URL)
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

try:
    _db = DATABASES.get("default", {})
    print(f"[cc.settings] DB -> {_db.get('ENGINE')} | NAME={_db.get('NAME')} | DEBUG={DEBUG} | FORCE_SQLITE={USE_LOCAL_SQLITE}")
except Exception:
    pass

# -------------------------------------------------
# Cache
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
# Passwords / Auth
# -------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 12}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
PASSWORD_HASHERS = ["django.contrib.auth.hashers.PBKDF2PasswordHasher"]
AUTHENTICATION_BACKENDS = ["django.contrib.auth.backends.ModelBackend"]

# -------------------------------------------------
# I18N
# -------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Africa/Blantyre"
USE_I18N = True
USE_TZ = True

# -------------------------------------------------
# Static / Media
# -------------------------------------------------
STATIC_URL = "/static/"

# Root static directories
STATICFILES_DIRS = [
    *(p for p in [BASE_DIR / "static", BASE_DIR / "circuitcity" / "static"] if p.exists()),
]

STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# Ensure default finders are enabled (FileSystemFinder + AppDirectories)
STATICFILES_FINDERS = [
    "django.contrib.staticfiles.finders.FileSystemFinder",
    "django.contrib.staticfiles.finders.AppDirectoriesFinder",
]

# Storage & WhiteNoise:
# - Dev/Tests: plain StaticFilesStorage (no manifest hashing)
# - Prod: CompressedManifestStaticFilesStorage (hashed names)
try:
    _static_backend = (
        "django.contrib.staticfiles.storage.StaticFilesStorage"
        if (DEBUG or TESTING)
        else "whitenoise.storage.CompressedManifestStaticFilesStorage"
    )
except Exception:
    _static_backend = "django.contrib.staticfiles.storage.StaticFilesStorage"

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": _static_backend},
}

# WhiteNoise dev helpers
WHITENOISE_AUTOREFRESH = DEBUG
# Ensure WhiteNoise serves from finders in dev (and in prod if needed without collectstatic)
WHITENOISE_USE_FINDERS = True

# -------------------------------------------------
# Auth redirects
# -------------------------------------------------
LOGIN_URL = "accounts:login"
# After login, jump to the auto-activator which picks the right business
LOGIN_REDIRECT_URL = "/tenants/activate-mine/"
LOGOUT_REDIRECT_URL = "accounts:login"

# -------------------------------------------------
# Email
# -------------------------------------------------
ADMINS = [("Ops", os.environ.get("ADMIN_EMAIL", "ops@example.com"))]
EMAIL_SUBJECT_PREFIX = "[CC] "

USE_SMTP_IN_DEBUG = os.environ.get("FORCE_SMTP_IN_DEBUG") == "1"

if DEBUG and not USE_SMTP_IN_DEBUG:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
    DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "noreply@example.com")
else:
    EMAIL_BACKEND = os.environ.get("EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend")
    EMAIL_HOST = os.environ.get("EMAIL_HOST", "smtp.gmail.com")
    EMAIL_PORT = env_int("EMAIL_PORT", 587)
    EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
    EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
    EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
    DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", EMAIL_HOST_USER or "noreply@example.com")
    EMAIL_TIMEOUT = env_int("EMAIL_TIMEOUT", 10)

LOW_STOCK_ALERT_RECIPIENTS = [
    e.strip()
    for e in os.environ.get("LOW_STOCK_ALERT_RECIPIENTS", os.environ.get("ADMIN_EMAIL", "")).split(",")
    if e.strip()
]

# -------------------------------------------------
# Logging
# -------------------------------------------------
class RedactIMEIFilter(logging.Filter):
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

try:
    import pythonjsonlogger  # type: ignore
    _have_json_logger = True
except Exception:
    _have_json_logger = False

USE_JSON_LOGS = env_bool("USE_JSON_LOGS", True) and not DEBUG and _have_json_logger

_json_formatter = {"()": "pythonjsonlogger.jsonlogger.JsonFormatter", "fmt": "%(asctime)s %(levelname)s %(name)s %(message)s"}
_plain_formatter = {"format": "%(levelname)s %(name)s: %(message)s"}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {"redact_imei": {"()": "cc.settings.RedactIMEIFilter"}},
    "formatters": {"json": _json_formatter, "plain": _plain_formatter},
    "handlers": {
        "console_json": {"class": "logging.StreamHandler", "filters": ["redact_imei"], "formatter": "json" if USE_JSON_LOGS else "plain"},
        "mail_admins": {"level": "ERROR", "class": "django.utils.log.AdminEmailHandler", "include_html": True, "filters": ["redact_imei"]},
    },
    "loggers": {
        "access": {"handlers": ["console_json"], "level": "INFO", "propagate": False},
        "django.request": {"handlers": ["mail_admins", "console_json"], "level": "ERROR", "propagate": False},
        "django.security": {"handlers": ["console_json"], "level": "WARNING", "propagate": False},
        "": {"handlers": ["console_json"], "level": "INFO"},
    },
}

# -------------------------------------------------
# Misc
# -------------------------------------------------
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUDIT_LOG_SETTINGS = {
    "ENABLED": True,
    "AUDIT_MODEL": "inventory.AuditLog",
    "TRACK_DELETES": True,
    "TRACK_EDITS": True,
    "INCLUDE_USER": True,
}

V1_SIMPLE_DASHBOARD = True
WARRANTY_CHECK_ENABLED = env_bool("WARRANTY_CHECK_ENABLED", False)
WARRANTY_ENFORCE_COUNTRY = env_bool("WARRANTY_ENFORCE_COUNTRY", True)
ACTIVATION_ALERT_MINUTES = env_int("ACTIVATION_ALERT_MINUTES", 15)
WARRANTY_REQUEST_TIMEOUT = env_int("WARRANTY_REQUEST_TIMEOUT", 12)

# ---- Single source of truth: product feature flags --------------------------
FEATURES = {
    # Existing flags kept compatible with env overrides
    "CSV_EXPORTS": env_bool("FEATURE_CSV_EXPORTS", True),
    "CSV_IMPORT": env_bool("FEATURE_CSV_IMPORT", True),
    "LOW_STOCK_DIGEST": env_bool("FEATURE_LOW_STOCK_DIGEST", True),
    "ROLE_ENFORCEMENT": env_bool("FEATURE_ROLE_ENFORCEMENT", True),

    # New clear flags used by templates/navigation
    # LAYBY is ON by default; can disable via FEATURE_LAYBY=0
    "LAYBY": feature_enabled("LAYBY", default=True),
    # SIMULATOR is OFF by default; enable via FEATURE_SIMULATOR=1
    "SIMULATOR": feature_enabled("SIMULATOR", default=False),
}
# -----------------------------------------------------------------------------

DATA_IMPORT_MAX_EXPANSION = env_int("DATA_IMPORT_MAX_EXPANSION", 5000)

# -------------------------------------------------
# Sentry
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
# Metadata
# -------------------------------------------------
APP_NAME = os.environ.get("APP_NAME", "Circuit City")
APP_ENV = os.environ.get("APP_ENV", "dev" if DEBUG else "beta")
BETA_FEEDBACK_MAILTO = os.environ.get("BETA_FEEDBACK_MAILTO", "beta@circuitcity.example")
