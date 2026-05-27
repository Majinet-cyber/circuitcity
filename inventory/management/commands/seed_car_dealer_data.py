# inventory/management/commands/seed_car_dealer_data.py
"""
Management command: populate CarMake and CarModel reference data.

Usage:
    python manage.py seed_car_dealer_data
    python manage.py seed_car_dealer_data --force   (re-seed even if data exists)

This command is idempotent — safe to run multiple times.
"""
from django.core.management.base import BaseCommand


# ---------------------------------------------------------------------------
# Reference data
# ---------------------------------------------------------------------------

CAR_DATA: list[dict] = [
    {
        "make": "Toyota",
        "popular": True,
        "sort_order": 1,
        "models": [
            {"name": "Vitz", "body_type": "hatchback", "common_years": "2005-2022"},
            {"name": "Yaris", "body_type": "hatchback", "common_years": "2020+"},
            {"name": "Corolla", "body_type": "sedan", "common_years": "2000-2022"},
            {"name": "Axio", "body_type": "sedan", "common_years": "2006-2022"},
            {"name": "Premio", "body_type": "sedan", "common_years": "2001-2020"},
            {"name": "Allion", "body_type": "sedan", "common_years": "2001-2021"},
            {"name": "Hilux", "body_type": "pickup", "common_years": "2005-2024"},
            {"name": "Land Cruiser Prado", "body_type": "suv", "common_years": "2000-2023"},
            {"name": "Land Cruiser 200", "body_type": "suv", "common_years": "2008-2021"},
            {"name": "RAV4", "body_type": "suv", "common_years": "2006-2023"},
            {"name": "Harrier", "body_type": "suv", "common_years": "2003-2022"},
            {"name": "Fortuner", "body_type": "suv", "common_years": "2005-2022"},
            {"name": "Wish", "body_type": "minivan", "common_years": "2003-2017"},
            {"name": "Noah", "body_type": "minivan", "common_years": "2001-2022"},
            {"name": "Voxy", "body_type": "minivan", "common_years": "2001-2022"},
            {"name": "Hiace", "body_type": "van", "common_years": "2005-2022"},
            {"name": "Probox", "body_type": "wagon", "common_years": "2002-2022"},
            {"name": "Succeed", "body_type": "wagon", "common_years": "2002-2020"},
            {"name": "Auris", "body_type": "hatchback", "common_years": "2007-2019"},
            {"name": "C-HR", "body_type": "suv", "common_years": "2016+"},
            {"name": "Rush", "body_type": "suv", "common_years": "2006-2021"},
            {"name": "Camry", "body_type": "sedan", "common_years": "2006-2023"},
        ],
    },
    {
        "make": "Mazda",
        "popular": True,
        "sort_order": 2,
        "models": [
            {"name": "Demio", "body_type": "hatchback", "common_years": "2007-2019"},
            {"name": "Mazda2", "body_type": "hatchback", "common_years": "2019+"},
            {"name": "Axela", "body_type": "sedan", "common_years": "2003-2019"},
            {"name": "Mazda3", "body_type": "sedan", "common_years": "2019+"},
            {"name": "CX-5", "body_type": "suv", "common_years": "2012+"},
            {"name": "CX-3", "body_type": "suv", "common_years": "2015+"},
            {"name": "CX-9", "body_type": "suv", "common_years": "2007+"},
            {"name": "BT-50", "body_type": "pickup", "common_years": "2006+"},
            {"name": "Atenza", "body_type": "sedan", "common_years": "2002-2019"},
            {"name": "Mazda6", "body_type": "sedan", "common_years": "2019+"},
        ],
    },
    {
        "make": "Honda",
        "popular": True,
        "sort_order": 3,
        "models": [
            {"name": "Fit", "body_type": "hatchback", "common_years": "2001-2022"},
            {"name": "Jazz", "body_type": "hatchback", "common_years": "2001-2022"},
            {"name": "Vezel", "body_type": "suv", "common_years": "2013-2022"},
            {"name": "HR-V", "body_type": "suv", "common_years": "2022+"},
            {"name": "CR-V", "body_type": "suv", "common_years": "2002-2022"},
            {"name": "Civic", "body_type": "sedan", "common_years": "2006-2022"},
            {"name": "Accord", "body_type": "sedan", "common_years": "2003-2022"},
            {"name": "Freed", "body_type": "minivan", "common_years": "2008-2021"},
            {"name": "Odyssey", "body_type": "minivan", "common_years": "2003-2021"},
        ],
    },
    {
        "make": "Subaru",
        "popular": True,
        "sort_order": 4,
        "models": [
            {"name": "Impreza", "body_type": "sedan", "common_years": "2000-2023"},
            {"name": "Forester", "body_type": "suv", "common_years": "2002-2023"},
            {"name": "XV", "body_type": "suv", "common_years": "2012-2022"},
            {"name": "Crosstrek", "body_type": "suv", "common_years": "2022+"},
            {"name": "Legacy", "body_type": "sedan", "common_years": "2003-2022"},
            {"name": "Outback", "body_type": "wagon", "common_years": "2003-2022"},
        ],
    },
    {
        "make": "Nissan",
        "popular": True,
        "sort_order": 5,
        "models": [
            {"name": "Note", "body_type": "hatchback", "common_years": "2005-2022"},
            {"name": "Tiida", "body_type": "sedan", "common_years": "2004-2013"},
            {"name": "X-Trail", "body_type": "suv", "common_years": "2001-2022"},
            {"name": "Juke", "body_type": "suv", "common_years": "2010-2022"},
            {"name": "Navara", "body_type": "pickup", "common_years": "2005-2022"},
            {"name": "March", "body_type": "hatchback", "common_years": "2003-2022"},
            {"name": "Serena", "body_type": "minivan", "common_years": "2005-2022"},
            {"name": "Patrol", "body_type": "suv", "common_years": "2005-2022"},
        ],
    },
    {
        "make": "Ford",
        "popular": True,
        "sort_order": 6,
        "models": [
            {"name": "Ranger", "body_type": "pickup", "common_years": "2006-2023"},
            {"name": "Everest", "body_type": "suv", "common_years": "2015-2023"},
            {"name": "Focus", "body_type": "hatchback", "common_years": "2005-2019"},
            {"name": "Fiesta", "body_type": "hatchback", "common_years": "2009-2019"},
            {"name": "Explorer", "body_type": "suv", "common_years": "2011-2022"},
        ],
    },
    {
        "make": "Mercedes-Benz",
        "popular": True,
        "sort_order": 7,
        "models": [
            {"name": "C-Class", "body_type": "sedan", "common_years": "2007-2022"},
            {"name": "E-Class", "body_type": "sedan", "common_years": "2007-2022"},
            {"name": "GLE", "body_type": "suv", "common_years": "2015-2022"},
            {"name": "A-Class", "body_type": "hatchback", "common_years": "2012-2022"},
            {"name": "ML-Class", "body_type": "suv", "common_years": "2006-2015"},
            {"name": "GLC", "body_type": "suv", "common_years": "2015+"},
            {"name": "Sprinter", "body_type": "van", "common_years": "2006-2022"},
        ],
    },
    {
        "make": "Volkswagen",
        "popular": True,
        "sort_order": 8,
        "models": [
            {"name": "Polo", "body_type": "hatchback", "common_years": "2009-2022"},
            {"name": "Golf", "body_type": "hatchback", "common_years": "2009-2022"},
            {"name": "Passat", "body_type": "sedan", "common_years": "2005-2022"},
            {"name": "Tiguan", "body_type": "suv", "common_years": "2007-2022"},
            {"name": "Amarok", "body_type": "pickup", "common_years": "2010-2022"},
        ],
    },
    {
        "make": "BMW",
        "popular": True,
        "sort_order": 9,
        "models": [
            {"name": "1 Series", "body_type": "hatchback", "common_years": "2004-2022"},
            {"name": "3 Series", "body_type": "sedan", "common_years": "2005-2022"},
            {"name": "5 Series", "body_type": "sedan", "common_years": "2004-2022"},
            {"name": "X1", "body_type": "suv", "common_years": "2009-2022"},
            {"name": "X3", "body_type": "suv", "common_years": "2003-2022"},
            {"name": "X5", "body_type": "suv", "common_years": "2004-2022"},
        ],
    },
    {
        "make": "Mitsubishi",
        "popular": False,
        "sort_order": 10,
        "models": [
            {"name": "Pajero", "body_type": "suv", "common_years": "2002-2022"},
            {"name": "Outlander", "body_type": "suv", "common_years": "2006-2022"},
            {"name": "ASX", "body_type": "suv", "common_years": "2010-2022"},
            {"name": "L200", "body_type": "pickup", "common_years": "2006-2022"},
            {"name": "Mirage", "body_type": "hatchback", "common_years": "2012-2022"},
        ],
    },
    {
        "make": "Isuzu",
        "popular": False,
        "sort_order": 11,
        "models": [
            {"name": "D-Max", "body_type": "pickup", "common_years": "2004-2022"},
            {"name": "MU-X", "body_type": "suv", "common_years": "2013-2022"},
            {"name": "ELF", "body_type": "van", "common_years": "2006-2022"},
        ],
    },
    {
        "make": "Hyundai",
        "popular": False,
        "sort_order": 12,
        "models": [
            {"name": "i10", "body_type": "hatchback", "common_years": "2007-2022"},
            {"name": "i20", "body_type": "hatchback", "common_years": "2008-2022"},
            {"name": "Tucson", "body_type": "suv", "common_years": "2009-2022"},
            {"name": "Santa Fe", "body_type": "suv", "common_years": "2006-2022"},
        ],
    },
    {
        "make": "Kia",
        "popular": False,
        "sort_order": 13,
        "models": [
            {"name": "Sportage", "body_type": "suv", "common_years": "2010-2022"},
            {"name": "Picanto", "body_type": "hatchback", "common_years": "2007-2022"},
            {"name": "Sorento", "body_type": "suv", "common_years": "2009-2022"},
        ],
    },
]


