import os
from pathlib import Path

# Load .env file before Django settings
try:
    from dotenv import load_dotenv

    BASE_DIR = Path(__file__).resolve().parent.parent
    load_dotenv(BASE_DIR / ".env")
except Exception:
    pass  # python-dotenv not installed or .env not found

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cc.settings")

from django.core.wsgi import get_wsgi_application

application = get_wsgi_application()
