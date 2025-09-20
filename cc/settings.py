"""
Django settings for cc project.
"""

from pathlib import Path
from urllib.parse import urlparse
import os
import re
import logging
import sys
import importlib.util as _ils  # for optional imports

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

# Base DEBUG from envs
DEBUG = env_bool("DJANGO_DEBUG", env_bool("DEBUG", True))
TESTING = any(arg in sys.argv for arg in ("test", "pytest"))

# ⚠️ Make sure local runserver acts like dev unless you opt out
if "runserver" in sys.argv and not env_bool("FORCE_PROD_BEHAVIOR", False):
    DEBUG = True

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

# Add Render host if provided
if RENDER_EXTERNAL_URL:
    parsed = urlparse(RENDER_EXTERNAL_URL)
    host = parsed.netloc
    if host and host not in ALLOWED_HOSTS:
        # strip port if present
        ALLOWED_HOSTS.append(host.split(":")[0])

# Always allow *.onrender.com in hosted envs
if ".onrender.com" not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(".onrender.com")

# Optional explicit hosts
if LIVE_HOST and LIVE_HOST not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(LIVE_HOST)
if APP_DOMAIN and APP_DOMAIN not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(APP_DOMAIN)

# DEBUG/TESTING convenience: allow Django test client host
if DEBUG or TESTING:
    for h in ("testserver", "localhost", "127.0.0.1", "[::1]"):
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
    # also allow the dashboard healthz path if hit directly
    SECURE_REDIRECT_EXEMPT.append(r"^dashboard/healthz$")

SESSION_COOKIE_NAME = os.environ.get("SESSION_COOKIE_NAME", "cc_sessionid")
CSRF_COOKIE_NAME = os.environ.get("CSRF_COOKIE_NAME", "cc_csrftoken")

# Allow JS to read the CSRF cookie in DEBUG (so fetch can attach X-CSRFToken)
CSRF_COOKIE_HTTPONLY = False if DEBUG else True
SESSION_COOKIE_HTTPONLY = True
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_COOKIE_SAMESITE = os.environ.get("CSRF_COOKIE_SAMESITE", "Lax")
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
if DEBUG:
    SECURE_SSL_REDIRECT = False
    SESSION_COOKIE_SECURE = False
    CSRF_COOKIE_SECURE = False
    CSRF_COOKIE_HTTPONLY = False
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
    "hq",

    # NEW: multi-tenant core
    "tenants",

    # your apps
    "accounts.apps.AccountsConfig",   # ensure AppConfig.ready() runs signals
    "inventory",
    "sales",
    "dashboard",
    "onboarding",                     # ✅ add onboarding flow
    "insights",
    "wallet.apps.WalletConfig",

    # Avoid stdlib 'reports' collision on Windows paths.
    "ccreports.apps.ReportsConfig",

    # NEW: notifications app (bell icon + email/WhatsApp fanout)
    "notifications",

    # ✅ NEW: AI-CFO module
    "cfo",

    # ✅ NEW: Simulator (Scenarios & Simulation)
    "simulator",

    # ✅ NEW: Layby module
    "layby.apps.LaybyConfig",

    # ✅ NEW: Billing & subscriptions
    "billing",
]

# Optional OTP apps
if ENABLE_2FA:
    INSTALLED_APPS += [
        "phonenumber_field",
        "django_otp",
        "django_otp.plugins.otp_totp",
        "django_otp.plugins.otp_static",
        "two_factor",
        "two_factor.plugins.email",
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

    # ✅ Attach request.business from session (defense-in-depth; runs before tenant resolver)
    "tenants.utils.attach_business",

    # ✅ Resolve/override active tenant (if you have a richer resolver)
    "tenants.middleware.TenantResolutionMiddleware",

    # ✅ Billing trial/subscription gate (enforced by feature flag)
    "billing.middleware.SubscriptionGateMiddleware",

    # Inventory read-only guard when auditor mode is ON
    "inventory.middleware.AuditorReadOnlyMiddleware",

    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

# Only add OTP middleware if 2FA is enabled (must be after AuthenticationMiddleware)
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
# Base template config
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],  # project-level templates/
        "APP_DIRS": True,
        "OPTIONS": {
            "debug": DEBUG,
            # Preload only safe builtins; add optional ones below
            "builtins": [
                "django.templatetags.static",      # {% static %}
                "django.contrib.humanize.templatetags.humanize",  # intcomma, naturaltime, etc.
            ],
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "django.template.context_processors.static",
                "cc.context.globals",               # STATIC_VERSION, APP_NAME, APP_ENV, FEATURES, etc.
            ],
            # Default OFF to avoid scary ⚠️ markers unless you opt in.
            **(
                {"string_if_invalid": "⚠️ {{ %s }} ⚠️"}
                if DEBUG and env_bool("TEMPLATE_WARN_MISSING", False)
                else {}
            ),
        },
    },
]

