# inventory/migrations/1061_mobilemoney_operations_upgrade.py
"""
Mobile Money vertical upgrade:
- Adds send_money, receive_money, float_purchase, failed, correction tx types
- Adds customer_name and charges to MobileMoneyTransaction
- Adds credit_type, reason, source_transaction to MobileMoneyCredit
- Adds total_commissions to MobileMoneyReconciliation
- Creates CommissionRule model (configurable slab-based commission engine)
- Creates AgentSettlement model (inter-agent float/cash tracking)
"""
import django.db.models.deletion
import django.utils.timezone
from decimal import Decimal
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("inventory", "1060_rename_inventory_iot_device_type_ts_idx_inventory_i_device__aa70ae_idx_and_more"),
        ("tenants", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # ── MobileMoneyTransaction: new fields ───────────────────────────────
        migrations.AddField(
            model_name="mobilemoneytransaction",
            name="customer_name",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Customer name (optional)",
                max_length=150,
            ),
        ),
        migrations.AddField(
            model_name="mobilemoneytransaction",
            name="charges",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0.00"),
                help_text="Charges deducted from customer or network fees",
                max_digits=10,
            ),
        ),
        # Update tx_type choices to include new types
        migrations.AlterField(
            model_name="mobilemoneytransaction",
            name="tx_type",
            field=models.CharField(
                choices=[
                    ("send_money", "Send Money"),
                    ("receive_money", "Receive Money"),
                    ("cash_in", "Cash In"),
                    ("cash_out", "Cash Out"),
                    ("float_purchase", "Float Purchase"),
                    ("airtime", "Airtime Top-Up"),
                    ("bill_payment", "Bill Payment"),
                    ("reversal", "Reversal"),
                    ("failed", "Failed Transaction"),
                    ("correction", "Correction"),
                    ("adjustment", "Adjustment"),
                ],
                db_index=True,
                default="cash_in",
                help_text="Type of transaction",
                max_length=20,
            ),
        ),
        # New network index
        migrations.AddIndex(
            model_name="mobilemoneytransaction",
            index=models.Index(
                fields=["business", "network", "-created_at"],
                name="inventory_m_biz_net_ts_idx",
            ),
        ),

        # ── MobileMoneyCredit: new fields ────────────────────────────────────
        migrations.AddField(
            model_name="mobilemoneycredit",
            name="credit_type",
            field=models.CharField(
                choices=[
                    ("customer_credit", "Customer Credit (they owe us)"),
                    ("agent_debt", "Agent Debt (we owe them)"),
                ],
                db_index=True,
                default="customer_credit",
                help_text="Whether we are owed (credit) or we owe (debt)",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="mobilemoneycredit",
            name="reason",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Reason for credit/debt (e.g. 'sent money, forgot to collect')",
                max_length=200,
            ),
        ),
        migrations.AddField(
            model_name="mobilemoneycredit",
            name="source_transaction",
            field=models.ForeignKey(
                blank=True,
                help_text="Transaction that originated this credit/debt",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="linked_credits",
                to="inventory.mobilemoneytransaction",
            ),
        ),
        migrations.AddIndex(
            model_name="mobilemoneycredit",
            index=models.Index(
                fields=["business", "status"],
                name="inventory_m_biz_status_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="mobilemoneycredit",
            index=models.Index(
                fields=["business", "credit_type", "status"],
                name="inventory_m_biz_type_status_idx",
            ),
        ),

        # ── MobileMoneyReconciliation: total_commissions ─────────────────────
        migrations.AddField(
            model_name="mobilemoneyreconciliation",
            name="total_commissions",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0.00"),
                help_text="Commission earned on this day",
                max_digits=10,
            ),
        ),

        # ── CommissionRule ───────────────────────────────────────────────────
        migrations.CreateModel(
            name="CommissionRule",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("network", models.CharField(
                    choices=[("airtel", "Airtel Money"), ("tnm", "TNM Mpamba"), ("other", "Other")],
                    db_index=True,
                    max_length=20,
                )),
                ("tx_type", models.CharField(
                    choices=[
                        ("send_money", "Send Money"),
                        ("receive_money", "Receive Money"),
                        ("cash_in", "Cash In"),
                        ("cash_out", "Cash Out"),
                        ("float_purchase", "Float Purchase"),
                        ("airtime", "Airtime Top-Up"),
                        ("bill_payment", "Bill Payment"),
                        ("reversal", "Reversal"),
                        ("failed", "Failed Transaction"),
                        ("correction", "Correction"),
                        ("adjustment", "Adjustment"),
                    ],
                    db_index=True,
                    max_length=20,
                )),
                ("rule_type", models.CharField(
                    choices=[("fixed", "Fixed Amount"), ("percentage", "Percentage of Transaction"), ("slab", "Amount Slab")],
                    default="percentage",
                    max_length=20,
                )),
                ("fixed_amount", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=10)),
                ("percentage_rate", models.DecimalField(
                    decimal_places=4,
                    default=Decimal("0.0000"),
                    help_text="e.g. 0.0150 = 1.5%",
                    max_digits=6,
                )),
                ("min_amount", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12)),
                ("max_amount", models.DecimalField(
                    blank=True,
                    decimal_places=2,
                    help_text="Leave blank for no upper limit",
                    max_digits=12,
                    null=True,
                )),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("business", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="mm_commission_rules",
                    to="tenants.business",
                )),
            ],
            options={"ordering": ["network", "tx_type", "min_amount"]},
        ),

        # ── AgentSettlement ──────────────────────────────────────────────────
        migrations.CreateModel(
            name="AgentSettlement",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("settlement_type", models.CharField(
                    choices=[
                        ("borrowed_float", "Borrowed Float"),
                        ("returned_float", "Returned Float"),
                        ("borrowed_cash", "Borrowed Cash"),
                        ("returned_cash", "Returned Cash"),
                        ("settlement", "General Settlement"),
                    ],
                    db_index=True,
                    default="borrowed_float",
                    max_length=20,
                )),
                ("agent_name", models.CharField(help_text="Other agent's name", max_length=150)),
                ("agent_phone", models.CharField(blank=True, default="", max_length=20)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=12)),
                ("direction", models.CharField(
                    choices=[("given", "We gave"), ("received", "We received")],
                    default="received",
                    help_text="Did we give or receive?",
                    max_length=10,
                )),
                ("is_settled", models.BooleanField(default=False)),
                ("settled_at", models.DateTimeField(blank=True, null=True)),
                ("notes", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("business", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="mm_agent_settlements",
                    to="tenants.business",
                )),
                ("created_by", models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="mm_settlements_created",
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]
