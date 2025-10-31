"""
Django settings for cc project.
"""
from pathlib import Path
from urllib.parse import urlparse
import os
import sys
import importlib

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
            out.append(f"https://*{h}")  # wildcard subdomains like .onrender.com
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
DEBUG = env_bool("DEBUG", IS_RUNSERVER)
TESTING = any(arg in sys.argv for arg in ("test", "pytest"))
ON_RENDER = env_bool("RENDER", False) or ("RENDER" in os.environ)

# Allow from env first, else sane defaults (Render host, localhost, etc.)
ALLOWED_HOSTS = env_csv(
    "ALLOWED_HOSTS",
    "emajinet.africa,www.emajinet.africa,localhost,127.0.0.1,0.0.0.0,.onrender.com",
)
if ON_RENDER and ".onrender.com" not in ALLOWED_HOSTS and "*.onrender.com" not in ALLOWED_HOSTS:
    ALLOWED_HOSTS = list({*ALLOWED_HOSTS, ".onrender.com"})
if IS_RUNSERVER and "*" not in ALLOWED_HOSTS:
    ALLOWED_HOSTS = list({*ALLOWED_HOSTS, "localhost", "127.0.0.1", "0.0.0.0"})

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
]
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

# Behind a proxy (Render/NGINX)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True

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

# --------------------------- session & csrf ---------------------------
SESSION_COOKIE_NAME = os.environ.get("SESSION_COOKIE_NAME", "cc_sessionid")
CSRF_COOKIE_NAME = os.environ.get("CSRF_COOKIE_NAME", "cc_csrftoken")
CSRF_COOKIE_HTTPONLY = True
SESSION_COOKIE_HTTPONLY = True
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_COOKIE_SAMESITE = os.environ.get("SESSION_COOKIE_SAMESITE", "Lax")
CSRF_COOKIE_SAMESITE = os.environ.get("CSRF_COOKIE_SAMESITE", "Lax")
SESSION_COOKIE_AGE = 60 * 60 * 4

# Use cached DB sessions to reduce DB roundtrips and survive brief DB blips.
SESSION_ENGINE = "django.contrib.sessions.backends.cached_db"
SESSION_SAVE_EVERY_REQUEST = False

# Canonical session key for active tenant (used by middleware/utils)
TENANT_SESSION_KEY = os.environ.get("TENANT_SESSION_KEY", "active_business_id")

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
    "inventory",
    "sales",
    "dashboard",
    "simulator",
    # Billing
    "billing",
    "wallet",
    # Layby (TOP-LEVEL import, not circuitcity.layby)
    "layby.apps.LaybyConfig",
]

# Optional dev/helper apps
INSTALLED_APPS += [a for a in (
    _optional_app("sslserver"),
    _optional_app("django_extensions"),
) if a]

print("[cc.settings] Final INSTALLED_APPS:", INSTALLED_APPS)

# --------------------------- middleware ---------------------------
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
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

    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]
print("[cc.settings] Final MIDDLEWARE:", MIDDLEWARE)
print(f"[cc.settings] SSL flags → DEBUG={DEBUG} RUNSERVER={IS_RUNSERVER} "
      f"SECURE_SSL_REDIRECT={SECURE_SSL_REDIRECT} SESSION_COOKIE_SECURE={SESSION_COOKIE_SECURE} CSRF_COOKIE_SECURE={CSRF_COOKIE_SECURE}")

ROOT_URLCONF = "cc.urls"

# --------------------------- templates ---------------------------
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [
            *(p for p in [BASE_DIR / "templates", BASE_DIR / "circuitcity" / "templates"] if p.exists())
        ],
        "APP_DIRS": True,
        "OPTIONS": {
            "debug": DEBUG,
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "cc.context_processors.build_meta",
                "cc.context_processors.role_flags",
                "cc.context_processors.brand",
                "tenants.context_processors.tenant_context",
                "billing.context_processors.trial_banner",
            ],
        },
    },
]
SILENCED_SYSTEM_CHECKS = ["templates.E003"]

WSGI_APPLICATION = "cc.wsgi.application"

# --------------------------- database ---------------------------
DATABASES: dict = {}
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()

USE_LOCAL_SQLITE = env_bool("USE_LOCAL_SQLITE", default=not bool(DATABASE_URL))
REQUIRE_DATABASE_URL = env_bool("REQUIRE_DATABASE_URL", False)
PGCONNECT_TIMEOUT = env_int("PGCONNECT_TIMEOUT", 5)

# Keep DB connections warm & resilient (Render Postgres can drop idle ones)
DB_CONN_MAX_AGE = env_int("DB_CONN_MAX_AGE", 300)  # seconds

