from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "1072_marketplacestorefrontprofile_currency"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="marketplacelisting",
            name="verification_status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending Review"),
                    ("verified", "Verified"),
                    ("rejected", "Rejected"),
                    ("taken_down", "Taken Down"),
                ],
                db_index=True,
                default="pending",
                help_text="HQ moderation status for this listing.",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="marketplacelisting",
            name="verified_by",
            field=models.ForeignKey(
                blank=True,
                help_text="HQ staff who last moderated this listing.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="marketplace_listings_verified",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="marketplacelisting",
            name="verified_at",
            field=models.DateTimeField(
                blank=True,
                null=True,
                help_text="Timestamp of last HQ moderation action.",
            ),
        ),
        migrations.AddField(
            model_name="marketplacelisting",
            name="rejection_reason",
            field=models.TextField(
                blank=True,
                default="",
                help_text="Reason shown to merchant when listing is rejected.",
            ),
        ),
        migrations.AddField(
            model_name="marketplacelisting",
            name="takedown_reason",
            field=models.TextField(
                blank=True,
                default="",
                help_text="Internal reason for takedown (also shown to merchant).",
            ),
        ),
        migrations.AddField(
            model_name="marketplacelisting",
            name="is_visible_publicly",
            field=models.BooleanField(
                db_index=True,
                default=True,
                help_text=(
                    "Set to False by HQ to immediately hide listing from public marketplace "
                    "without changing the business-facing status."
                ),
            ),
        ),
    ]
