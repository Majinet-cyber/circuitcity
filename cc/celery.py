# cc/celery.py
from __future__ import annotations

import os
from celery import Celery

# Point Celery at Django settings
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cc.settings")

# Create Celery app
app = Celery("cc")

# Load any CELERY_* settings from Django
app.config_from_object("django.conf:settings", namespace="CELERY")

# Auto-discover tasks.py in installed apps
app.autodiscover_tasks()


@app.task(bind=True)
def debug_task(self):
    print(f"Request: {self.request!r}")