# ---------------------------------------------------------------------------
# Demo vehicle seed data — realistic starter stock for car dealer businesses
# ---------------------------------------------------------------------------

DEMO_VEHICLES = [
    # Popular affordable hatchbacks / city cars
    {
        "make": "Toyota", "model": "Vitz",
        "year": 2015, "body_type": "hatchback", "transmission": "auto",
        "fuel_type": "petrol", "engine_size": "1.0L", "mileage": 68000,
        "color": "White", "condition": "used", "status": "in_stock",
        "buying_price": "2800000", "selling_price": "3200000",
        "description": "Well maintained Toyota Vitz. Japan import. Service history available.",
    },
    {
        "make": "Honda", "model": "Fit",
        "year": 2017, "body_type": "hatchback", "transmission": "auto",
        "fuel_type": "petrol", "engine_size": "1.3L", "mileage": 52000,
        "color": "Silver", "condition": "used", "status": "in_stock",
        "buying_price": "3500000", "selling_price": "4200000",
        "description": "Clean Honda Fit in excellent condition. Low mileage.",
    },
    {
        "make": "Mazda", "model": "Demio",
        "year": 2016, "body_type": "hatchback", "transmission": "auto",
        "fuel_type": "petrol", "engine_size": "1.3L", "mileage": 74000,
        "color": "Red", "condition": "used", "status": "in_stock",
        "buying_price": "3000000", "selling_price": "3600000",
        "description": "Sporty Mazda Demio. Economical fuel consumption. Great city car.",
    },
    {
        "make": "Nissan", "model": "March",
        "year": 2014, "body_type": "hatchback", "transmission": "auto",
        "fuel_type": "petrol", "engine_size": "1.2L", "mileage": 82000,
        "color": "Blue", "condition": "used", "status": "in_stock",
        "buying_price": "2200000", "selling_price": "2700000",
        "description": "Compact Nissan March. Ideal for students and city commuters.",
    },
    # Sedans
    {
        "make": "Toyota", "model": "Corolla",
        "year": 2018, "body_type": "sedan", "transmission": "auto",
        "fuel_type": "petrol", "engine_size": "1.8L", "mileage": 45000,
        "color": "White", "condition": "used", "status": "in_stock",
        "buying_price": "5500000", "selling_price": "6500000",
        "description": "Toyota Corolla 2018. Full option. Locally registered.",
    },
    {
        "make": "Toyota", "model": "Premio",
        "year": 2016, "body_type": "sedan", "transmission": "auto",
        "fuel_type": "petrol", "engine_size": "1.8L", "mileage": 61000,
        "color": "Silver", "condition": "used", "status": "in_stock",
        "buying_price": "4800000", "selling_price": "5800000",
        "description": "Toyota Premio F package. Elegant family sedan. Clean interior.",
    },
    {
        "make": "Mercedes-Benz", "model": "C-Class",
        "year": 2015, "body_type": "sedan", "transmission": "auto",
        "fuel_type": "petrol", "engine_size": "2.0L", "mileage": 88000,
        "color": "Black", "condition": "used", "status": "in_stock",
        "buying_price": "8500000", "selling_price": "10500000",
        "description": "Mercedes-Benz C200. Executive saloon. Well maintained, full service history.",
    },
    {
        "make": "BMW", "model": "3 Series",
        "year": 2014, "body_type": "sedan", "transmission": "auto",
        "fuel_type": "petrol", "engine_size": "2.0L", "mileage": 96000,
        "color": "White", "condition": "used", "status": "in_stock",
        "buying_price": "7800000", "selling_price": "9500000",
        "description": "BMW 320i F30. Sports luxury sedan. Excellent driving dynamics.",
    },
    # SUVs and crossovers
    {
        "make": "Nissan", "model": "X-Trail",
        "year": 2016, "body_type": "suv", "transmission": "auto",
        "fuel_type": "petrol", "engine_size": "2.0L", "mileage": 72000,
        "color": "Grey", "condition": "used", "status": "in_stock",
        "buying_price": "7000000", "selling_price": "8500000",
        "description": "Nissan X-Trail T32. 7-seater family SUV. Panoramic roof.",
    },
    {
        "make": "Honda", "model": "CR-V",
        "year": 2017, "body_type": "suv", "transmission": "auto",
        "fuel_type": "petrol", "engine_size": "1.5L", "mileage": 58000,
        "color": "White", "condition": "used", "status": "in_stock",
        "buying_price": "8000000", "selling_price": "9800000",
        "description": "Honda CR-V 1.5 Turbo. Spacious and fuel efficient SUV.",
    },
    {
        "make": "Toyota", "model": "RAV4",
        "year": 2018, "body_type": "suv", "transmission": "auto",
        "fuel_type": "petrol", "engine_size": "2.5L", "mileage": 42000,
        "color": "Pearl White", "condition": "used", "status": "in_stock",
        "buying_price": "11000000", "selling_price": "13500000",
        "description": "Toyota RAV4 2018 Adventure edition. Low mileage. Full option.",
    },
    {
        "make": "Subaru", "model": "Forester",
        "year": 2016, "body_type": "suv", "transmission": "auto",
        "fuel_type": "petrol", "engine_size": "2.0L", "mileage": 79000,
        "color": "Black", "condition": "used", "status": "in_stock",
        "buying_price": "7500000", "selling_price": "9000000",
        "description": "Subaru Forester XT. Turbocharged AWD. Excellent for rough terrain.",
    },
    # Pickups / Workhorses
    {
        "make": "Toyota", "model": "Hilux",
        "year": 2019, "body_type": "pickup", "transmission": "manual",
        "fuel_type": "diesel", "engine_size": "2.8L", "mileage": 55000,
        "color": "White", "condition": "used", "status": "in_stock",
        "buying_price": "16000000", "selling_price": "19500000",
        "description": "Toyota Hilux Revo DC 4x4. Workhorse and family pick-up. Very good condition.",
    },
    {
        "make": "Isuzu", "model": "D-Max",
        "year": 2018, "body_type": "pickup", "transmission": "manual",
        "fuel_type": "diesel", "engine_size": "3.0L", "mileage": 67000,
        "color": "Silver", "condition": "used", "status": "in_stock",
        "buying_price": "14000000", "selling_price": "17000000",
        "description": "Isuzu D-Max 4x4. Heavy duty double cab. Excellent towing capacity.",
    },
    {
        "make": "Mazda", "model": "BT-50",
        "year": 2017, "body_type": "pickup", "transmission": "manual",
        "fuel_type": "diesel", "engine_size": "3.2L", "mileage": 88000,
        "color": "Grey", "condition": "used", "status": "in_stock",
        "buying_price": "12000000", "selling_price": "14500000",
        "description": "Mazda BT-50 3.2 4x4. Reliable workhorse. Full service records.",
    },
]


