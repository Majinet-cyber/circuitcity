# Generated migration: add e-signature fields to MerchantContract
import uuid
from django.db import migrations, models


def _populate_sign_tokens(apps, schema_editor):
    """Give every existing MerchantContract a unique sign token."""
    MerchantContract = apps.get_model("hq", "MerchantContract")
    for contract in MerchantContract.objects.filter(sign_token__isnull=True):
        contract.sign_token = uuid.uuid4()
        contract.save(update_fields=["sign_token"])


class Migration(migrations.Migration):

    dependencies = [
        ("hq", "0010_add_hq_permissions"),
    ]

    operations = [
        # 1. Add status field
        migrations.AddField(
            model_name="merchantcontract",
            name="status",
            field=models.CharField(
                choices=[
                    ("draft", "Draft"),
                    ("sent", "Sent to Merchant"),
                    ("viewed", "Viewed by Merchant"),
                    ("signed", "Signed"),
                    ("void", "Void"),
                ],
                default="draft",
                db_index=True,
                max_length=20,
            ),
        ),
        # 2. Add signature_name
        migrations.AddField(
            model_name="merchantcontract",
            name="signature_name",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Full name typed by the merchant when signing",
                max_length=255,
            ),
        ),
        # 3. Add signed_ip
        migrations.AddField(
            model_name="merchantcontract",
            name="signed_ip",
            field=models.GenericIPAddressField(blank=True, null=True),
        ),
        # 4. Add signed_user_agent
        migrations.AddField(
            model_name="merchantcontract",
            name="signed_user_agent",
            field=models.TextField(blank=True, default=""),
        ),
        # 5. Add sign_token (nullable first so existing rows can be populated)
        migrations.AddField(
            model_name="merchantcontract",
            name="sign_token",
            field=models.UUIDField(null=True, blank=True),
        ),
        # 6. Populate existing rows with unique tokens via Python
        migrations.RunPython(_populate_sign_tokens, reverse_code=migrations.RunPython.noop),
        # 7. Now make it non-nullable with default + unique
        migrations.AlterField(
            model_name="merchantcontract",
            name="sign_token",
            field=models.UUIDField(default=uuid.uuid4, unique=True, db_index=True),
        ),
    ]
