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
# Paths & .env
# -------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent

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

DEBUG = env_bool("DJANGO_DEBUG", env_bool("DEBUG", True))
TESTING = any(arg in sys.argv for arg in ("test", "pytest"))

RENDER = bool(os.environ.get("RENDER") or os.environ.get("RENDER_EXTERNAL_URL"))
RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL", "").strip()
APP_DOMAIN = os.environ.get("APP_DOMAIN", "").strip()
LIVE_HOST = os.environ.get("LIVE_HOST", "").strip()

_default_hosts = "localhost,127.0.0.1,0.0.0.0,192.168.1.104,.ngrok-free.app,.trycloudflare.com,.onrender.com"
ALLOWED_HOSTS = env_csv("ALLOWED_HOSTS", os.environ.get("DJANGO_ALLOWED_HOSTS", _default_hosts))

# Add Render external host if provided
if RENDER_EXTERNAL_URL:
    _parsed = urlparse(RENDER_EXTERNAL_URL)
    _host = _parsed.netloc.split(":")[0]
    if _host and _host not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(_host)

# Always allow *.onrender.com
if ".onrender.com" not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(".onrender.com")

# Explicit hosts
for _h in (LIVE_HOST, APP_DOMAIN):
    if _h and _h not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(_h)

# Dev/test convenience
if DEBUG or TESTING:
    for _h in ("testserver", "localhost", "127.0.0.1", "[::1]"):
        if _h not in ALLOWED_HOSTS:
            ALLOWED_HOSTS.append(_h)

# SSL policy
FORCE_SSL = env_bool("FORCE_SSL", env_bool("DJANGO_FORCE_SSL", False))
USE_SSL = FORCE_SSL or (RENDER and not DEBUG)
HEALTHZ_ALLOW_HTTP = env_bool("HEALTHZ_ALLOW_HTTP", False)

# Security headers
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True

SECURE_SSL_REDIRECT = bool(USE_SSL) and not HEALTHZ_ALLOW_HTTP
SESSION_COOKIE_SECURE = bool(USE_SSL)
CSRF_COOKIE_SECURE = bool(USE_SSL)

if USE_SSL:
    SECURE_HSTS_SECONDS = env_int("SECURE_HSTS_SECONDS", 31536000)
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
else:
    SECURE_HSTS_SECONDS = 0
    SECURE_HSTS_INCLUDE_SUBDOMAINS = False
    SECURE_HSTS_PRELOAD = False

SECURE_REDIRECT_EXEMPT = [r"^healthz$"] if HEALTHZ_ALLOW_HTTP else []


# -------------------------------------------------
# Session & CSRF
# -------------------------------------------------
SESSION_COOKIE_NAME = os.environ.get("SESSION_COOKIE_NAME", "cc_sessionid")
CSRF_COOKIE_NAME = os.environ.get("CSRF_COOKIE_NAME", "cc_csrftoken")

CSRF_COOKIE_HTTPONLY = False if DEBUG else True
SESSION_COOKIE_HTTPONLY = True
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_COOKIE_SAMESITE = os.environ.get("SESSION_COOKIE_SAMESITE", "Lax")
CSRF_COOKIE_SAMESITE = os.environ.get("CSRF_COOKIE_SAMESITE", "Lax")
SESSION_COOKIE_AGE = 60 * 60 * 4  # 4 hours

SESSION_ENGINE = "django.contrib.sessions.backends.db"

# CSRF trusted origins (must include scheme)
_default_csrf = ",".join(
    [
        "http://localhost",
        "http://127.0.0.1",
        "http://0.0.0.0",
        "http://192.168.1.104",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "https://*.ngrok-free.app",
        "https://*.trycloudflare.com",
        "https://*.onrender.com",
    ]
)
_csrf_primary = os.environ.get("CSRF_TRUSTED_ORIGINS")
_csrf_legacy = os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", _default_csrf)
CSRF_TRUSTED_ORIGINS = env_csv("CSRF_TRUSTED_ORIGINS", _csrf_primary or _csrf_legacy)

def _add_origin(url: str):
    if url and url not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS.append(url)

if RENDER_EXTERNAL_URL:
    _p = urlparse(RENDER_EXTERNAL_URL)
    if _p.scheme and _p.netloc:
        _add_origin(f"{_p.scheme}://{_p.netloc.split(':')[0]}")
if LIVE_HOST:
    _add_origin(f"https://{LIVE_HOST}")
if APP_DOMAIN:
    _add_origin(f"https://{APP_DOMAIN}")


