from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Create TengaSale role groups."

    def handle(self, *args, **options):
        for group_name in ["Merchant", "Underwriter", "HQ"]:
            Group.objects.get_or_create(name=group_name)

        self.stdout.write(self.style.SUCCESS("Seeded TengaSale roles: Merchant, Underwriter, HQ."))