# ---------- Optional template helpers (safe to miss) ----------
def _maybe_add_ctx(path: str):
    try:
        mod = ".".join(path.split(".")[:-1])
        if _ils.find_spec(mod):
            TEMPLATES[0]["OPTIONS"]["context_processors"].append(path)
    except Exception:
        pass

def _maybe_add_builtin(path: str):
    try:
        mod = ".".join(path.split(".")[:-1])
        if _ils.find_spec(mod):
            TEMPLATES[0]["OPTIONS"]["builtins"].append(path)
    except Exception:
        pass

# Context processors that are nice-to-have but optional
_maybe_add_ctx("core.context.flags")          # adds IS_MANAGER/IS_OWNER/IS_AGENT + FEATURES if available
_maybe_add_ctx("tenants.context.globals")     # may expose request.business / BRAND_NAME
_maybe_add_ctx("tenants.context.business")    # alt name if you create it

# Builtin template tags/filters that are optional
_maybe_add_builtin("tenants.templatetags.form_extras")  # e.g., |add_class; loaded only if present

WSGI_APPLICATION = "cc.wsgi.application"


# -------------------------------------------------
# Database — prefer SQLite locally; require DATABASE_URL when hosted
# -------------------------------------------------
DATABASES: dict = {}

# 🔧 DEFAULT CHANGE: do NOT force SQLite when hosted (Render).
# - Locally: default True (SQLite)
# - On hosting (Render/custom domain): default False (use Postgres via DATABASE_URL)
FORCE_SQLITE = env_bool("FORCE_SQLITE", default=not ON_HOSTING)
if FORCE_SQLITE:
    # Keep developer convenience locally
    os.environ.pop("DATABASE_URL", None)
    os.environ["USE_LOCAL_SQLITE"] = "1"

DATABASE_URL = _str_env("DATABASE_URL")
USE_LOCAL_SQLITE = env_bool("USE_LOCAL_SQLITE", default=(DEBUG and not ON_HOSTING))

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
    raise RuntimeError("DATABASE_URL must be set in production (hosted, DEBUG=False).")
else:
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
try:
    _db = DATABASES.get("default", {})
    print(f"[cc.settings] DB -> {_db.get('ENGINE')} | NAME={_db.get('NAME')} | DEBUG={DEBUG} | FORCE_SQLITE={FORCE_SQLITE}")
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
CELERY_TASK_ALWAYS_EAGER = env_bool("CELERY_TASK_ALWAYS_EAGER", False)
CELERY_TASK_TIME_LIMIT = env_int("CELERY_TASK_TIME_LIMIT", 60 * 5)
CELERY_TASK_SOFT_TIME_LIMIT = env_int("CELERY_TASK_SOFT_TIME_LIMIT", 60 * 4)

CELERY_BEAT_SCHEDULE = {
    "forecast_daily":   {"task": "insights.tasks.forecast_daily",   "schedule": crontab(hour=20, minute=15)},
    "alerts_low_stock": {"task": "insights.tasks.alerts_low_stock", "schedule": crontab(hour=7,  minute=45)},
    "nudges_hourly":    {"task": "insights.tasks.nudges_hourly",    "schedule": crontab(minute=0, hour="8-18")},
    "weekly_reports":   {"task": "insights.tasks.weekly_reports",   "schedule": crontab(hour=7,  minute=30, day_of_week="mon")},
    # ✅ NEW: Trial ending reminders (runs daily 08:00)
    "billing_trial_reminders": {"task": "billing.tasks.remind_trials_ending_soon", "schedule": crontab(hour=8, minute=0)},
}

