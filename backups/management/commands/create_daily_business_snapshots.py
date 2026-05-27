from __future__ import annotations

import os

from django.core.files.base import File
from django.core.management.base import BaseCommand
from django.utils import timezone

from backups.helpers import cleanup_temp_files, export_business_data_to_zip
from backups.models import BackupSnapshot, BackupStatus, DataExportLog
from tenants.models import Business


class Command(BaseCommand):
    help = "Create daily Data Vault snapshots for tenant-scoped business data."

    def add_arguments(self, parser):
        parser.add_argument("--business-id", type=int, help="Limit snapshot creation to one business.")
        parser.add_argument("--force", action="store_true", help="Create a snapshot even if one already exists today.")

    def handle(self, *args, **options):
        today = timezone.localdate()
        qs = Business.objects.all().order_by("id")
        if options.get("business_id"):
            qs = qs.filter(pk=options["business_id"])

        created = 0
        skipped = 0
        failed = 0
        for business in qs:
            if not options.get("force") and BackupSnapshot.objects.filter(
                business=business,
                status=BackupStatus.SUCCESS,
                created_at__date=today,
            ).exists():
                skipped += 1
                continue

            snapshot = BackupSnapshot.objects.create(business=business, status=BackupStatus.PENDING)
            try:
                snapshot.status = BackupStatus.RUNNING
                snapshot.save(update_fields=["status"])
                zip_path, records_count = export_business_data_to_zip(business)
                file_size = os.path.getsize(zip_path)
                with open(zip_path, "rb") as fh:
                    snapshot.file.save(zip_path.name, File(fh), save=False)
                snapshot.file_size = file_size
                snapshot.records_count = records_count
                snapshot.status = BackupStatus.SUCCESS
                snapshot.completed_at = timezone.now()
                snapshot.save()
                DataExportLog.objects.create(
                    business=business,
                    category=DataExportLog.ExportCategory.ALL,
                    export_format=DataExportLog.ExportFormat.ZIP,
                    label="Daily automatic snapshot",
                    records_count=records_count,
                    file_size=file_size,
                    status=BackupStatus.SUCCESS,
                    snapshot=snapshot,
                )
                cleanup_temp_files(zip_path)
                created += 1
            except Exception as exc:
                snapshot.status = BackupStatus.FAILED
                snapshot.error_message = str(exc)
                snapshot.completed_at = timezone.now()
                snapshot.save(update_fields=["status", "error_message", "completed_at"])
                failed += 1
                self.stderr.write(f"{business.id} {business.name}: {exc}")

        self.stdout.write(self.style.SUCCESS(f"Daily snapshots complete. created={created} skipped={skipped} failed={failed}"))
