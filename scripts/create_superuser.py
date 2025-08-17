# scripts/create_superuser.py
import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "cc.settings")  # keep if your project module is 'cc'
django.setup()

from django.contrib.auth import get_user_model
User = get_user_model()

username = os.getenv("DJANGO_SUPERUSER_USERNAME")
password = os.getenv("DJANGO_SUPERUSER_PASSWORD")
email    = os.getenv("DJANGO_SUPERUSER_EMAIL", "")

if username and password:
    if not User.objects.filter(username=username).exists():
        User.objects.create_superuser(username, email, password)
        print(f"Created superuser {username}")
    else:
        print(f"Superuser {username} already exists; skipping")
else:
    print("DJANGO_SUPERUSER_USERNAME/PASSWORD not set; skipping")
