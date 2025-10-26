from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
import os

class Command(BaseCommand):
    help = "Create/update a superuser from env vars."

    def handle(self, *args, **kwargs):
        User = get_user_model()
        username = os.getenv("DJANGO_SUPERUSER_USERNAME", "admin")
        email = os.getenv("DJANGO_SUPERUSER_EMAIL", "admin@example.com")
        pw = os.getenv("DJANGO_SUPERUSER_PASSWORD", "changeme")

        u, _ = User.objects.get_or_create(
            username=username,
            defaults={"email": email, "is_staff": True, "is_superuser": True},
        )
        u.email = email
        u.is_staff = True
        u.is_superuser = True
        u.set_password(pw)
        u.save()
        self.stdout.write("ensure_superuser: OK")


