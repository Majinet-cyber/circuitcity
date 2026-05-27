# config/settings_production.py  <-- adjust "config" to your project package (folder that has settings.py)
from .settings import *  # keep EVERYTHING from your base settings
import os
import dj_database_url

DEBUG = False

# Secrets / hosts
SECRET_KEY = os.environ.get("SECRET_KEY", "unsafe-default-change-me")
ALLOWED_HOSTS = [
    h.strip() for h in os.environ.get("ALLOWED_HOSTS", ".onrender.com,localhost,127.0.0.1").split(",") if h.strip()
]

# CSRF requires scheme; include your Render URL(s)
# Example: https://your-service.onrender.com
_render_host = os.environ.get("RENDER_EXTERNAL_HOSTNAME")
_csrf_hosts = {f"https://{_render_host}"} if _render_host else set()
_csrf_hosts.update({f"https://{h}" for h in ALLOWED_HOSTS if h and not h.startswith("http")})
CSRF_TRUSTED_ORIGINS = sorted(_csrf_hosts | {"https://*.onrender.com"})

# DB (Render gives DATABASE_URL); SSL & pooling
DATABASES = {"default": dj_database_url.config(conn_max_age=600, ssl_require=True)}

# Static files via WhiteNoise (no code changes needed)
STATIC_URL = "/static/"
STATIC_ROOT = os.path.join(BASE_DIR, "staticfiles")
# NOTE: Static storage is configured in settings.py using STORAGES (Django 4.2+ API)
# STATICFILES_STORAGE is deprecated. The base settings.py uses:
# STORAGES = {"staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"}}

# WhiteNoise safety: Don't hard-fail on missing static files in manifest
# This prevents 500 errors from missing brand icons or other static files
# during rolling deploys or when static files are added/removed.
# Note: The brand_icon template tag also provides an additional safety layer
# by checking file existence before calling .url()
WHITENOISE_MANIFEST_STRICT = False

# Insert WhiteNoise middleware right after SecurityMiddleware if not already there
if "whitenoise.middleware.WhiteNoiseMiddleware" not in MIDDLEWARE:
    try:
        idx = MIDDLEWARE.index("django.middleware.security.SecurityMiddleware") + 1
    except ValueError:
        idx = 0
    MIDDLEWARE.insert(idx, "whitenoise.middleware.WhiteNoiseMiddleware")

# Render runs behind a proxy - CRITICAL for preventing redirect loops
# These settings are already in base settings.py but we ensure they're set here too
# Without these, Django can't detect HTTPS behind the proxy, causing ERR_TOO_MANY_REDIRECTS
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True

# Basic prod logging to console (so Render logs show errors)
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}