if env_bool("ENABLE_PAYSLIP_SCHEDULER", True):
    CELERY_BEAT_SCHEDULE["payslips_monthly"] = {
        "task": "wallet.tasks.run_payout_schedules",
        "schedule": crontab(hour=6, minute=30, day_of_month="1"),
    }

CELERY_BEAT_SCHEDULE["cfo_nightly_cycle"] = {
    "task": "cfo.tasks.nightly_cfo_cycle",
    "schedule": crontab(hour=21, minute=30),
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

# ---- Auth redirects (conditional 2FA) ----
if ENABLE_2FA:
    LOGIN_URL = "two_factor:login"
    LOGOUT_REDIRECT_URL = "two_factor:login"
    TWO_FACTOR_PATCH_ADMIN = True
    PHONENUMBER_DEFAULT_REGION = os.environ.get("PHONENUMBER_DEFAULT_REGION", "MW")
else:
    # Use the named route for robustness across domains/paths
    LOGIN_URL = "accounts:login"
    LOGOUT_REDIRECT_URL = "accounts:login"

# Land users on the tenant-aware dashboard home (root routes to dashboard:home)
LOGIN_REDIRECT_URL = "/"

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
STATIC_VERSION = os.environ.get("STATIC_VERSION", "2025-09-19-1")

# ✅ Manifest hashing toggle:
#  - Always DISABLE manifest for runserver/DEBUG/TESTING unless you override with FORCE_PROD_BEHAVIOR=1.
DISABLE_MANIFEST = env_bool(
    "DISABLE_MANIFEST",
    default=(DEBUG or TESTING or ("runserver" in sys.argv and not env_bool("FORCE_PROD_BEHAVIOR", False)))
)
# Optional legacy knob for hosted prod environments
DISABLE_MANIFEST_IN_PROD = env_bool("DISABLE_MANIFEST_IN_PROD", False)

_use_manifest = not (DISABLE_MANIFEST or DISABLE_MANIFEST_IN_PROD)
_static_backend = (
    "whitenoise.storage.CompressedManifestStaticFilesStorage"
    if _use_manifest
    else "django.contrib.staticfiles.storage.StaticFilesStorage"
)

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": _static_backend},
}

# WhiteNoise: in dev auto-reload, in prod cache; never crash on missing manifest entries
WHITENOISE_AUTOREFRESH = DEBUG
WHITENOISE_MAX_AGE = 60 * 60 * 24 * 7  # 7 days
WHITENOISE_MANIFEST_STRICT = False


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

# NEW: Notification fanout configuration (email + WhatsApp)
NOTIFY_ADMIN_EMAILS = env_csv("NOTIFY_ADMIN_EMAILS", os.environ.get("ADMIN_EMAIL", ""))

# WhatsApp dispatch backend: "console", "twilio", or "meta"
WHATSAPP_BACKEND = os.environ.get("WHATSAPP_BACKEND", "console").lower()
ADMIN_WHATSAPP_NUMBER = os.environ.get("ADMIN_WHATSAPP_NUMBER", "").strip()

# Twilio WhatsApp (only if WHATSAPP_BACKEND="twilio")
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_WHATSAPP_FROM = os.environ.get("TWILIO_WHATSAPP_FROM", "")

# Meta WhatsApp Cloud API (only if WHATSAPP_BACKEND="meta")
WHATSAPP_TOKEN = os.environ.get("WHATSAPP_TOKEN", "")
WHATSAPP_PHONE_NUMBER_ID = os.environ.get("WHATSAPP_PHONE_NUMBER_ID", "")

# Optional: UI polling interval (ms) for bell icon badge refresh
NOTIFICATIONS_POLL_MS = env_int("NOTIFICATIONS_POLL_MS", 15000)


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

V1_SIMPLE_DASHBOARD = False
WARRANTY_CHECK_ENABLED = env_bool("WARRANTY_CHECK_ENABLED", False)

WARRANTY_ENFORCE_COUNTRY = env_bool("WARRANTY_ENFORCE_COUNTRY", True)
ACTIVATION_ALERT_MINUTES = env_int("ACTIVATION_ALERT_MINUTES", 15)
WARRANTY_REQUEST_TIMEOUT = env_int("WARRANTY_REQUEST_TIMEOUT", 12)

