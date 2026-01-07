"""
Management command to seed clothing jersey products for football teams.
Idempotent - can be run multiple times without creating duplicates.

Usage:
    python manage.py seed_clothing_jerseys
    python manage.py seed_clothing_jerseys --business-id=1
"""
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.db import transaction, models
from tenants.models import Business
from inventory.models import MerchProduct
from inventory.models_verticals import ClothingVariant, ClothingProductLog, ClothingProductAction
from inventory.business_kinds import BusinessKind


# Jersey data structure: (team_name, league, season)
JERSEY_TEAMS = [
    # EPL (English Premier League)
    ("Chelsea FC", "EPL", "2024/25"),
    ("Manchester United", "EPL", "2024/25"),
    ("Liverpool FC", "EPL", "2024/25"),
    ("Arsenal FC", "EPL", "2024/25"),
    ("Manchester City", "EPL", "2024/25"),
    # LaLiga (Spanish)
    ("Real Madrid", "LaLiga", "2024/25"),
    ("FC Barcelona", "LaLiga", "2024/25"),
    # Bundesliga (German)
    ("Bayern Munich", "Bundesliga", "2024/25"),
    ("Borussia Dortmund", "Bundesliga", "2024/25"),
    # Additional popular teams
    ("Tottenham Hotspur", "EPL", "2024/25"),
    ("Newcastle United", "EPL", "2024/25"),
    ("Atlético Madrid", "LaLiga", "2024/25"),
    ("AC Milan", "Serie A", "2024/25"),
    ("Paris Saint-Germain", "Ligue 1", "2024/25"),
    ("Inter Milan", "Serie A", "2024/25"),
]

# Kit types with colors
KIT_TYPES = [
    ("Home", ["Red", "Blue", "White", "Black", "Navy"]),
    ("Away", ["White", "Black", "Grey", "Yellow", "Green"]),
    ("Third", ["Orange", "Purple", "Pink", "Multi", "Other"]),
]

# Jersey sizes
JERSEY_SIZES = ["S", "M", "L", "XL"]

# Price ranges (in MWK - Malawian Kwacha)
PRICE_RANGES = {
    "order_price": (Decimal("25000"), Decimal("35000")),  # Cost price
    "selling_price": (Decimal("45000"), Decimal("65000")),  # Retail price
}


class Command(BaseCommand):
    help = "Seed clothing jersey products for popular football teams (EPL, LaLiga, Bundesliga, etc.)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--business-id",
            type=int,
            help="Specific business ID to seed jerseys for (optional, seeds for all clothing businesses if not provided)",
        )
        parser.add_argument(
            "--dry-run", action="store_true", help="Preview what would be created without actually creating it"
        )

    def handle(self, *args, **options):
        business_id = options.get("business_id")
        dry_run = options.get("dry_run", False)

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN MODE - No data will be created"))

        # Get target businesses
        if business_id:
            businesses = Business.objects.filter(id=business_id, business_kind=BusinessKind.CLOTHING)
            if not businesses.exists():
                self.stdout.write(
                    self.style.ERROR(f"Business with ID {business_id} not found or not a CLOTHING business")
                )
                return
        else:
            businesses = Business.objects.filter(business_kind=BusinessKind.CLOTHING)

        if not businesses.exists():
            self.stdout.write(self.style.ERROR("No CLOTHING businesses found"))
            return

        self.stdout.write(f"Found {businesses.count()} clothing business(es)")

        total_created = 0
        total_skipped = 0

        for business in businesses:
            self.stdout.write(f"\n{'='*60}")
            self.stdout.write(f"Processing business: {business.name} (ID: {business.id})")
            self.stdout.write(f"{'='*60}")

            created, skipped = self._seed_jerseys_for_business(business, dry_run)
            total_created += created
            total_skipped += skipped

        self.stdout.write(f"\n{'='*60}")
        if dry_run:
            self.stdout.write(
                self.style.SUCCESS(
                    f"DRY RUN COMPLETE: Would create {total_created} products, skip {total_skipped} existing"
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"SEEDING COMPLETE: Created {total_created} products, skipped {total_skipped} existing"
                )
            )
        self.stdout.write(f"{'='*60}\n")

    def _seed_jerseys_for_business(self, business, dry_run=False):
        """Seed jerseys for a single business"""
        import random

        created_count = 0
        skipped_count = 0

        for team_name, league, season in JERSEY_TEAMS:
            for kit_type, possible_colors in KIT_TYPES:
                # Pick a primary color for this kit
                primary_color = random.choice(possible_colors)

                # Create product name
                product_name = f"{team_name} {season} {kit_type} Jersey"

                # Check if product already exists (idempotent)
                existing = MerchProduct.objects.filter(
                    business=business, name__iexact=product_name, vertical="clothing"
                ).exists()

                if existing:
                    skipped_count += 1
                    self.stdout.write(self.style.WARNING(f"  ⊘ SKIP: {product_name} (already exists)"))
                    continue

                if dry_run:
                    created_count += 1
                    self.stdout.write(self.style.SUCCESS(f"  ✓ WOULD CREATE: {product_name}"))
                    continue

                # Generate random prices within range
                order_price = Decimal(
                    random.randint(int(PRICE_RANGES["order_price"][0]), int(PRICE_RANGES["order_price"][1]))
                )
                selling_price = Decimal(
                    random.randint(int(PRICE_RANGES["selling_price"][0]), int(PRICE_RANGES["selling_price"][1]))
                )

                # Create product with transaction
                with transaction.atomic():
                    # Create base product
                    product = MerchProduct.objects.create(
                        business=business,
                        name=product_name,
                        brand=team_name,
                        category="jersey",
                        vertical="clothing",
                        order_price=order_price,
                        selling_price=selling_price,
                        quantity=0,  # Will be set via variants
                        is_active=True,
                    )

                    # Create variants for each size
                    for size in JERSEY_SIZES:
                        # Random quantity per variant
                        quantity = random.randint(5, 15)

                        variant = ClothingVariant.objects.create(
                            product=product,
                            size=size,
                            color=primary_color,
                            quantity=quantity,
                            order_price=order_price,
                            selling_price=selling_price,
                        )

                    # Update product total quantity
                    total_quantity = (
                        ClothingVariant.objects.filter(product=product).aggregate(total=models.Sum("quantity"))["total"]
                        or 0
                    )
                    product.quantity = total_quantity
                    product.save(update_fields=["quantity"])

                    # Log creation
                    try:
                        from django.contrib.auth import get_user_model

                        User = get_user_model()
                        system_user = User.objects.filter(is_superuser=True).first()

                        ClothingProductLog.objects.create(
                            product=product,
                            action=ClothingProductAction.CREATED,
                            changes={
                                "name": product_name,
                                "category": "jersey",
                                "team": team_name,
                                "league": league,
                                "season": season,
                                "kit_type": kit_type,
                                "variants_created": len(JERSEY_SIZES),
                                "initial_stock": total_quantity,
                            },
                            performed_by=system_user,
                        )
                    except Exception:
                        # Log creation is optional, don't fail seeding if it errors
                        pass

                    created_count += 1
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"  ✓ CREATED: {product_name} "
                            f"({len(JERSEY_SIZES)} sizes, {total_quantity} units, "
                            f"K{selling_price:.0f})"
                        )
                    )

        return created_count, skipped_count
