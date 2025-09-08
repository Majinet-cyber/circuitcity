import os
from django.conf import settings

def globals(request):
    return {
        "APP_NAME": getattr(settings, "APP_NAME", "Circuit City"),
        "APP_ENV": getattr(settings, "APP_ENV", "dev"),
        "STATIC_VERSION": getattr(settings, "STATIC_VERSION", "dev"),
    }
