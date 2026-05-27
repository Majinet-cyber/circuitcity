# Generated migration for Phase 4 price audit models

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [
        ("audit", "0001_initial"),
        ("sales", "0001_initial"),
        ("inventory", "0001_initial"),
        ("tenants", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="PriceAdjustment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "adjustment_type",
                    models.CharField(
                        choices=[
                            ("PRICE_CORRECTION", "Price Correction"),
                            ("COST_CORRECTION", "Cost Correction"),
                            ("BOTH", "Price and Cost Correction"),
                        ],
                        help_text="What aspect of the sale is being corrected",
                        max_length=20,
                    ),
                ),
                (
                    "original_selling_price",
                    models.DecimalField(decimal_places=2, help_text="Selling price before adjustment", max_digits=12),
                ),
                (
                    "original_cost_price",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        help_text="Cost price before adjustment (if applicable)",
                        max_digits=12,
                        null=True,
                    ),
                ),
                (
                    "new_selling_price",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        help_text="New selling price (null if only cost changed)",
                        max_digits=12,
                        null=True,
                    ),
                ),
                (
                    "new_cost_price",
                    models.DecimalField(
                        blank=True,
                        decimal_places=2,
                        help_text="New cost price (null if only selling price changed)",
                        max_digits=12,
                        null=True,
                    ),
                ),
                ("reason", models.TextField(help_text="Why this adjustment was made (required)")),
                (
                    "adjusted_at",
                    models.DateTimeField(default=django.utils.timezone.now, help_text="When adjustment was made"),
                ),
                (
                    "commission_adjusted",
                    models.BooleanField(
                        default=False, help_text="Whether a compensating wallet transaction was created"
                    ),
                ),
                (
                    "commission_adjustment_txn_id",
                    models.IntegerField(
                        blank=True, help_text="ID of compensating WalletTransaction (if any)", null=True
                    ),
                ),
                (
                    "adjusted_by",
                    models.ForeignKey(
                        help_text="Manager who made the adjustment",
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="price_adjustments",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "business",
                    models.ForeignKey(
                        help_text="Business this adjustment belongs to",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="price_adjustments",
                        to="tenants.business",
                    ),
                ),
                (
                    "sale",
                    models.ForeignKey(
                        help_text="Sale being adjusted",
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="price_adjustments",
                        to="sales.sale",
                    ),
                ),
            ],
            options={
                "ordering": ["-adjusted_at"],
            },
        ),
        migrations.CreateModel(
            name="UnsoldPriceEdit",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "field_changed",
                    models.CharField(
                        choices=[
                            ("order_price", "Order Price (Cost)"),
                            ("selling_price", "Selling Price"),
                            ("both", "Both Prices"),
                        ],
                        help_text="Which price field(s) changed",
                        max_length=20,
                    ),
                ),
                ("old_order_price", models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ("old_selling_price", models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ("new_order_price", models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ("new_selling_price", models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ("reason", models.TextField(help_text="Why this edit was made (required)")),
                ("edited_at", models.DateTimeField(default=django.utils.timezone.now)),
                (
                    "business",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="unsold_price_edits",
                        to="tenants.business",
                    ),
                ),
                (
                    "edited_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="unsold_price_edits",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "item",
                    models.ForeignKey(
                        help_text="Inventory item that was edited",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="price_edits",
                        to="inventory.inventoryitem",
                    ),
                ),
            ],
            options={
                "ordering": ["-edited_at"],
            },
        ),
        migrations.AddIndex(
            model_name="priceadjustment",
            index=models.Index(fields=["sale", "-adjusted_at"], name="audit_price_sale_ad_idx"),
        ),
        migrations.AddIndex(
            model_name="priceadjustment",
            index=models.Index(fields=["business", "-adjusted_at"], name="audit_price_busines_idx"),
        ),
        migrations.AddIndex(
            model_name="priceadjustment",
            index=models.Index(fields=["adjusted_by", "-adjusted_at"], name="audit_price_adjuste_idx"),
        ),
        migrations.AddIndex(
            model_name="unsoldpriceedit",
            index=models.Index(fields=["item", "-edited_at"], name="audit_unsol_item_ed_idx"),
        ),
        migrations.AddIndex(
            model_name="unsoldpriceedit",
            index=models.Index(fields=["business", "-edited_at"], name="audit_unsol_busines_idx"),
        ),
        migrations.AddIndex(
            model_name="unsoldpriceedit",
            index=models.Index(fields=["edited_by", "-edited_at"], name="audit_unsol_edited__idx"),
        ),
    ]