if TESTING:
    DATABASES["default"] = {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
elif DATABASE_URL:
    try:
        import dj_database_url  # type: ignore
    except Exception as e:
        raise RuntimeError("dj-database-url must be installed") from e

    # TLS for Render/prod
    cfg = dj_database_url.parse(
        DATABASE_URL,
        conn_max_age=DB_CONN_MAX_AGE,
        ssl_require=not DEBUG,
    )
    # Enable health checks so Django pings before using a possibly-stale connection.
    cfg["CONN_MAX_AGE"] = DB_CONN_MAX_AGE
    cfg["CONN_HEALTH_CHECKS"] = True

    opts = dict(cfg.get("OPTIONS") or {})
    opts.setdefault("connect_timeout", PGCONNECT_TIMEOUT)
    # If DATABASE_URL doesn’t include sslmode, enforce it in prod.
    if not DEBUG:
        opts.setdefault("sslmode", "require")
    cfg["OPTIONS"] = opts
    DATABASES["default"] = cfg
elif USE_LOCAL_SQLITE:
    sqlite_path = str(BASE_DIR / "db.sqlite3")
    DATABASES["default"] = {"ENGINE": "django.db.backends.sqlite3", "NAME": sqlite_path}
else:
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
        "CONN_MAX_AGE": DB_CONN_MAX_AGE,
        "CONN_HEALTH_CHECKS": True,
        "OPTIONS": {"connect_timeout": PGCONNECT_TIMEOUT, **({"sslmode": "require"} if not DEBUG else {})},
    }

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
    # keep 12 for now
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 12}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
PASSWORD_HASHERS = ["django.contrib.auth.hashers.PBKDF2PasswordHasher"]
AUTHENTICATION_BACKENDS = ["django.contrib.auth.backends.ModelBackend"]
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Africa/Blantyre"
USE_I18N = True
USE_TZ = True

# --------------------------- static / media ---------------------------
STATIC_URL = "/static/"
STATICFILES_DIRS = [*(p for p in [BASE_DIR / "static", BASE_DIR / "circuitcity" / "static"] if p.exists())]
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

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
WHITENOISE_AUTOREFRESH = DEBUG
WHITENOISE_MAX_AGE = 60 * 60 * 24 * 365
WHITENOISE_INDEX_FILE = False

# --------------------------- auth redirects ---------------------------
LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/accounts/login/"

# --------------------------- email ---------------------------
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

# --------------------------- billing ---------------------------
BILLING = {
    "PROVIDER": os.environ.get("BILLING_PROVIDER", "stripe"),
    "DEFAULT_CURRENCY": os.environ.get("BILLING_CURRENCY", "MWK"),
    "TRIAL_DAYS": env_int("BILLING_TRIAL_DAYS", 30),
    "GRACE_DAYS": env_int("BILLING_GRACE_DAYS", 30),
    "INVOICE_FROM": os.environ.get("BILLING_INVOICE_FROM", os.environ.get("DEFAULT_FROM_EMAIL", "noreply@example.com")),
}
BILLING_PLANS = {
    "starter": {"code": "starter", "name": "Starter", "amount": 20000, "currency": "MWK", "max_agents": 0, "max_stores": 1},
    "growth": {"code": "growth", "name": "Growth", "amount": 60000, "currency": "MWK", "max_agents": 5, "max_stores": 5},
    "pro": {"code": "pro", "name": "Pro", "amount": 120000, "currency": "MWK", "max_agents": None, "max_stores": None},
}

REPORTS_DEFAULT_CURRENCY = BILLING["DEFAULT_CURRENCY"]
BILLING_TRIAL_DAYS = BILLING["TRIAL_DAYS"]
BILLING_GRACE_DAYS = BILLING["GRACE_DAYS"]

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

APP_NAME = os.environ.get("APP_NAME", "Circuit City")
APP_ENV = os.environ.get("APP_ENV", "dev" if DEBUG else "beta")
BETA_FEEDBACK_MAILTO = os.environ.get("BETA_FEEDBACK_MAILTO", "beta@circuitcity.example")

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
        "django.template": {"handlers": ["console"], "level": "DEBUG" if DEBUG else "INFO", "propagate": True},
    },
}

# --------------------------- feature flags for templates (optional) ---------------------------
CC_SHOW_ADMIN_TIP = env_bool("CC_SHOW_ADMIN_TIP", False)
CC_PUBLIC_ERROR_PAGE = env_bool("CC_PUBLIC_ERROR_PAGE", True)
