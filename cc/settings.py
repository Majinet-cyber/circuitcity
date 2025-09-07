"""
Django settings for cc project.
"""

from pathlib import Path
from urllib.parse import urlparse
import os
import re
import logging
import sys

# Safe import for Celery crontab (so settings still load before Celery is installed)
try:
    from celery.schedules import crontab  # type: ignore
except Exception:  # pragma: no cover
    def crontab(*args, **kwargs):
        return None


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


def _str_env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


# -------------------------------------------------
# Base paths
# -------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent


# -------------------------------------------------
# .env loading (python-dotenv) — do this EARLY
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

DEBUG = env_bool("DJANGO_DEBUG", env_bool("DEBUG", True))
TESTING = any(arg in sys.argv for arg in ("test", "pytest"))

# Make tracebacks bubble up during local dev to quickly find 500s
DEBUG_PROPAGATE_EXCEPTIONS = env_bool("DEBUG_PROPAGATE_EXCEPTIONS", DEBUG)

# Hosting hints (Render/custom domain/etc.)
RENDER = bool(os.environ.get("RENDER") or os.environ.get("RENDER_EXTERNAL_URL"))
RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL", "")

APP_DOMAIN = os.environ.get("APP_DOMAIN", "").strip()
LIVE_HOST = os.environ.get("LIVE_HOST", "").strip()

_default_hosts = "localhost,127.0.0.1,0.0.0.0,192.168.1.104,.ngrok-free.app,.trycloudflare.com,.onrender.com"
ALLOWED_HOSTS = env_csv("ALLOWED_HOSTS", os.environ.get("DJANGO_ALLOWED_HOSTS", _default_hosts))

# Optional extras for LAN/mobile testing
EXTRA_HOSTS = env_csv("EXTRA_HOSTS", "")
for h in EXTRA_HOSTS:
    if h and h not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(h)

LAN_IP = _str_env("LAN_IP")
if LAN_IP and LAN_IP not in ALLOWED_HOSTS:
    # ALLOWED_HOSTS must not include the port
    ALLOWED_HOSTS.append(LAN_IP)

if RENDER_EXTERNAL_URL:
    parsed = urlparse(RENDER_EXTERNAL_URL)
    host = parsed.netloc
    if host and host not in ALLOWED_HOSTS:
        # strip port if present
        ALLOWED_HOSTS.append(host.split(":")[0])

if ".onrender.com" not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(".onrender.com")

if LIVE_HOST and LIVE_HOST not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(LIVE_HOST)
if APP_DOMAIN and APP_DOMAIN not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(APP_DOMAIN)

# DEBUG/TESTING convenience: allow Django test client host
if DEBUG or TESTING:
    for h in ("testserver", "localhost", "127.0.0.1"):
        if h not in ALLOWED_HOSTS:
            ALLOWED_HOSTS.append(h)

FORCE_SSL = env_bool("FORCE_SSL", env_bool("DJANGO_FORCE_SSL", False))
ON_HOSTING = bool(RENDER or RENDER_EXTERNAL_URL or LIVE_HOST or APP_DOMAIN)
USE_SSL = FORCE_SSL or ON_HOSTING  # prod-ish envs default to SSL protections

HEALTHZ_ALLOW_HTTP = env_bool("HEALTHZ_ALLOW_HTTP", False)

BEHIND_SSL_PROXY = env_bool("BEHIND_SSL_PROXY", RENDER)
if BEHIND_SSL_PROXY:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    USE_X_FORWARDED_HOST = True
else:
    SECURE_PROXY_SSL_HEADER = None
    USE_X_FORWARDED_HOST = False

SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"

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

SECURE_REDIRECT_EXEMPT = []
if HEALTHZ_ALLOW_HTTP:
    SECURE_REDIRECT_EXEMPT.append(r"^healthz$")

SESSION_COOKIE_NAME = os.environ.get("SESSION_COOKIE_NAME", "cc_sessionid")
CSRF_COOKIE_NAME = os.environ.get("CSRF_COOKIE_NAME", "cc_csrftoken")

# Allow JS to read the CSRF cookie in DEBUG (so fetch can attach X-CSRFToken)
CSRF_COOKIE_HTTPONLY = False if DEBUG else True
SESSION_COOKIE_HTTPONLY = True
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_COOKIE_SAMESITE = os.environ.get("SESSION_COOKIE_SAMESITE", "Lax")  # ✅ fixed env name
CSRF_COOKIE_SAMESITE = os.environ.get("CSRF_COOKIE_SAMESITE", "Lax")
SESSION_COOKIE_AGE = 60 * 60 * 4  # 4 hours

