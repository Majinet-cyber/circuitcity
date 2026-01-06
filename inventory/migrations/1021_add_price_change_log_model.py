# Generated manually for price change audit feature

from decimal import Decimal

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "1020_ensure_cementcost_notes_column"),
        ("tenants", "0010_business_business_kind"),  # Location exists by this point
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="PriceChangeLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "scope",
                    models.CharField(
                        choices=[
                            ("product_price", "Product Current Price"),
                            ("sale_line", "Sale Line Price Correction"),
                        ],
                        db_index=True,
                        help_text="What type of price was changed",
                        max_length=20,
                    ),
                ),
                (
                    "old_price",
                    models.DecimalField(
                        decimal_places=2,
                        help_text="Price before change",
                        max_digits=10,
                        validators=[MinValueValidator(Decimal("0.00"))],
                    ),
                ),
                (
                    "new_price",
                    models.DecimalField(
                        decimal_places=2,
                        help_text="Price after change",
                        max_digits=10,
                        validators=[MinValueValidator(Decimal("0.00"))],
                    ),
                ),
                ("reason", models.CharField(help_text="Required: Why was this price changed?", max_length=500)),
                (
                    "created_at",
                    models.DateTimeField(
                        db_index=True,
                        default=django.utils.timezone.now,
                        editable=False,
                        help_text="When change was made",
                    ),
                ),
                (
                    "business",
                    models.ForeignKey(
                        db_index=True,
                        help_text="Business where price change occurred",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="price_changes",
                        to="tenants.business",
                    ),
                ),
                (
                    "location",
                    models.ForeignKey(
                        blank=True,
                        help_text="Location (if applicable)",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="price_changes",
                        to="inventory.location",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        help_text="Manager who made the change",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="price_changes_made",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "product",
                    models.ForeignKey(
                        blank=True,
                        help_text="Product (for PRODUCT_PRICE scope)",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="price_changes",
                        to="inventory.merchproduct",
                    ),
                ),
                (
                    "cement_sale",
                    models.ForeignKey(
                        blank=True,
                        help_text="Cement sale (for SALE_LINE scope)",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="price_changes",
                        to="inventory.cementsale",
                    ),
                ),
                (
                    "liquor_sale",
                    models.ForeignKey(
                        blank=True,
                        help_text="Liquor sale (for SALE_LINE scope)",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="price_changes",
                        to="inventory.liquorsale",
                    ),
                ),
                (
                    "pharmacy_sale",
                    models.ForeignKey(
                        blank=True,
                        help_text="Pharmacy sale (for SALE_LINE scope)",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="price_changes",
                        to="inventory.pharmacysale",
                    ),
                ),
                (
                    "grocery_sale",
                    models.ForeignKey(
                        blank=True,
                        help_text="Grocery sale (for SALE_LINE scope)",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="price_changes",
                        to="inventory.grocerysale",
                    ),
                ),
                (
                    "clothing_sale",
                    models.ForeignKey(
                        blank=True,
                        help_text="Clothing sale (for SALE_LINE scope)",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="price_changes",
                        to="inventory.clothingsale",
                    ),
                ),
            ],
            options={
                "verbose_name": "Price Change",
                "verbose_name_plural": "Price Changes",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="pricechangelog",
            index=models.Index(fields=["business", "-created_at"], name="inventory_p_busines_idx001"),
        ),
        migrations.AddIndex(
            model_name="pricechangelog",
            index=models.Index(fields=["business", "scope", "-created_at"], name="inventory_p_busines_idx002"),
        ),
        migrations.AddIndex(
            model_name="pricechangelog",
            index=models.Index(fields=["product", "-created_at"], name="inventory_p_product_idx001"),
        ),
        migrations.AddIndex(
            model_name="pricechangelog",
            index=models.Index(fields=["user", "-created_at"], name="inventory_p_user_cr_idx001"),
        ),
    ]
