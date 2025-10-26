# scripts/create_superuser.py
import os, django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cc.settings")  # change if your settings module is not cc.settings
django.setup()

from django.contrib.auth import get_user_model
User = get_user_model()

u = os.getenv("DJANGO_SUPERUSER_USERNAME")
p = os.getenv("DJANGO_SUPERUSER_PASSWORD")
e = os.getenv("DJANGO_SUPERUSER_EMAIL", "")

if u and p:
    if not User.objects.filter(username=u).exists():
        User.objects.create_superuser(u, e, p)
        print(f"Created superuser {u}")
    else:
        print(f"Superuser {u} already exists; skipping")
else:
    print("DJANGO_SUPERUSER_USERNAME/PASSWORD not set; skipping")


