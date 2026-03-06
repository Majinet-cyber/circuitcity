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


class Command(BaseCommand):
    help = "Seed CarMake and CarModel reference data for Car Dealer vertical"

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Re-seed data even if makes/models already exist",
        )

    def handle(self, *args, **options):
        force = options.get("force", False)

        try:
            from inventory.models_car_dealer import CarMake, CarModel
        except ImportError:
            self.stderr.write(
                self.style.ERROR("Car dealer models not available. Run migrations first.")
            )
            return

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
                f"Done. Created {created_makes} makes, {created_models} models. "
                f"Updated {updated_makes} makes, {updated_models} models."
            )
        )
