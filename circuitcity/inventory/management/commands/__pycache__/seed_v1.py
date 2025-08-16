# inventory/management/commands/seed_v1.py
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import transaction
from inventory.models import Location, Product

class Command(BaseCommand):
    help = "Seed V1 demo data: groups, 3 locations, 5 products, 10 agents"

    @transaction.atomic
    def handle(self, *args, **opts):
        User = get_user_model()

        # Groups
        admin_g, _ = Group.objects.get_or_create(name="Admin")
        agent_g, _ = Group.objects.get_or_create(name="Agent")
        audit_g, _ = Group.objects.get_or_create(name="Auditor")

        # Locations
        locs = ["Downtown", "Mall Kiosk", "Airport Stand"]
        for name in locs:
            Location.objects.get_or_create(name=name)

        # Products
        prods = [
            ("Tecno", "Spark 20", "64GB"),
            ("Itel", "P40+", "128GB"),
            ("Infinix", "Hot 40", "8/128"),
            ("Samsung", "A15", "4/128"),
            ("Nokia", "C32", "64GB"),
        ]
        for b, m, v in prods:
            Product.objects.get_or_create(brand=b, model=m, variant=v)

        # Admin user (if none exists)
        if not User.objects.filter(is_superuser=True).exists():
            admin = User.objects.create_user(username="admin", email="admin@example.com")
            admin.set_password("admin123")
            admin.is_staff = True
            admin.is_superuser = True
            admin.save()
            admin.groups.add(admin_g)
            self.stdout.write(self.style.SUCCESS("Created superuser admin / admin123"))

        # 10 agents
        for i in range(1, 11):
            uname = f"agent{i:02d}"
            if not User.objects.filter(username=uname).exists():
                u = User.objects.create_user(username=uname, email=f"{uname}@example.com")
                u.set_password("agent123")
                u.is_staff = False
                u.save()
                u.groups.add(agent_g)
        self.stdout.write(self.style.SUCCESS("Seeded: groups, locations, products, agents"))