SESSION_ENGINE = "django.contrib.sessions.backends.db"

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
_csrf_from_primary = os.environ.get("CSRF_TRUSTED_ORIGINS")
_csrf_from_legacy = os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", _default_csrf)
CSRF_TRUSTED_ORIGINS = env_csv("CSRF_TRUSTED_ORIGINS", _csrf_from_primary or _csrf_from_legacy)

# Helper to add computed origins
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

# Add LAN origins for mobile testing
if LAN_IP:
    _add_origin(f"http://{LAN_IP}")
    _add_origin(f"http://{LAN_IP}:8000")
    _add_origin(f"https://{LAN_IP}")

# Optional extras via env
for origin in env_csv("EXTRA_CSRF_ORIGINS", ""):
    _add_origin(origin)

# Add test client origin for convenience in DEBUG/TESTING
if DEBUG or TESTING:
    _add_origin("http://testserver")

# ----------- CRUCIAL FOR LOCAL LOGIN -----------
# In DEBUG, make absolutely sure cookies aren't "Secure" and no SSL redirect.
# This prevents the classic "login says invalid / session won't stick" on http://127.0.0.1:8000/.
if DEBUG:
    SECURE_SSL_REDIRECT = False
    SESSION_COOKIE_SECURE = False
    CSRF_COOKIE_SECURE = False
    CSRF_COOKIE_HTTPONLY = False  # <-- readable by JS in dev for fetch()-based POSTs
    SECURE_HSTS_SECONDS = 0
    SECURE_HSTS_INCLUDE_SUBDOMAINS = False
    SECURE_HSTS_PRELOAD = False
# ----------------------------------------------


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
# Applications
# -------------------------------------------------
# Toggle 2FA easily: set ENABLE_2FA=1 in environment if you want it ON.
ENABLE_2FA = env_bool("ENABLE_2FA", False)

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",

    # your apps
    "accounts.apps.AccountsConfig",  # ensure AppConfig.ready() runs signals
    "inventory",
    "sales",
    "dashboard",
    "insights",
    "wallet.apps.WalletConfig",

    # IMPORTANT: renamed to avoid conflict with stdlib 'reports' module name on Windows paths.
    # Our app package is 'ccreports' (with ReportsConfig inside).
    "ccreports.apps.ReportsConfig",
]

if ENABLE_2FA:
    # Required by two_factor migrations (imports phonenumbers via this app)
    INSTALLED_APPS += [
        "phonenumber_field",
        "django_otp",
        "django_otp.plugins.otp_totp",
        "django_otp.plugins.otp_static",
        "two_factor",
    ]

# Optional: django-debug-toolbar (only if DEBUG_TOOLBAR=1 and package installed)
if DEBUG and env_bool("DEBUG_TOOLBAR", False):
    try:
        import debug_toolbar  # type: ignore
        INSTALLED_APPS.append("debug_toolbar")  # pragma: no cover
    except Exception:
        pass


# -------------------------------------------------
# Middleware
# -------------------------------------------------
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    # ✅ Expose current request to inventory audit signals (tamper detection chain)
    "inventory.signals.RequestMiddleware",
    "cc.middleware.RequestIDMiddleware",
    "cc.middleware.AccessLogMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "inventory.middleware.AuditorReadOnlyMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

# Only add OTP middleware if 2FA is enabled
if ENABLE_2FA:
    MIDDLEWARE.insert(
        MIDDLEWARE.index("django.contrib.auth.middleware.AuthenticationMiddleware") + 1,
        "django_otp.middleware.OTPMiddleware",
    )

# Insert debug toolbar middleware at the top if enabled
if DEBUG and "debug_toolbar" in INSTALLED_APPS:
    MIDDLEWARE.insert(1, "debug_toolbar.middleware.DebugToolbarMiddleware")  # pragma: no cover

ROOT_URLCONF = "cc.urls"


# -------------------------------------------------
# Templates  ✅ Keep this simple & reliable
# -------------------------------------------------
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        # Always look in the project-level 'templates/' folder:
        "DIRS": [BASE_DIR / "templates"],
        # And also auto-discover app templates like:
        # accounts/templates/accounts/login.html
        "APP_DIRS": True,
        "OPTIONS": {
            "debug": DEBUG,  # helpful for template debugging in dev
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "django.template.context_processors.static",  # expose STATIC_URL
                "cc.context.globals",                       # expose STATIC_VERSION, APP_NAME, APP_ENV, FEATURES
            ],
            # In DEBUG, make missing variables very visible in templates
            **(
                {"string_if_invalid": "⚠️ {{ %s }} ⚠️"}
                if DEBUG and env_bool("TEMPLATE_WARN_MISSING", True)
                else {}
            ),
        },
    },
]