class Command(BaseCommand):
    help = "Seed CarMake, CarModel reference data and optionally seed demo vehicles"

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Re-seed data even if makes/models already exist",
        )
        parser.add_argument(
            "--demo",
            action="store_true",
            help="Also seed demo vehicles into all car_dealer businesses",
        )
        parser.add_argument(
            "--business",
            type=int,
            default=None,
            help="Limit demo vehicle seeding to a specific business ID",
        )

    def handle(self, *args, **options):
        force = options.get("force", False)
        seed_demo = options.get("demo", False)
        business_id = options.get("business")

        try:
            from inventory.models_car_dealer import CarMake, CarModel, CarDealerVehicle
        except ImportError:
            self.stderr.write(
                self.style.ERROR("Car dealer models not available. Run migrations first.")
            )
            return

        # ----------------------------------------------------------------
        # 1. Seed reference data (makes & models)
        # ----------------------------------------------------------------
        created_makes = 0
        created_models = 0
        updated_makes = 0
        updated_models = 0

        for entry in CAR_DATA:
            make_name = entry["make"]
            make_defaults = {
                "sort_order": entry.get("sort_order", 0),
                "is_popular": entry.get("popular", False),
            }

            make_obj, make_created = CarMake.objects.get_or_create(
                name=make_name,
                defaults=make_defaults,
            )

            if not make_created and force:
                for k, v in make_defaults.items():
                    setattr(make_obj, k, v)
                make_obj.save(update_fields=list(make_defaults.keys()))
                updated_makes += 1
            elif make_created:
                created_makes += 1

            for idx, model_entry in enumerate(entry.get("models", [])):
                model_name = model_entry["name"]
                model_defaults = {
                    "body_type": model_entry.get("body_type", ""),
                    "common_years": model_entry.get("common_years", ""),
                    "sort_order": idx,
                }

                model_obj, model_created = CarModel.objects.get_or_create(
                    make=make_obj,
                    name=model_name,
                    defaults=model_defaults,
                )

                if not model_created and force:
                    for k, v in model_defaults.items():
                        setattr(model_obj, k, v)
                    model_obj.save(update_fields=list(model_defaults.keys()))
                    updated_models += 1
                elif model_created:
                    created_models += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Reference data: Created {created_makes} makes, {created_models} models. "
                f"Updated {updated_makes} makes, {updated_models} models."
            )
        )

        if not seed_demo:
            return

        # ----------------------------------------------------------------
        # 2. Seed demo vehicles into car_dealer businesses
        # ----------------------------------------------------------------
        try:
            from tenants.models import Business
        except ImportError:
            self.stderr.write(self.style.ERROR("tenants.models not available."))
            return

        qs = Business.objects.filter(business_kind="car_dealer")
        if business_id:
            qs = qs.filter(pk=business_id)

        if not qs.exists():
            self.stdout.write(
                self.style.WARNING(
                    "No car_dealer businesses found. Signup as a Car Dealer business first, "
                    "then re-run with --demo to seed vehicles."
                )
            )
            return

        from decimal import Decimal

        total_seeded = 0
        for biz in qs:
            existing = CarDealerVehicle.objects.filter(business=biz).count()
            if existing >= 5 and not force:
                self.stdout.write(
                    f"  Skipping {biz.name} — already has {existing} vehicles (use --force to override)"
                )
                continue

            seeded = 0
            for vdata in DEMO_VEHICLES:
                make_name = vdata["make"]
                model_name = vdata["model"]

                try:
                    make_obj = CarMake.objects.get(name=make_name)
                    model_obj = CarModel.objects.get(make=make_obj, name=model_name)
                except (CarMake.DoesNotExist, CarModel.DoesNotExist):
                    # Fallback to free-text if reference data not yet seeded
                    make_obj = None
                    model_obj = None

                CarDealerVehicle.objects.create(
                    business=biz,
                    make=make_obj,
                    model=model_obj,
                    make_text=make_name if not make_obj else "",
                    model_text=model_name if not model_obj else "",
                    year=vdata.get("year"),
                    body_type=vdata.get("body_type", ""),
                    transmission=vdata.get("transmission", ""),
                    fuel_type=vdata.get("fuel_type", ""),
                    engine_size=vdata.get("engine_size", ""),
                    mileage=vdata.get("mileage"),
                    color=vdata.get("color", ""),
                    condition=vdata.get("condition", "used"),
                    status=vdata.get("status", "in_stock"),
                    buying_price=Decimal(vdata["buying_price"]) if vdata.get("buying_price") else None,
                    selling_price=Decimal(vdata["selling_price"]) if vdata.get("selling_price") else None,
                    description=vdata.get("description", ""),
                    features_notes="Demo vehicle — starter data",
                )
                seeded += 1

            total_seeded += seeded
            self.stdout.write(
                self.style.SUCCESS(f"  Seeded {seeded} demo vehicles into '{biz.name}'")
            )

        self.stdout.write(
            self.style.SUCCESS(f"Demo seed complete. Total vehicles added: {total_seeded}")
        )
