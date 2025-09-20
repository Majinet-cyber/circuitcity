"""
Django settings for cc project.
"""

from pathlib import Path
from urllib.parse import urlparse
import importlib
import logging
import os
import re
import sys

# -------------------------------------------------
# Small env helpers
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
# Paths & .env
# -------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv(BASE_DIR / ".env")
except Exception:
    pass

# -------------------------------------------------
# Utilities to resolve modules in either location
# -------------------------------------------------
def _first_importable(*candidates: str) -> str | None:
    for dotted in candidates:
        try:
            importlib.import_module(dotted)
            return dotted
        except Exception:
            continue
    return None

# Apps we know are top-level in your repo (per your import checks):
TOP_LEVEL_FIRST: set[str] = {
    "inventory",
    "wallet",
    "ccreports",
    "tenants",
    "billing",
    "notifications",
    "layby",
    "hq",
    "reports",
    "sales",
    "simulator",
    "cfo",
    "insights",
    "common",
    "core",
    "onboarding",
}

def _resolve_app(pkg: str, config_class: str | None = None) -> str | None:
    """
    Return an INSTALLED_APPS entry for `pkg`, trying both the package path
    and the top-level path. If `pkg` is in TOP_LEVEL_FIRST, prefer the short
    name; otherwise prefer 'circuitcity.<pkg>'.

    If config_class is provided (e.g., 'AccountsConfig'), choose the AppConfig
    path if present.
    """
    if pkg in TOP_LEVEL_FIRST:
        bases = (pkg, f"circuitcity.{pkg}")
    else:
        bases = (f"circuitcity.{pkg}", pkg)

    if config_class:
        for base in bases:
            try:
                mod = importlib.import_module(f"{base}.apps")
                if hasattr(mod, config_class):
                    return f"{base}.apps.{config_class}"
            except Exception:
                pass
    # fall back to package itself if importable
    return _first_importable(*bases)

def _resolve_middleware(mod_base: str, cls: str) -> str:
    # Prefer short for top-level apps, else packaged
    if mod_base.split(".", 1)[0] in TOP_LEVEL_FIRST:
        dotted = _first_importable(mod_base, f"circuitcity.{mod_base}")
    else:
        dotted = _first_importable(f"circuitcity.{mod_base}", mod_base)
    if not dotted:
        # last resort: return what caller passed (it may still import at runtime)
        return f"{mod_base}.{cls}"
    return f"{dotted}.{cls}"

# -------------------------------------------------
# Security / Debug
# -------------------------------------------------
SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "django-insecure-w#o#i4apw-$iz-3sivw57n=2j6fgku@1pfqfs76@3@7)a0h$ys",  # dev fallback
)

DEBUG = env_bool("DJANGO_DEBUG", env_bool("DEBUG", True))
TESTING = any(arg in sys.argv for arg in ("test", "pytest"))

# Make `runserver` dev-friendly unless you force prod behaviour
if "runserver" in sys.argv and not env_bool("FORCE_PROD_BEHAVIOR", False):
    DEBUG = True

DEBUG_PROPAGATE_EXCEPTIONS = env_bool("DEBUG_PROPAGATE_EXCEPTIONS", DEBUG)

RENDER = bool(os.environ.get("RENDER") or os.environ.get("RENDER_EXTERNAL_URL"))
RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL", "")
APP_DOMAIN = os.environ.get("APP_DOMAIN", "").strip()
LIVE_HOST = os.environ.get("LIVE_HOST", "").strip()

_default_hosts = "localhost,127.0.0.1,0.0.0.0,192.168.1.104,.ngrok-free.app,.trycloudflare.com,.onrender.com"
ALLOWED_HOSTS = env_csv("ALLOWED_HOSTS", os.environ.get("DJANGO_ALLOWED_HOSTS", _default_hosts))

EXTRA_HOSTS = env_csv("EXTRA_HOSTS", "")
for h in EXTRA_HOSTS:
    if h and h not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(h)

