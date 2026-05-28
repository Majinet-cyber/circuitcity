from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from accounts.utils import assign_role


class Command(BaseCommand):
    help = "Create or update TengaSale demo users (dev only — do NOT run in production)."

    USERS = [
        {
            "username": "hq_admin",
            "email": "hq@tengasale.africa",
            "first_name": "HQ",
            "last_name": "Admin",
            "role": "hq",
            "is_staff": True,
            "is_superuser": False,
        },
        {
            "username": "merchant_admin",
            "email": "merchantadmin@tengasale.africa",
            "first_name": "Merchant",
            "last_name": "Administrator",
            "role": "merchant_admin",
            "is_staff": False,
            "is_superuser": False,
        },
        {
            "username": "tech_support",
            "email": "techsupport@tengasale.africa",
            "first_name": "Tech",
            "last_name": "Support",
            "role": "tech_support",
            "is_staff": False,
            "is_superuser": False,
        },
        {
            "username": "underwriter1",
            "email": "underwriter@tengasale.africa",
            "first_name": "Demo",
            "last_name": "Underwriter",
            "role": "underwriter",
            "is_staff": False,
            "is_superuser": False,
        },
        {
            "username": "demo_merchant",
            "email": "merchant@tengasale.africa",
            "first_name": "Demo",
            "last_name": "Merchant",
            "role": "merchant",
            "is_staff": False,
            "is_superuser": False,
        },
        # Legacy usernames kept so existing test data/bookmarks still work
        {
            "username": "merchant1",
            "email": "",
            "first_name": "",
            "last_name": "",
            "role": "merchant",
            "is_staff": False,
            "is_superuser": False,
        },
        {
            "username": "hq1",
            "email": "",
            "first_name": "",
            "last_name": "",
            "role": "hq",
            "is_staff": True,
            "is_superuser": False,
        },
        {
            "username": "admin1",
            "email": "",
            "first_name": "",
            "last_name": "",
            "role": "hq",
            "is_staff": True,
            "is_superuser": True,
        },
    ]

    def handle(self, *args, **options):
        User = get_user_model()

        for user_data in self.USERS:
            username = user_data["username"]
            user, created = User.objects.get_or_create(username=username)
            user.set_password("demo12345")
            user.is_active = True
            user.is_staff = user_data["is_staff"]
            user.is_superuser = user_data["is_superuser"]
            if user_data.get("email"):
                user.email = user_data["email"]
            if user_data.get("first_name"):
                user.first_name = user_data["first_name"]
            if user_data.get("last_name"):
                user.last_name = user_data["last_name"]
            user.save()
            assign_role(user, user_data["role"])

        names = ", ".join(u["username"] for u in self.USERS)
        self.stdout.write(self.style.SUCCESS(f"Seeded TengaSale demo users: {names}."))
        self.stdout.write(self.style.WARNING("Password for all demo users: demo12345 — do NOT use in production."))
