from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from accounts.models import UserProfile


class Command(BaseCommand):
    help = "Ensure existing users have TengaSale profiles and staff/superusers default to HQ."

    def handle(self, *args, **options):
        User = get_user_model()
        created_count = 0
        hq_count = 0

        for user in User.objects.all():
            profile, created = UserProfile.objects.get_or_create(user=user)
            if created:
                created_count += 1
            if (user.is_superuser or user.is_staff) and not profile.role:
                profile.role = UserProfile.ROLE_HQ
                profile.save(update_fields=["role"])
                hq_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded TengaSale roles: {created_count} profiles created, {hq_count} staff/superusers set to HQ."
            )
        )