WSGI_APPLICATION = "cc.wsgi.application"


# -------------------------------------------------
# Database — prefer SQLite locally; require DATABASE_URL only when truly needed
# -------------------------------------------------
DATABASES: dict = {}

# Hard guard: always use SQLite in DEBUG unless explicitly overridden
FORCE_SQLITE_IN_DEBUG = True
if DEBUG and FORCE_SQLITE_IN_DEBUG:
    # Neutralize any hosted-style hints that might leak in
    os.environ.pop("DATABASE_URL", None)
    os.environ["USE_LOCAL_SQLITE"] = "1"

DATABASE_URL = _str_env("DATABASE_URL")
USE_LOCAL_SQLITE = env_bool("USE_LOCAL_SQLITE", default=DEBUG)

# Only require DATABASE_URL if explicitly requested via env, or we appear hosted AND not DEBUG AND not using SQLite
REQUIRE_DATABASE_URL = env_bool(
    "REQUIRE_DATABASE_URL",
    ON_HOSTING and (not DEBUG) and (not USE_LOCAL_SQLITE),
)

if DATABASE_URL:
    try:
        import dj_database_url  # type: ignore
    except Exception as e:
        raise RuntimeError("dj-database-url must be installed to use DATABASE_URL") from e

    DATABASES["default"] = dj_database_url.parse(
        DATABASE_URL,
        conn_max_age=600,
        ssl_require=USE_SSL,
    )
elif USE_LOCAL_SQLITE:
    sqlite_path = str(BASE_DIR / "db.sqlite3")
    DATABASES["default"] = {"ENGINE": "django.db.backends.sqlite3", "NAME": sqlite_path}
elif REQUIRE_DATABASE_URL:
    # We were explicitly told to require it, or we are in hosted non-debug w/o sqlite fallback
    raise RuntimeError("DATABASE_URL must be set in production (hosted, DEBUG=False).")
else:
    # Optional: discrete Postgres env vars
    NAME = _str_env("POSTGRES_DB") or _str_env("DB_NAME", "circuitcity")
    USER = _str_env("POSTGRES_USER") or _str_env("DB_USER", "ccuser")
    PASSWORD = _str_env("POSTGRES_PASSWORD") or _str_env("DB_PASSWORD", "")
    HOST = _str_env("POSTGRES_HOST") or _str_env("DB_HOST", "127.0.0.1")
    PORT = _str_env("POSTGRES_PORT") or _str_env("DB_PORT", "5432")
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

# Quick visibility in dev
if DEBUG:
    try:
        _db = DATABASES.get("default", {})
        print(f"[cc.settings] DB -> {_db.get('ENGINE')} | NAME={_db.get('NAME')}")
    except Exception:
        pass


# -------------------------------------------------
# Caching (Redis if REDIS_URL provided)
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
# Celery (task queue) — uses Redis if available
# -------------------------------------------------
CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL") or REDIS_URL or "redis://127.0.0.1:6379/0"
CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND") or CELERY_BROKER_URL
CELERY_TIMEZONE = "Africa/Blantyre"
CELERY_ENABLE_UTC = False
CELERY_TASK_ALWAYS_EAGER = env_bool("CELERY_TASK_ALWAYS_EAGER", False)  # handy for local tests
# ⬇️ Phase-2: sensible limits to prevent runaway tasks
CELERY_TASK_TIME_LIMIT = env_int("CELERY_TASK_TIME_LIMIT", 60 * 5)       # hard cap 5 min
CELERY_TASK_SOFT_TIME_LIMIT = env_int("CELERY_TASK_SOFT_TIME_LIMIT", 60 * 4)  # soft cap 4 min

CELERY_BEAT_SCHEDULE = {
    "forecast_daily":   {"task": "insights.tasks.forecast_daily",   "schedule": crontab(hour=20, minute=15)},
    "alerts_low_stock": {"task": "insights.tasks.alerts_low_stock", "schedule": crontab(hour=7,  minute=45)},
    "nudges_hourly":    {"task": "insights.tasks.nudges_hourly",    "schedule": crontab(minute=0, hour="8-18")},
    "weekly_reports":   {"task": "insights.tasks.weekly_reports",   "schedule": crontab(hour=7,  minute=30, day_of_week="mon")},
}

# Optional monthly payslip auto-run (guarded)
if env_bool("ENABLE_PAYSLIP_SCHEDULER", True):
    CELERY_BEAT_SCHEDULE["payslips_monthly"] = {
        "task": "wallet.tasks.run_payout_schedules",
        "schedule": crontab(hour=6, minute=30, day_of_month="1"),
    }