LAN_IP = _str_env("LAN_IP")
if LAN_IP and LAN_IP not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(LAN_IP)

if RENDER_EXTERNAL_URL:
    parsed = urlparse(RENDER_EXTERNAL_URL)
    host = parsed.netloc.split(":")[0]
    if host and host not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(host)

if ".onrender.com" not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(".onrender.com")

for _h in (LIVE_HOST, APP_DOMAIN):
    if _h and _h not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(_h)

if DEBUG or TESTING:
    for _h in ("testserver", "localhost", "127.0.0.1", "[::1]"):
        if _h not in ALLOWED_HOSTS:
            ALLOWED_HOSTS.append(_h)

FORCE_SSL = env_bool("FORCE_SSL", env_bool("DJANGO_FORCE_SSL", False))
ON_HOSTING = bool(RENDER or RENDER_EXTERNAL_URL or LIVE_HOST or APP_DOMAIN)
USE_SSL = FORCE_SSL or ON_HOSTING
HEALTHZ_ALLOW_HTTP = env_bool("HEALTHZ_ALLOW_HTTP", False)

BEHIND_SSL_PROXY = env_bool("BEHIND_SSL_PROXY", RENDER)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https") if BEHIND_SSL_PROXY else None
USE_X_FORWARDED_HOST = bool(BEHIND_SSL_PROXY)

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

SECURE_REDIRECT_EXEMPT = [r"^healthz$"] if HEALTHZ_ALLOW_HTTP else []

SESSION_COOKIE_NAME = os.environ.get("SESSION_COOKIE_NAME", "cc_sessionid")
CSRF_COOKIE_NAME = os.environ.get("CSRF_COOKIE_NAME", "cc_csrftoken")

CSRF_COOKIE_HTTPONLY = False if DEBUG else True
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
if LAN_IP:
    _add_origin(f"http://{LAN_IP}")
    _add_origin(f"http://{LAN_IP}:8000")

for o in env_csv("EXTRA_CSRF_ORIGINS", ""):
    _add_origin(o)
if DEBUG or TESTING:
    _add_origin("http://testserver")

# -------------------------------------------------
# Uploads
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
# Applications (auto-resolved from your repo)
# -------------------------------------------------
# Which apps should use AppConfig classes
_APP_NAMES_WITH_CONFIG = {
    "accounts": "AccountsConfig",      # package app
    "tenants": "TenantsConfig",        # top-level app with AppConfig
}

# Simple apps (no special AppConfig required)
_APP_NAMES_SIMPLE = [
    "audit", "billing", "ccreports", "cfo", "common", "core", "dashboard",
    "hq", "insights", "inventory", "layby", "notifications",
    "onboarding", "reports", "sales", "simulator", "wallet",
]

LOCAL_APPS: list[str] = []

# apps with specific AppConfig class
for name, cfg in _APP_NAMES_WITH_CONFIG.items():
    resolved = _resolve_app(name, cfg)
    if resolved:
        LOCAL_APPS.append(resolved)

# simple apps (no special AppConfig required)
for name in _APP_NAMES_SIMPLE:
    resolved = _resolve_app(name)
    if resolved:
        LOCAL_APPS.append(resolved)

INSTALLED_APPS = [
    # Django
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    # Local (auto-resolved to correct dotted paths)
    *LOCAL_APPS,
]

# -------------------------------------------------
# Middleware
# -------------------------------------------------
INVENTORY_MW = _resolve_middleware("inventory.middleware", "AuditorReadOnlyMiddleware")
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "cc.middleware.RequestIDMiddleware",
    "cc.middleware.AccessLogMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    INVENTORY_MW,
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
# Database
# -------------------------------------------------
DATABASES: dict = {}
ON_HOSTING = bool(RENDER or RENDER_EXTERNAL_URL or LIVE_HOST or APP_DOMAIN)

FORCE_SQLITE = env_bool("FORCE_SQLITE", default=not ON_HOSTING)
if FORCE_SQLITE:
    os.environ.pop("DATABASE_URL", None)
    os.environ["USE_LOCAL_SQLITE"] = "1"

