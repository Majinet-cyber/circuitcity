# Generated manually for farm premium + marketplace sync

import django.core.validators
import django.db.models.deletion
import django.utils.timezone
from decimal import Decimal

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "1052_vehicle_gallery_images"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="farmlivestockbatch",
            name="age_months",
            field=models.PositiveSmallIntegerField(
                blank=True,
                help_text="Typical or average age in months (for the batch)",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="farmlivestockbatch",
            name="animal_subtype",
            field=models.CharField(
                choices=[
                    ("unspecified", "Select subtype (use quick-picks below)"),
                    ("chicken_broilers", "Broilers"),
                    ("chicken_layers", "Layers"),
                    ("chicken_indigenous", "Indigenous / local chickens"),
                    ("chicken_hybrid", "Hybrid chickens"),
                    ("chicken_chicks", "Chicks"),
                    ("chicken_point_of_lay", "Point-of-lay birds"),
                    ("pig_local", "Local pigs"),
                    ("pig_hybrid", "Hybrid / improved pigs"),
                    ("pig_piglets", "Piglets"),
                    ("pig_growers", "Growers / fattening"),
                    ("pig_sows", "Sows"),
                    ("pig_boars", "Boars"),
                    ("goat_local", "Local goats"),
                    ("goat_boer", "Boer / improved breeds"),
                    ("goat_kids", "Kids (young goats)"),
                    ("goat_breeding_male", "Breeding males"),
                    ("goat_breeding_female", "Breeding females"),
                    ("cattle_local", "Local cattle"),
                    ("cattle_dairy", "Dairy cattle"),
                    ("cattle_beef", "Beef cattle"),
                    ("cattle_calves", "Calves"),
                    ("cattle_heifers", "Heifers"),
                    ("cattle_bulls", "Bulls"),
                    ("ducks_default", "Ducks"),
                    ("ducks_layer", "Layer ducks"),
                    ("rabbits_broiler", "Rabbits (meat)"),
                    ("rabbits_breeding", "Rabbits (breeding)"),
                    ("sheep_breeding", "Sheep (breeding)"),
                    ("sheep_lambs", "Lambs"),
                    ("fish_pond", "General pond fish"),
                    ("fish_tilapia", "Tilapia"),
                    ("fish_catfish", "Catfish"),
                    ("other_generic", "Other / custom"),
                ],
                db_index=True,
                default="unspecified",
                help_text="Practical subtype (broilers, layers, piglets, etc.)",
                max_length=40,
            ),
        ),
        migrations.AddField(
            model_name="farmlivestockbatch",
            name="breed_text",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Breed or strain (optional, free text)",
                max_length=120,
            ),
        ),
        migrations.AddField(
            model_name="farmlivestockbatch",
            name="cost_basis_per_head_mwk",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Your cost per head (for margin checks)",
                max_digits=12,
                null=True,
                validators=[django.core.validators.MinValueValidator(Decimal("0.00"))],
            ),
        ),
        migrations.AddField(
            model_name="farmlivestockbatch",
            name="dairy_output_note",
            field=models.CharField(
                blank=True,
                default="",
                help_text="For dairy: output note (e.g. litres per day)",
                max_length=200,
            ),
        ),
        migrations.AddField(
            model_name="farmlivestockbatch",
            name="egg_production_status",
            field=models.CharField(
                blank=True,
                default="",
                help_text="For layers: production level or status",
                max_length=80,
            ),
        ),
        migrations.AddField(
            model_name="farmlivestockbatch",
            name="expected_sale_price_mwk",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Asking or expected sale price per head (marketplace & margin)",
                max_digits=12,
                null=True,
                validators=[django.core.validators.MinValueValidator(Decimal("0.00"))],
            ),
        ),
        migrations.AddField(
            model_name="farmlivestockbatch",
            name="feed_growth_stage",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Feed or growth stage (e.g. starter, grower, finisher)",
                max_length=80,
            ),
        ),
        migrations.AddField(
            model_name="farmlivestockbatch",
            name="gender",
            field=models.CharField(
                blank=True,
                choices=[
                    ("na", "Not specified"),
                    ("mixed", "Mixed flock / herd"),
                    ("male", "Male"),
                    ("female", "Female"),
                ],
                default="na",
                max_length=12,
            ),
        ),
        migrations.AddField(
            model_name="farmlivestockbatch",
            name="health_status",
            field=models.CharField(
                choices=[
                    ("unknown", "Not recorded"),
                    ("good", "Good"),
                    ("watch", "Under observation"),
                    ("treating", "Under treatment / vet care"),
                ],
                default="unknown",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="farmlivestockbatch",
            name="is_featured_listing",
            field=models.BooleanField(
                default=False,
                help_text="Highlight on internal dashboard and metadata for marketplace",
            ),
        ),
        migrations.AddField(
            model_name="farmlivestockbatch",
            name="last_marketplace_sync_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="farmlivestockbatch",
            name="marketplace_listing",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="farm_livestock_batch",
                to="inventory.marketplacelisting",
            ),
        ),
        migrations.AddField(
            model_name="farmlivestockbatch",
            name="primary_image",
            field=models.ImageField(
                blank=True,
                help_text="Primary photo for this batch (used for marketplace cover)",
                null=True,
                upload_to="farm/batch/%Y/%m/",
            ),
        ),
        migrations.AddField(
            model_name="farmlivestockbatch",
            name="sale_availability",
            field=models.CharField(
                choices=[
                    ("available_now", "Available now"),
                    ("preorder", "Preorder / future date"),
                    ("reserved", "Reserved (spoken for)"),
                ],
                default="available_now",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="farmlivestockbatch",
            name="vaccination_status",
            field=models.CharField(
                choices=[
                    ("unknown", "Not recorded"),
                    ("current", "Vaccination current"),
                    ("partial", "Partial / needs booster"),
                    ("none", "None on record"),
                ],
                default="unknown",
                max_length=20,
            ),
        ),
        migrations.AddIndex(
            model_name="farmlivestockbatch",
            index=models.Index(
                fields=["business", "animal_subtype"],
                name="inventory_f_business_3e7a8d_idx",
            ),
        ),
        migrations.CreateModel(
            name="FarmBatchImage",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "image",
                    models.ImageField(upload_to="farm/batch_gallery/%Y/%m/"),
                ),
                ("caption", models.CharField(blank=True, default="", max_length=200)),
                (
                    "sort_order",
                    models.PositiveSmallIntegerField(db_index=True, default=0),
                ),
                (
                    "uploaded_at",
                    models.DateTimeField(
                        db_index=True, default=django.utils.timezone.now
                    ),
                ),
                (
                    "batch",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="gallery_images",
                        to="inventory.farmlivestockbatch",
                    ),
                ),
            ],
            options={
                "ordering": ["sort_order", "uploaded_at"],
            },
        ),
        migrations.AlterField(
            model_name="farmcrop",
            name="category",
            field=models.CharField(
                choices=[
                    ("staples", "Staples"),
                    ("cash_crops", "Cash Crops"),
                    ("legumes", "Legumes"),
                    ("roots_tubers", "Roots & Tubers"),
                    ("vegetables", "Vegetables"),
                    ("eggs", "Eggs"),
                    ("milk", "Milk & dairy"),
                    ("animal_feed", "Animal feed"),
                    ("fertilizer", "Fertilizer / manure"),
                    ("fresh_produce", "Fresh produce"),
                    ("seedlings", "Seedlings & saplings"),
                ],
                db_index=True,
                default="staples",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="farmcrop",
            name="cost_basis_per_unit_mwk",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Unit cost (for margin estimation)",
                max_digits=12,
                null=True,
                validators=[django.core.validators.MinValueValidator(Decimal("0.00"))],
            ),
        ),
        migrations.AddField(
            model_name="farmcrop",
            name="is_featured_listing",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="farmcrop",
            name="last_marketplace_sync_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="farmcrop",
            name="list_price_per_unit_mwk",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Asking price per unit for marketplace & margin",
                max_digits=12,
                null=True,
                validators=[django.core.validators.MinValueValidator(Decimal("0.00"))],
            ),
        ),
        migrations.AddField(
            model_name="farmcrop",
            name="marketplace_listing",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="farm_crop_line",
                to="inventory.marketplacelisting",
            ),
        ),
        migrations.AddField(
            model_name="farmcrop",
            name="primary_image",
            field=models.ImageField(
                blank=True, null=True, upload_to="farm/crop/%Y/%m/"
            ),
        ),
        migrations.AddField(
            model_name="farmcrop",
            name="sale_availability",
            field=models.CharField(
                choices=[
                    ("available_now", "Available now"),
                    ("preorder", "Preorder / future date"),
                    ("reserved", "Reserved (spoken for)"),
                ],
                default="available_now",
                max_length=20,
            ),
        ),
    ]