# -------------------------------------------------
# Upload limits
# -------------------------------------------------
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10 MB
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024   # 5 MB
FILE_UPLOAD_HANDLERS = [
    "django.core.files.uploadhandler.MemoryFileUploadHandler",
    "django.core.files.uploadhandler.TemporaryFileUploadHandler",
]
FILE_UPLOAD_PERMISSIONS = 0o640
FILE_UPLOAD_DIRECTORY_PERMISSIONS = 0o750


# -------------------------------------------------
# Installed apps
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

    # WhiteNoise helper for dev (prevents double static handling)
    "whitenoise.runserver_nostatic",

    # Local apps (use full dotted paths for reliability)
    "circuitcity.tenants.apps.TenantsConfig",
    "circuitcity.accounts.apps.AccountsConfig",
    "circuitcity.inventory",
    "circuitcity.sales",
    "circuitcity.dashboard",
]

# -------------------------------------------------
# Middleware
# -------------------------------------------------
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",

    # Observability middlewares present in your repo
    "cc.middleware.RequestIDMiddleware",
    "cc.middleware.AccessLogMiddleware",

    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",

    # Inventory read-only guard present in your repo
    "circuitcity.inventory.middleware.AuditorReadOnlyMiddleware",

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
        "DIRS": [
            BASE_DIR / "circuitcity" / "templates",
            BASE_DIR / "templates",
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
# Database — SQLite locally; DATABASE_URL supported
# -------------------------------------------------
DATABASES: dict = {}

FORCE_SQLITE = env_bool("FORCE_SQLITE", False)
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
USE_LOCAL_SQLITE = env_bool("USE_LOCAL_SQLITE", default=DEBUG)
REQUIRE_DATABASE_URL = env_bool("REQUIRE_DATABASE_URL", (RENDER or not DEBUG))

if FORCE_SQLITE or (USE_LOCAL_SQLITE and not DATABASE_URL):
    sqlite_path = str(BASE_DIR / "db.sqlite3")
    DATABASES["default"] = {"ENGINE": "django.db.backends.sqlite3", "NAME": sqlite_path}
elif DATABASE_URL:
    try:
        import dj_database_url  # type: ignore
    except Exception as e:
        raise RuntimeError("dj-database-url must be installed to use DATABASE_URL") from e
    DATABASES["default"] = dj_database_url.parse(
        DATABASE_URL,
        conn_max_age=600,
        ssl_require=bool(USE_SSL and not DEBUG),
    )
elif REQUIRE_DATABASE_URL and not USE_LOCAL_SQLITE:
    raise RuntimeError("DATABASE_URL must be set in production (Render/DEBUG=False).")
else:
    # Optional discrete Postgres env vars
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
    }


# -------------------------------------------------
# Cache (Redis if REDIS_URL set; else local memory)
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
# Auth & i18n
# -------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 12}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
    {
        "NAME": "circuitcity.accounts.validators.StrongPasswordValidator",
        "OPTIONS": {
            "min_len": 12,
            "require_digit": True,
            "require_upper": True,
            "require_lower": True,
            "require_symbol": True,
        },
    },
]

PASSWORD_HASHERS = ["django.contrib.auth.hashers.PBKDF2PasswordHasher"]

AUTHENTICATION_BACKENDS = ["django.contrib.auth.backends.ModelBackend"]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Africa/Blantyre"
USE_I18N = True
USE_TZ = True


# -------------------------------------------------
# Static / Media
# -------------------------------------------------
STATIC_URL = "/static/"
STATICFILES_DIRS = [
    *(p for p in [BASE_DIR / "static", BASE_DIR / "circuitcity" / "static"] if p.exists())
]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# WhiteNoise storage (manifest only when not DEBUG/TESTING)
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
# Prevent 500s if a hashed asset is referenced but missing after deploy
WHITENOISE_MANIFEST_STRICT = False


# -------------------------------------------------
# Auth redirects
# -------------------------------------------------
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "accounts:login"

# Messages storage (robust across redirects)
MESSAGE_STORAGE = "django.contrib.messages.storage.session.SessionStorage"


# -------------------------------------------------
# Email
# -------------------------------------------------
ADMINS = [("Ops", os.environ.get("ADMIN_EMAIL", "ops@example.com"))]
EMAIL_SUBJECT_PREFIX = os.environ.get("EMAIL_SUBJECT_PREFIX", "[CC] ")

