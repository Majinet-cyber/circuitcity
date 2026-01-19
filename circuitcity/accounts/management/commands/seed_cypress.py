"""
Seed Cypress E2E Test Users and Businesses

This management command creates deterministic test data for Cypress E2E tests.
It ensures all verticals have a manager user with a business and sample inventory.

Usage:
    python manage.py seed_cypress
    python manage.py seed_cypress --vertical phones
    python manage.py seed_cypress --json  # Output JSON for Cypress
"""
import json
import sys
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.text import slugify

from inventory.models import Location
from tenants.models import Business, Membership

User = get_user_model()


VERTICAL_CONFIGS = {
    "phones": {
        "email": "empire@gmai.com",
        "password": "@Lincoln1863?",
        "business_name": "Empire Phones",
        "business_kind": "phones",
    },
    "pharmacy": {
        "email": "samantha@gmail.com",
        "password": "@Lincoln1863?",
        "business_name": "Samantha Pharmacy",
        "business_kind": "pharmacy",
    },
    "liquor": {
        "email": "nimue@gmail.com",
        "password": "@Lincoln1863?",
        "business_name": "Nimue Bar",
        "business_kind": "liquor",
    },
    "gym": {
        "email": "yuji@gmail.com",
        "password": "@Lincoln1863?",
        "business_name": "Yuji Fitness",
        "business_kind": "gym",
    },
    "clothing": {
        "email": "motouch@gmail.com",
        "password": "@Lincoln1863?",
        "business_name": "Motouch Clothing",
        "business_kind": "clothing",
    },
    "grocery": {
        "email": "grocery@test.circuitcity.local",
        "password": "@Lincoln1863?",
        "business_name": "Test Grocery",
        "business_kind": "grocery",
    },
    "farm": {
        "email": "farm@test.circuitcity.local",
        "password": "@Lincoln1863?",
        "business_name": "Test Farm",
        "business_kind": "farm",
    },
    "cement": {
        "email": "cement@test.circuitcity.local",
        "password": "@Lincoln1863?",
        "business_name": "Test Cement",
        "business_kind": "cement",
    },
    "welding": {
        "email": "welding@test.circuitcity.local",
        "password": "@Lincoln1863?",
        "business_name": "Test Welding",
        "business_kind": "welding",
    },
    "hardware": {
        "email": "hardware@test.circuitcity.local",
        "password": "@Lincoln1863?",
        "business_name": "Test Hardware",
        "business_kind": "hardware",
    },
}


def get_or_create_business_ci(*, name: str, defaults: dict):
    """Get or create Business with case-insensitive name lookup."""
    b = Business.objects.filter(name__iexact=name).first()
    if b:
        return b, False

    from django.db import IntegrityError

    try:
        return Business.objects.create(name=name, **defaults), True
    except IntegrityError:
        b = Business.objects.filter(name__iexact=name).first()
        if b:
            return b, False
        raise


def seed_phone_sample_data(business, location):
    """Seed sample phone inventory for dashboard data."""
    try:
        from inventory.models import Phone, PhoneSold
        from django.utils import timezone
        from datetime import timedelta

        # Create 2 in-stock phones
        phone1, _ = Phone.objects.get_or_create(
            business=business,
            imei="111111111111111",
            defaults={
                "brand": "Samsung",
                "model": "Galaxy A50",
                "storage": "64GB",
                "ram": "4GB",
                "color": "Black",
                "condition": "new",
                "cost": Decimal("150000"),
                "price": Decimal("200000"),
                "location": location,
            },
        )

        phone2, _ = Phone.objects.get_or_create(
            business=business,
            imei="222222222222222",
            defaults={
                "brand": "Apple",
                "model": "iPhone 12",
                "storage": "128GB",
                "ram": "4GB",
                "color": "Blue",
                "condition": "new",
                "cost": Decimal("500000"),
                "price": Decimal("650000"),
                "location": location,
            },
        )

        # Create 1 sold phone (for dashboard trends)
        sold, _ = PhoneSold.objects.get_or_create(
            business=business,
            imei="333333333333333",
            defaults={
                "brand": "Samsung",
                "model": "Galaxy S21",
                "storage": "256GB",
                "ram": "8GB",
                "color": "White",
                "condition": "new",
                "cost": Decimal("300000"),
                "price": Decimal("400000"),
                "location": location,
                "sold_at": timezone.now() - timedelta(days=1),
            },
        )

        return {"phones_created": 2, "phones_sold": 1}
    except Exception as e:
        return {"error": str(e)}


