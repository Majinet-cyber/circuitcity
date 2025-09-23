from django.core.management.base import BaseCommand
from django.utils import timezone
from django.core.mail import mail_admins
from django.conf import settings
from datetime import timedelta
from inventory.models import InventoryItem, WarrantyCheckLog
from inventory.warranty import CarlcareClient

class Command(BaseCommand):
    help = (
        "Re-check IMEIs and alert if activation without sale is older than "
        "ACTIVATION_ALERT_MINUTES (settings, default 15)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit", type=int, default=0,
            help="Limit number of items to check (useful for testing)."
        )
        parser.add_argument(
            "--imei", type=str, default="",
            help="Check only this IMEI (bypasses sold_at filter)."
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Run without sending emails or saving updates (read-only)."
        )
        parser.add_argument(
            "--verbose-items", action="store_true",
            help="Print per-item status lines."
        )

    def handle(self, *args, **opts):
        client = CarlcareClient(timeout=getattr(settings, "WARRANTY_REQUEST_TIMEOUT", 12))
        now = timezone.now()
        window = int(getattr(settings, "ACTIVATION_ALERT_MINUTES", 15))
        threshold = timedelta(minutes=window)

        # Build queryset
        if opts["imei"]:
            qs = InventoryItem.objects.filter(imei=opts["imei"])
        else:
            qs = (
                InventoryItem.objects
                .filter(sold_at__isnull=True)
                .exclude(imei__isnull=True)
                .exclude(imei__exact="")
            )
        if opts["limit"] > 0:
            qs = qs.order_by("id")[:opts["limit"]]

        total = 0
        activated = 0
        alerted = 0

        for item in qs:
            total += 1
            w = client.check(item.imei)

            # Log result (unless dry-run)
            if not opts["dry_run"]:
                WarrantyCheckLog.objects.create(
                    imei=item.imei,
                    result=w.status,
                    expires_at=w.expires_at,
                    item=item,
                    notes="scheduled_check",
                )

            # Update cached fields
            item.warranty_status = w.status
            item.warranty_expires_at = w.expires_at
            item.warranty_last_checked_at = now

            is_activated = (w.status == "UNDER_WARRANTY" and w.expires_at is not None)
            if is_activated:
                activated += 1
                if not item.activation_detected_at:
                    item.activation_detected_at = now

                # Alert if past threshold and not sold
                age = now - item.activation_detected_at if item.activation_detected_at else timedelta(0)
                if (item.sold_at is None) and (age >= threshold):
                    alerted += 1
                    if not opts["dry_run"]:
                        mail_admins(
                            subject="Activation without sale (possible theft)",
                            message=(
                                f"IMEI {item.imei} activated but not marked sold for >{window} minutes. "
                                f"Item ID={item.id}"
                            ),
                            fail_silently=True,
                        )

            if not opts["dry_run"]:
                item.save(update_fields=[
                    "warranty_status", "warranty_expires_at",
                    "warranty_last_checked_at", "activation_detected_at"
                ])

            if opts["verbose_items"]:
                self.stdout.write(
                    f"{item.imei or 'NO-IMEI'} -> status={w.status} "
                    f"exp={w.expires_at or '-'} "
                    f"activated_at={item.activation_detected_at or '-'}"
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"Checked {total} item(s); activated now: {activated}; alerts sent: {alerted}"
                + (" (dry-run)" if opts["dry_run"] else "")
            )
        )
