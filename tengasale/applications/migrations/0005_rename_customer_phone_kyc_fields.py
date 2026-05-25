# Generated manually to preserve existing KYC image data while aligning migrations with models.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("applications", "0004_financingapplication_calculated_3_month_daily_and_more"),
    ]

    operations = [
        migrations.RenameField(
            model_name="financingapplication",
            old_name="customer_phone_image",
            new_name="customer_face_image",
        ),
        migrations.RenameField(
            model_name="financingapplication",
            old_name="correction_customer_phone_image",
            new_name="correction_customer_face_image",
        ),
        migrations.AlterField(
            model_name="financingapplication",
            name="customer_face_image",
            field=models.ImageField(blank=True, null=True, upload_to="kyc/faces/"),
        ),
        migrations.AlterField(
            model_name="financingapplication",
            name="status",
            field=models.CharField(
                choices=[
                    ("started", "Start"),
                    ("customer_details", "Customer Details"),
                    ("device_selection", "Device Selection"),
                    ("kyc", "KYC"),
                    ("kyc_capture", "KYC Capture"),
                    ("location_details", "Location Details"),
                    ("work_details", "Work Details"),
                    ("signature", "Signature"),
                    ("correction_requested", "Correction Requested"),
                    ("imei_required", "IMEI Required"),
                    ("submitted", "Submitted"),
                    ("under_review", "Under Review"),
                    ("approved", "Approved"),
                    ("rejected", "Rejected"),
                    ("completed", "Completed"),
                ],
                default="started",
                max_length=40,
            ),
        ),
    ]