FORCE_SMTP_IN_DEBUG = env_bool("FORCE_SMTP_IN_DEBUG", False) or env_bool("USE_SMTP_IN_DEBUG", False)

if DEBUG and not FORCE_SMTP_IN_DEBUG:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
    DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "noreply@example.com")
else:
    EMAIL_BACKEND = os.environ.get("EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend")
    EMAIL_HOST = os.environ.get("EMAIL_HOST", "smtp.gmail.com")
    EMAIL_PORT = env_int("EMAIL_PORT", 587)
    EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
    EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
    EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
    DEFAULT_FROM_EMAIL = (
        os.environ.get("DEFAULT_FROM_EMAIL")
        or (f"{os.environ.get('APP_NAME', 'Circuit City')} <{EMAIL_HOST_USER}>" if EMAIL_HOST_USER else "noreply@example.com")
    )
    SERVER_EMAIL = os.environ.get("SERVER_EMAIL", DEFAULT_FROM_EMAIL)
    EMAIL_TIMEOUT = env_int("EMAIL_TIMEOUT", 10)

LOW_STOCK_ALERT_RECIPIENTS = [
    e.strip()
    for e in os.environ.get("LOW_STOCK_ALERT_RECIPIENTS", os.environ.get("ADMIN_EMAIL", "")).split(",")
    if e.strip()
]


# -------------------------------------------------
# Logging (IMEI redaction; JSON in prod)
# -------------------------------------------------
class RedactIMEIFilter(logging.Filter):
    IMEI_RE = re.compile(r"(?<!\d)\d{15}(?!\d)")
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
            if msg and self.IMEI_RE.search(msg):
                record.msg = self.IMEI_RE.sub("[IMEI-REDACTED]", msg)
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

_json_formatter = {
    "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
    "fmt": "%(asctime)s %(levelname)s %(name)s %(message)s",
}

_plain_formatter = {"format": "%(levelname)s %(name)s: %(message)s"}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {"redact_imei": {"()": "cc.settings.RedactIMEIFilter"}},
    "formatters": {"json": _json_formatter, "plain": _plain_formatter},
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
        "access": {"handlers": ["console_json"], "level": "INFO", "propagate": False},
        "django.request": {"handlers": ["mail_admins", "console_json"], "level": "ERROR", "propagate": False},
        "django.security": {"handlers": ["console_json"], "level": "WARNING", "propagate": False},
        "": {"handlers": ["console_json"], "level": "INFO"},
    },
}


# -------------------------------------------------
# Misc app flags
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

FEATURES = {
    "CSV_EXPORTS": os.environ.get("FEATURE_CSV_EXPORTS", "1") == "1",
    "CSV_IMPORT": os.environ.get("FEATURE_CSV_IMPORT", "1") == "1",
    "LOW_STOCK_DIGEST": os.environ.get("FEATURE_LOW_STOCK_DIGEST", "1") == "1",
    "ROLE_ENFORCEMENT": os.environ.get("FEATURE_ROLE_ENFORCEMENT", "1") == "1",
}

DATA_IMPORT_MAX_EXPANSION = env_int("DATA_IMPORT_MAX_EXPANSION", 5000)


# -------------------------------------------------
# Sentry (optional)
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
# App metadata
# -------------------------------------------------
APP_NAME = os.environ.get("APP_NAME", "Circuit City")
APP_ENV = os.environ.get("APP_ENV", "dev" if DEBUG else "beta")
BETA_FEEDBACK_MAILTO = os.environ.get("BETA_FEEDBACK_MAILTO", "beta@circuitcity.example")


# -------------------------------------------------
# Accounts / Auth feature knobs
# -------------------------------------------------
ACCOUNTS_RESET_CODE_TTL_SECONDS = env_int("ACCOUNTS_RESET_CODE_TTL_SECONDS", 5 * 60)
ACCOUNTS_RESET_SEND_WINDOW_MINUTES = env_int("ACCOUNTS_RESET_SEND_WINDOW_MINUTES", 45)
ACCOUNTS_RESET_MAX_SENDS_PER_WINDOW = env_int("ACCOUNTS_RESET_MAX_SENDS_PER_WINDOW", 3)

ACCOUNTS_LOGIN_LOCKOUT = {
    "STAGE0_FAILS": 3,
    "STAGE0_LOCK_SECONDS": 5 * 60,
    "STAGE1_FAILS": 2,
    "STAGE1_LOCK_SECONDS": 45 * 60,
    "STAGE2_FAILS": 2,
    "HARD_BLOCK": True,
}