def seed_generic_sample_data(business, location, vertical_key):
    """Seed sample inventory for non-phone verticals."""
    try:
        from inventory.models import GenericProduct
        from django.utils import timezone

        product, _ = GenericProduct.objects.get_or_create(
            business=business,
            sku=f"E2E-{vertical_key.upper()}-001",
            defaults={
                "name": f"E2E Test {vertical_key.title()} Product",
                "category": "test",
                "quantity": 10,
                "cost": Decimal("1000"),
                "price": Decimal("1500"),
                "location": location,
            },
        )

        return {"products_created": 1}
    except Exception as e:
        return {"error": str(e)}


class Command(BaseCommand):
    help = "Seed Cypress E2E test users and businesses"

    def add_arguments(self, parser):
        parser.add_argument(
            "--vertical",
            type=str,
            help="Seed only this vertical (phones, clothing, etc.)",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            help="Output JSON for Cypress task",
        )

    def handle(self, *args, **options):
        vertical_filter = options.get("vertical")
        output_json = options.get("json")

        if vertical_filter and vertical_filter not in VERTICAL_CONFIGS:
            self.stderr.write(
                self.style.ERROR(
                    f"Unknown vertical: {vertical_filter}. Valid options: {', '.join(VERTICAL_CONFIGS.keys())}"
                )
            )
            sys.exit(1)

        results = []
        verticals_to_seed = [vertical_filter] if vertical_filter else VERTICAL_CONFIGS.keys()

        for vertical_key in verticals_to_seed:
            config = VERTICAL_CONFIGS[vertical_key]
            result = self.seed_vertical(vertical_key, config, output_json)
            results.append(result)

            if not output_json:
                if result.get("success"):
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"[OK] {vertical_key}: user_id={result['user_id']}, business_id={result['business_id']}"
                        )
                    )
                else:
                    self.stdout.write(self.style.ERROR(f"[FAIL] {vertical_key}: {result.get('error')}"))

        if output_json:
            # Output JSON for Cypress task
            output = {"verticals": {r["vertical"]: r for r in results if r.get("success")}}
            self.stdout.write(json.dumps(output, indent=2))

    def seed_vertical(self, vertical_key, config, silent=False):
        """Seed one vertical with user, business, and sample data."""
        try:
            with transaction.atomic():
                email = config["email"]
                password = config["password"]
                business_name = config["business_name"]
                business_kind = config["business_kind"]

                # Get or create user
                user, user_created = User.objects.get_or_create(
                    username=email,
                    defaults={
                        "email": email,
                        "is_active": True,
                        "first_name": vertical_key.title(),
                        "last_name": "Manager",
                    },
                )

                if user_created or not user.has_usable_password():
                    user.set_password(password)
                    user.save()

                # Get or create business
                base_slug = slugify(business_name)[:40] or f"test-{vertical_key}"
                unique_slug = base_slug
                i = 1
                while Business.objects.filter(slug=unique_slug).exclude(name__iexact=business_name).exists():
                    unique_slug = f"{base_slug}-{i}"
                    i += 1

                business, biz_created = get_or_create_business_ci(
                    name=business_name,
                    defaults={
                        "slug": unique_slug,
                        "business_kind": business_kind,
                        "status": "ACTIVE",
                        "created_by": user,
                    },
                )

                # Create or update membership
                membership, mem_created = Membership.objects.get_or_create(
                    user=user,
                    business=business,
                    defaults={
                        "role": "MANAGER",
                        "status": "ACTIVE",
                    },
                )

                # Ensure membership is active
                if not mem_created and membership.status != "ACTIVE":
                    membership.status = "ACTIVE"
                    membership.save(update_fields=["status"])

                # Get or create default location
                location, loc_created = Location.objects.get_or_create(
                    business=business,
                    name="Main Location",
                    defaults={
                        "city": "Test City",
                        "is_default": True,
                    },
                )

                # Seed sample data for dashboard
                sample_data = {}
                if vertical_key == "phones":
                    sample_data = seed_phone_sample_data(business, location)
                else:
                    sample_data = seed_generic_sample_data(business, location, vertical_key)

                return {
                    "success": True,
                    "vertical": vertical_key,
                    "user_id": user.id,
                    "email": user.email,
                    "business_id": business.id,
                    "business_name": business.name,
                    "location_id": location.id,
                    "created": {
                        "user": user_created,
                        "business": biz_created,
                        "membership": mem_created,
                        "location": loc_created,
                    },
                    "sample_data": sample_data,
                }

        except Exception as e:
            return {
                "success": False,
                "vertical": vertical_key,
                "error": str(e),
            }

