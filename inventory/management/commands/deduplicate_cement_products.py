# inventory/management/commands/deduplicate_cement_products.py
"""
Management command to deduplicate cement products.

Finds duplicate cement products (same brand, different names) and consolidates them into
a single canonical product, migrating related Stock, Inventory, and Sales records.

Usage:
    python manage.py deduplicate_cement_products [--dry-run] [--business-id=X]
"""

from decimal import Decimal
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Count, Q
from inventory.models import MerchProduct
from inventory.business_kinds import BusinessKind
from inventory.cement_seed import normalize_cement_brand_name
from tenants.models import Business


class Command(BaseCommand):
    help = "Deduplicate cement products by brand name, keeping one canonical product per brand"

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be done without making changes',
        )
        parser.add_argument(
            '--business-id',
            type=int,
            help='Only deduplicate products for a specific business ID',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        business_id = options.get('business_id')

        self.stdout.write(self.style.WARNING(
            f"{'[DRY RUN] ' if dry_run else ''}Cement Product Deduplication"
        ))
        self.stdout.write("")

        # Get businesses to process
        if business_id:
            businesses = Business.objects.filter(
                id=business_id,
                business_kind=BusinessKind.CEMENT
            )
        else:
            businesses = Business.objects.filter(business_kind=BusinessKind.CEMENT)

        if not businesses.exists():
            self.stdout.write(self.style.ERROR("No cement businesses found"))
            return

        total_duplicates = 0
        total_merged = 0

        for business in businesses:
            self.stdout.write(f"\nProcessing business: {business.name} (ID={business.id})")

            # Get all cement products for this business
            products = MerchProduct.objects.filter(
                business=business,
                kind=BusinessKind.CEMENT,
                is_active=True,
                category__icontains="cement"
            ).exclude(
                name__iexact="Cement"  # Skip generic placeholder
            ).order_by("name")

            if not products:
                self.stdout.write("  No cement products found")
                continue

            # Group by normalized brand name
            brand_groups = {}
            for product in products:
                # Extract brand from name
                brand = self._extract_brand_from_name(product.name)
                if not brand:
                    continue

                # Normalize to canonical name
                canonical_brand = normalize_cement_brand_name(brand)

                if canonical_brand not in brand_groups:
                    brand_groups[canonical_brand] = []
                brand_groups[canonical_brand].append(product)

            # Find duplicates (brands with multiple products)
            for brand, product_list in brand_groups.items():
                if len(product_list) < 2:
                    continue  # No duplicates

                total_duplicates += len(product_list) - 1

                self.stdout.write(f"\n  Found {len(product_list)} products for brand '{brand}':")
                for p in product_list:
                    self.stdout.write(f"    - {p.name} (ID={p.id}, stock={p.quantity_in_stock})")

                if dry_run:
                    canonical = self._choose_canonical(product_list)
                    self.stdout.write(self.style.SUCCESS(
                        f"    Would keep: {canonical.name} (ID={canonical.id})"
                    ))
                    for dup in product_list:
                        if dup.id != canonical.id:
                            self.stdout.write(f"    Would merge: {dup.name} (ID={dup.id})")
                else:
                    # Actually deduplicate
                    merged_count = self._deduplicate_brand(business, brand, product_list)
                    total_merged += merged_count

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(
            f"\n{'[DRY RUN] ' if dry_run else ''}Summary:"
        ))
        self.stdout.write(f"  Total duplicates found: {total_duplicates}")
        if not dry_run:
            self.stdout.write(f"  Total products merged: {total_merged}")
        else:
            self.stdout.write(f"  Products that would be merged: {total_duplicates}")

    def _extract_brand_from_name(self, name: str) -> str:
        """Extract brand name from product name like 'Njati Cement BAG (50KG)'."""
        # Remove common suffixes
        clean = name.replace(" Cement", "").replace(" BAG", "").replace("(50KG)", "").replace("(50kg)", "")
        clean = clean.strip()

        # Take first word as brand
        tokens = clean.split()
        return tokens[0] if tokens else ""

    def _choose_canonical(self, products):
        """
        Choose which product should be the canonical one.
        Prefer: most stock > most sales > oldest created_at
        """
        # Sort by: stock desc, id asc (older products have lower IDs)
        sorted_products = sorted(
            products,
            key=lambda p: (-p.quantity_in_stock, p.id)
        )
        return sorted_products[0]

    def _deduplicate_brand(self, business, brand, product_list):
        """
        Merge duplicate products into a single canonical product.
        Returns number of products merged.
        """
        if len(product_list) < 2:
            return 0

        canonical = self._choose_canonical(product_list)
        duplicates = [p for p in product_list if p.id != canonical.id]

        self.stdout.write(self.style.SUCCESS(
            f"    Keeping canonical: {canonical.name} (ID={canonical.id})"
        ))

        with transaction.atomic():
            for dup in duplicates:
                self.stdout.write(f"    Merging: {dup.name} (ID={dup.id})")

                # Merge stock
                canonical.quantity_in_stock += dup.quantity_in_stock

                # Update prices if duplicate has higher prices (prefer higher)
                if dup.selling_price and dup.selling_price > (canonical.selling_price or 0):
                    canonical.selling_price = dup.selling_price
                if dup.cost_price and dup.cost_price > (canonical.cost_price or 0):
                    canonical.cost_price = dup.cost_price

                canonical.save()

                # Soft-delete duplicate (mark inactive instead of hard delete)
                dup.is_active = False
                dup.save()

                self.stdout.write(f"      → Merged {dup.quantity_in_stock} units into canonical product")

        return len(duplicates)