DATABASE_URL = _str_env("DATABASE_URL")
USE_LOCAL_SQLITE = env_bool("USE_LOCAL_SQLITE", default=(DEBUG and not ON_HOSTING))
REQUIRE_DATABASE_URL = env_bool("REQUIRE_DATABASE_URL", ON_HOSTING and (not DEBUG) and (not USE_LOCAL_SQLITE))

if DATABASE_URL:
    try:
        import dj_database_url  # type: ignore
    except Exception as e:
        raise RuntimeError("dj-database-url must be installed to use DATABASE_URL") from e
    DATABASES["default"] = dj_database_url.parse(
        DATABASE_URL,
        conn_max_age=600,
        ssl_require=bool(USE_SSL),
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

# quick visibility in dev
try:
    _db = DATABASES.get("default", {})
    print(f"[cc.settings] DB -> {_db.get('ENGINE')} | NAME={_db.get('NAME')} | DEBUG={DEBUG} | FORCE_SQLITE={FORCE_SQLITE}")
except Exception:
    pass

# -------------------------------------------------
# Cache (Redis if available)
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
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "cc-local-cache", "TIMEOUT": CACHE_TTL_DEFAULT}}

# -------------------------------------------------
# Auth / i18n
# -------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 12}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
PASSWORD_HASHERS = ["django.contrib.auth.hashers.PBKDF2PasswordHasher"]
AUTHENTICATION_BACKENDS = ["django.contrib.auth.backends.ModelBackend"]

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "accounts:login"

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Africa/Blantyre"
USE_I18N = True
USE_TZ = True

# -------------------------------------------------
# Static / Media
# -------------------------------------------------
STATIC_URL = "/static/"
STATICFILES_DIRS = [*(p for p in [BASE_DIR / "static", BASE_DIR / "circuitcity" / "static"] if p.exists())]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

STATIC_VERSION = os.environ.get("STATIC_VERSION", "2025-09-19-1")

DISABLE_MANIFEST = env_bool("DISABLE_MANIFEST", default=(DEBUG or TESTING or ("runserver" in sys.argv and not env_bool("FORCE_PROD_BEHAVIOR", False))))
DISABLE_MANIFEST_IN_PROD = env_bool("DISABLE_MANIFEST_IN_PROD", False)
_use_manifest = not (DISABLE_MANIFEST or DISABLE_MANIFEST_IN_PROD)

_static_backend = "whitenoise.storage.CompressedManifestStaticFilesStorage" if _use_manifest else "django.contrib.staticfiles.storage.StaticFilesStorage"

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": _static_backend},
}
WHITENOISE_AUTOREFRESH = DEBUG
WHITENOISE_MAX_AGE = 60 * 60 * 24 * 7
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
    DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL") or (f"{os.environ.get('APP_NAME', 'Circuit City')} <{EMAIL_HOST_USER}>" if EMAIL_HOST_USER else "noreply@example.com")
    SERVER_EMAIL = os.environ.get("SERVER_EMAIL", DEFAULT_FROM_EMAIL)
    EMAIL_TIMEOUT = env_int("EMAIL_TIMEOUT", 10)

LOW_STOCK_ALERT_RECIPIENTS = [e.strip() for e in os.environ.get("LOW_STOCK_ALERT_RECIPIENTS", os.environ.get("ADMIN_EMAIL", "")).split(",") if e.strip()]

# -------------------------------------------------
# Logging (with IMEI redaction)
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
# Misc feature flags
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
# App metadata & accounts knobs
# -------------------------------------------------
APP_NAME = os.environ.get("APP_NAME", "Circuit City")
APP_ENV = os.environ.get("APP_ENV", "dev" if DEBUG else "beta")
BETA_FEEDBACK_MAILTO = os.environ.get("BETA_FEEDBACK_MAILTO", "beta@circuitcity.example")

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