# -------------------------------------------------
# Auth & passwords
# -------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 12}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
]

# Auth redirects
LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/inventory/"          # ⬅️ send users to the stock list (inventory home)
LOGOUT_REDIRECT_URL = "/accounts/login/"

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

# ---- UI cache-busting (used in templates as ?v={{ STATIC_VERSION }}) ----
STATIC_VERSION = os.environ.get("STATIC_VERSION", "2025-09-07-1")  # bumped to refresh cached assets

# Safety valve: allow disabling manifest storage in prod by env
DISABLE_MANIFEST_IN_PROD = env_bool("DISABLE_MANIFEST_IN_PROD", False)

try:
    _static_backend = (
        "django.contrib.staticfiles.storage.StaticFilesStorage"
        if (DEBUG or TESTING or DISABLE_MANIFEST_IN_PROD)
        else "whitenoise.storage.CompressedManifestStaticFilesStorage"
    )
except Exception:
    _static_backend = "django.contrib.staticfiles.storage.StaticFilesStorage"

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": _static_backend},
}

# WhiteNoise: in dev auto-reload, in prod cache; do not 500 on missing manifest entries
WHITENOISE_AUTOREFRESH = DEBUG
WHITENOISE_MAX_AGE = 60 * 60 * 24 * 7  # 7 days
WHITENOISE_MANIFEST_STRICT = False     # <— prevents "Missing staticfiles manifest entry" from crashing


# -------------------------------------------------
# Email
# -------------------------------------------------
ADMINS = [("Ops", os.environ.get("ADMIN_EMAIL", "ops@example.com"))]
EMAIL_SUBJECT_PREFIX = os.environ.get("EMAIL_SUBJECT_PREFIX", "[CC] ")

# Support either name; prefer FORCE_SMTP_IN_DEBUG
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
    # Prefer explicit DEFAULT_FROM_EMAIL; otherwise construct "App <user>" if user present
    DEFAULT_FROM_EMAIL = (
        os.environ.get("DEFAULT_FROM_EMAIL")
        or (f"{os.environ.get('APP_NAME', 'Circuit City')} <{EMAIL_HOST_USER}>" if EMAIL_HOST_USER else "noreply@example.com")
    )
    SERVER_EMAIL = os.environ.get("SERVER_EMAIL", DEFAULT_FROM_EMAIL)
    EMAIL_TIMEOUT = env_int("EMAIL_TIMEOUT", 10)

# Low-stock digest config
LOW_STOCK_ALERT_RECIPIENTS = [
    e.strip()
    for e in os.environ.get("LOW_STOCK_ALERT_RECIPIENTS", os.environ.get("ADMIN_EMAIL", "")).split(",")
    if e.strip()
]


# -------------------------------------------------
# Logging (IMEI redaction; JSON logs in prod when available)
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

V1_SIMPLE_DASHBOARD = False  # <- restore full-featured dashboard UI
WARRANTY_CHECK_ENABLED = env_bool("WARRANTY_CHECK_ENABLED", False)

WARRANTY_ENFORCE_COUNTRY = env_bool("WARRANTY_ENFORCE_COUNTRY", True)
ACTIVATION_ALERT_MINUTES = env_int("ACTIVATION_ALERT_MINUTES", 15)
WARRANTY_REQUEST_TIMEOUT = env_int("WARRANTY_REQUEST_TIMEOUT", 12)

FEATURES = {
    "CSV_EXPORTS": os.environ.get("FEATURE_CSV_EXPORTS", "1") == "1",
    "CSV_IMPORT": os.environ.get("FEATURE_CSV_IMPORT", "1") == "1",
    "LOW_STOCK_DIGEST": os.environ.get("FEATURE_LOW_STOCK_DIGEST", "1") == "1",
    "ROLE_ENFORCEMENT": os.environ.get("FEATURE_ROLE_ENFORCEMENT", "1") == "1",
    "REPORTS": os.environ.get("FEATURE_REPORTS", "1") == "1",  # ✅ enable Reports
}

DATA_IMPORT_MAX_EXPANSION = env_int("DATA_IMPORT_MAX_EXPANSION", 5000)

# ---------- Reports app knobs (safe defaults) ----------
REPORTS_DEFAULT_CURRENCY = os.environ.get("REPORTS_DEFAULT_CURRENCY", "MWK")
REPORTS_MAX_ROWS_EXPORT = env_int("REPORTS_MAX_ROWS_EXPORT", 50000)


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
# Local dev helpers
# -------------------------------------------------
INTERNAL_IPS = ["127.0.0.1", "localhost"]