# Which Django Groups count as "manager" / "admin" (read by tenants.utils)
ROLE_GROUP_MANAGER_NAMES = env_csv("ROLE_GROUP_MANAGER_NAMES", "Manager,Admin")
ROLE_GROUP_ADMIN_NAMES = env_csv("ROLE_GROUP_ADMIN_NAMES", "Admin")

FEATURES = {
    "CSV_EXPORTS": os.environ.get("FEATURE_CSV_EXPORTS", "1") == "1",
    "CSV_IMPORT": os.environ.get("FEATURE_CSV_IMPORT", "1") == "1",
    "LOW_STOCK_DIGEST": os.environ.get("FEATURE_LOW_STOCK_DIGEST", "1") == "1",
    "ROLE_ENFORCEMENT": os.environ.get("FEATURE_ROLE_ENFORCEMENT", "1") == "1",
    "REPORTS": os.environ.get("FEATURE_REPORTS", "1") == "1",
    "NOTIFICATIONS": os.environ.get("FEATURE_NOTIFICATIONS", "1") == "1",
    # ✅ Toggle simulator UI/routes easily if you ever need to: FEATURE_SIMULATOR=0
    "SIMULATOR": os.environ.get("FEATURE_SIMULATOR", "1") == "1",
    # ✅ Layby feature flag (keeps routes/templates enabled while you iterate)
    "LAYBY": os.environ.get("FEATURE_LAYBY", "1") == "1",

    # ---------- New: role/UI guard rails ----------
    # Show CFO modules in UI; set to 0 to hide globally (agents never see them anyway in templates)
    "CFO": os.environ.get("FEATURE_CFO", "1") == "1",
    # Admin Purchase Order / Place Order UI (admin-only area)
    "ADMIN_PO": os.environ.get("FEATURE_ADMIN_PO", "1") == "1",
    # Let agents submit & view their own budget requests
    "AGENT_BUDGETS": os.environ.get("FEATURE_AGENT_BUDGETS", "1") == "1",
    # Safety belt to hide any admin affordances from agent templates if accidentally rendered
    "HIDE_ADMIN_UI_FOR_AGENTS": os.environ.get("FEATURE_HIDE_ADMIN_UI_FOR_AGENTS", "1") == "1",

    # ✅ NEW: Multi-tenant feature toggle
    "MULTI_TENANT": os.environ.get("FEATURE_MULTI_TENANT", "1") == "1",

    # ✅ NEW: Billing enforcement toggle (soft by default)
    "BILLING_ENFORCE": os.environ.get("FEATURE_BILLING_ENFORCE", "0") == "1",
}

DATA_IMPORT_MAX_EXPANSION = env_int("DATA_IMPORT_MAX_EXPANSION", 5000)

# ---------- Reports app knobs (safe defaults) ----------
REPORTS_DEFAULT_CURRENCY = os.environ.get("REPORTS_DEFAULT_CURRENCY", "MWK")
REPORTS_MAX_ROWS_EXPORT = env_int("REPORTS_MAX_ROWS_EXPORT", 50000)

# ---------- Public knobs used by inventory APIs ----------
# Currency symbol used by charts/UI when API returns amounts
CURRENCY_SIGN = os.environ.get("CURRENCY_SIGN", "MK")
# Owner field(s) that link inventory items to a user/agent. Comma list env override:
#   AGENT_OWNER_FIELDS="agent,handler,seller"
AGENT_OWNER_FIELDS = env_csv(
    "AGENT_OWNER_FIELDS",
    "agent,owner,user,assigned_to,sold_by,created_by,added_by,scanned_in_by,checked_in_by,last_modified_by",
)

# ---------- Agent visibility / scoping (STRICT SELF-ONLY) ----------
# Enforce that agents cannot see global/business-wide stock or KPIs.
AGENT_CAN_VIEW_ALL = env_bool("AGENT_CAN_VIEW_ALL", False)  # keep False
AGENT_SCOPE_MODE = os.environ.get("AGENT_SCOPE_MODE", "self").strip().lower()
if AGENT_SCOPE_MODE not in ("self", "business"):
    AGENT_SCOPE_MODE = "self"
# Dashboard for agents must NOT aggregate globally
DASHBOARD_AGENT_GLOBAL = env_bool("DASHBOARD_AGENT_GLOBAL", False)
# Optional cache-buster for any dashboard/inventory caches
INVENTORY_CACHE_BUST_VERSION = os.environ.get("INVENTORY_CACHE_BUST_VERSION", "1")

