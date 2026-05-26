from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from accounts.utils import assign_role


class Command(BaseCommand):
    help = "Create or update TengaSale development users."

    USERS = [
        {
            "username": "merchant1",
            "role": "merchant",
            "is_staff": False,
            "is_superuser": False,
        },
        {
            "username": "underwriter1",
            "role": "underwriter",
            "is_staff": False,
            "is_superuser": False,
        },
        {
            "username": "hq1",
            "role": "hq",
            "is_staff": True,
            "is_superuser": False,
        },
        {
            "username": "admin1",
            "role": "hq",
            "is_staff": True,
            "is_superuser": True,
        },
    ]

    def handle(self, *args, **options):
        User = get_user_model()

        for user_data in self.USERS:
            username = user_data["username"]
            user, _ = User.objects.get_or_create(username=username)
            user.set_password("Testpass123!")
            user.is_active = True
            user.is_staff = user_data["is_staff"]
            user.is_superuser = user_data["is_superuser"]
            user.save()
            assign_role(user, user_data["role"])

        self.stdout.write(self.style.SUCCESS("Seeded TengaSale users: merchant1, underwriter1, hq1, admin1."))
