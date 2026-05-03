from __future__ import annotations

from dataclasses import dataclass

from django.core.management.base import BaseCommand
from django.db import DatabaseError

from inventory.services.media_safety import field_file_exists, storage_is_local


@dataclass
class MediaSpec:
    label: str
    model_path: str
    field_name: str
    clear_mode: str = "blank"


MEDIA_SPECS = [
    MediaSpec("marketplace listing primary", "inventory.MarketplaceListing", "media_file", "blank"),
    MediaSpec("marketplace gallery image", "inventory.MarketplaceListingImage", "image", "delete"),
    MediaSpec("car hire vehicle image", "inventory.HireVehicleImage", "image", "delete"),
    MediaSpec("car dealer vehicle image", "inventory.CarDealerVehicleImage", "image", "delete"),
    MediaSpec("farm batch primary image", "inventory.FarmLivestockBatch", "primary_image", "blank"),
    MediaSpec("farm crop primary image", "inventory.FarmCrop", "primary_image", "blank"),
    MediaSpec("farm batch gallery image", "inventory.FarmBatchImage", "image", "delete"),
    MediaSpec("welding notebook image", "inventory.WeldingNotebookEntry", "image", "blank"),
    MediaSpec("welding company logo", "inventory.WeldingBrandingSettings", "company_logo", "blank"),
    MediaSpec("welding signature image", "inventory.WeldingBrandingSettings", "signature_image", "blank"),
]


class Command(BaseCommand):
    help = "Audit local media file fields that point to missing files."

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear-invalid",
            action="store_true",
            help="Clear stale file references. Gallery image rows are deleted; files are never deleted.",
        )

    def handle(self, *args, **options):
        from django.apps import apps

        clear_invalid = bool(options.get("clear_invalid"))
        total_checked = 0
        total_missing = 0
        total_cleared = 0
        total_remote_skipped = 0

        for spec in MEDIA_SPECS:
            app_label, model_name = spec.model_path.split(".", 1)
            try:
                model = apps.get_model(app_label, model_name)
            except LookupError:
                self.stdout.write(self.style.WARNING(f"SKIP {spec.label}: model {spec.model_path} not found"))
                continue

            checked = missing = cleared = remote_skipped = 0
            qs = (
                model.objects.order_by()
                .only("pk", spec.field_name)
                .exclude(**{f"{spec.field_name}": ""})
                .exclude(**{f"{spec.field_name}__isnull": True})
            )
            try:
                iterator = qs.iterator()
                for obj in iterator:
                    field_file = getattr(obj, spec.field_name, None)
                    if not field_file or not getattr(field_file, "name", ""):
                        continue
                    checked += 1
                    total_checked += 1
                    storage = getattr(field_file, "storage", None)
                    if storage is not None and not storage_is_local(storage):
                        remote_skipped += 1
                        total_remote_skipped += 1
                        continue
                    if field_file_exists(field_file):
                        continue

                    missing += 1
                    total_missing += 1
                    self.stdout.write(
                        f"MISSING {spec.label}: {spec.model_path} id={obj.pk} "
                        f"{spec.field_name}={field_file.name!r}"
                    )
                    if clear_invalid:
                        if spec.clear_mode == "delete":
                            model.objects.filter(pk=obj.pk).delete()
                        else:
                            model.objects.filter(pk=obj.pk).update(**{spec.field_name: ""})
                        cleared += 1
                        total_cleared += 1
            except DatabaseError as exc:
                self.stdout.write(self.style.WARNING(f"SKIP {spec.label}: database schema error: {exc}"))
                continue

            self.stdout.write(
                f"{spec.label}: checked={checked} missing={missing} "
                f"remote_skipped={remote_skipped} cleared={cleared}"
            )

        mode = "CLEARED" if clear_invalid else "AUDIT ONLY"
        self.stdout.write(self.style.SUCCESS(f"Missing media audit {mode}"))
        self.stdout.write(f"Total checked: {total_checked}")
        self.stdout.write(f"Total missing: {total_missing}")
        self.stdout.write(f"Total remote skipped: {total_remote_skipped}")
        self.stdout.write(f"Total cleared: {total_cleared}")