# -------------------------------------------------
# Sentry (optional)
# -------------------------------------------------
SENTRY_DSN = os.environ.get("SENTRY_DSN", "")
if SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[DjangoIntegration],
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

# -------------------------------
# ✅ Tenant/branding preferences
# -------------------------------
TENANT_SESSION_KEY = os.environ.get("TENANT_SESSION_KEY", "active_business_id")
TENANT_BRAND_FROM_BUSINESS = env_bool("TENANT_BRAND_FROM_BUSINESS", True)
TENANT_BRAND_FALLBACK = os.environ.get("TENANT_BRAND_FALLBACK", APP_NAME)

# Thread-local tenant toggle (used by tenant managers; kept for clarity)
TENANT_THREADLOCAL_ENABLED = True

# OTP window (used by accounts.views OTP flow)
OTP_WINDOW_MINUTES = env_int("OTP_WINDOW_MINUTES", 20)

# --------------------------------
# ✅ Optional: move Django Admin off /admin
# --------------------------------
# Set ADMIN_URL in your .env (e.g. ADMIN_URL=backoffice-4e8f1c/)
# 🔒 Default to a non-obvious path so managers won't stumble into it.
ADMIN_URL = os.environ.get("ADMIN_URL", "__admin__/")

# -------------------------------------------------
# Local dev helpers
# -------------------------------------------------
INTERNAL_IPS = ["127.0.0.1", "localhost"]


# -------------------------------------------------
# ✅ AI-CFO defaults & secrets (safe fallbacks; override in .env)
# -------------------------------------------------
AIRTEL_WEBHOOK_SECRET = os.environ.get("AIRTEL_WEBHOOK_SECRET", "replace_me")
FINANCE_EMAIL = os.environ.get("FINANCE_EMAIL", os.environ.get("ADMIN_EMAIL", "finance@example.com"))
CFO_OPENING_BALANCE_DEFAULT = os.environ.get("CFO_OPENING_BALANCE_DEFAULT", "0")

# -------------------------------------------------
# ✅ Layby / Payments knobs (override in .env as you go)
# -------------------------------------------------
# Require an HMAC or shared secret on payment webhooks in prod
LAYBY_WEBHOOK_REQUIRE_SECRET = env_bool("LAYBY_WEBHOOK_REQUIRE_SECRET", True)
# If you need a separate secret from Airtel’s, set LAYBY_WEBHOOK_SECRET; else we reuse AIRTEL_WEBHOOK_SECRET
LAYBY_WEBHOOK_SECRET = os.environ.get("LAYBY_WEBHOOK_SECRET", AIRTEL_WEBHOOK_SECRET)
# Customer OTP dev mode — when True, we render OTP on screen for quick testing
LAYBY_CUSTOMER_OTP_DEV = env_bool("LAYBY_CUSTOMER_OTP_DEV", DEBUG)

# -------------------------------------------------
# ✅ Billing / Subscription knobs
# -------------------------------------------------
# Default free-trial length (days). Use BILLING_TRIAL_DAYS in .env to override.
BILLING_TRIAL_DAYS = env_int("BILLING_TRIAL_DAYS", 30)
# Backward-compat alias for any legacy code that reads TRIAL_DAYS
TRIAL_DAYS = BILLING_TRIAL_DAYS


# -------------------------------------------------
# ⚠️ DEV-ONLY: migration guard rails to unblock broken local migrations
# -------------------------------------------------
# If you created bad placeholder migrations in the `inventory` app (e.g. 0017/0018) and
# Django refuses to load the migration graph (NodeNotFoundError), you can temporarily
# disable inventory migrations so `migrate` works for other apps and the server runs.
# This assumes your local SQLite already has the inventory tables (from earlier work).
# DO NOT enable this in production; fix the migrations instead.
DISABLE_INVENTORY_MIGRATIONS = env_bool("DISABLE_INVENTORY_MIGRATIONS", False)
MIGRATION_MODULES = {}
if DISABLE_INVENTORY_MIGRATIONS:
    MIGRATION_MODULES["inventory"] = None
    try:
        print("[cc.settings] WARNING: DISABLE_INVENTORY_MIGRATIONS=1 → inventory migrations are disabled in this run.")
    except Exception:
        pass
