"""
Management command to seed default gamification badges.
"""
from django.core.management.base import BaseCommand
from inventory.services_gamification import seed_badges


class Command(BaseCommand):
    help = "Seed default gamification badges"

    def handle(self, *args, **options):
        self.stdout.write("Seeding badges...")
        count = seed_badges()
        self.stdout.write(self.style.SUCCESS(f"✅ Created {count} new badges"))
