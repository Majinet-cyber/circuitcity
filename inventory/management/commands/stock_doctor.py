# inventory/management/commands/stock_doctor.py
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from inventory.models import InventoryItem, normalize_imei

def digits_only(s): return "".join(ch for ch in str(s or "") if ch.isdigit())

class Command(BaseCommand):
    help = "Normalize IMEIs, re-scope to a business/location, and fix IN_STOCK/SOLD flags. Optionally sell a batch."

    def add_arguments(self, parser):
        parser.add_argument("--business", type=int, required=True, help="Business ID")
        parser.add_argument("--location", type=int, required=True, help="Location ID")
        parser.add_argument("--sell-file", type=str, help="Path to a text file with IMEIs to mark SOLD (one per line)")
        parser.add_argument("--dry-run", action="store_true", help="Do not write changes")

    @transaction.atomic
    def handle(self, *args, **opts):
        biz_id = opts["business"]
        loc_id = opts["location"]
        dry = opts["dry_run"]

        fixed_norm = fixed_scope = fixed_flags = 0
        for it in InventoryItem.all_objects.all().iterator():
            changed = []

            # normalize
            raw = getattr(it, "imei", None)
            if raw:
                d = digits_only(raw)
                d15 = normalize_imei(d) if callable(normalize_imei) else (d[:15] if len(d) >= 15 else d)
                if d15 and d15 != it.imei:
                    it.imei = d15; changed.append("imei")

            # re-scope
            if getattr(it, "business_id", None) != biz_id:
                it.business_id = biz_id; changed.append("business_id")
            if getattr(it, "current_location_id", None) != loc_id:
                it.current_location_id = loc_id; changed.append("current_location_id")

            # flags
            st = getattr(it, "status", None)
            sold_at = getattr(it, "sold_at", None)
            is_active = getattr(it, "is_active", True)

            if sold_at is not None:
                if st != "SOLD": it.status = "SOLD"; changed.append("status")
                if is_active: it.is_active = False; changed.append("is_active")
            elif st == "SOLD":
                it.sold_at = timezone.now(); changed.append("sold_at")
                if is_active: it.is_active = False; changed.append("is_active")
            elif st == "IN_STOCK":
                if sold_at is not None: it.sold_at = None; changed.append("sold_at")
                if is_active is False: it.is_active = True; changed.append("is_active")

            if changed and not dry:
                it.save(update_fields=list(dict.fromkeys(changed)))

            if "imei" in changed: fixed_norm += 1
            if {"business_id","current_location_id"} & set(changed): fixed_scope += 1
            if {"status","sold_at","is_active"} & set(changed): fixed_flags += 1

        self.stdout.write(self.style.SUCCESS(
            f"Normalized: {fixed_norm} | Re-scoped: {fixed_scope} | Flags fixed: {fixed_flags}"
        ))

        # optional bulk sell
        sell_file = opts.get("sell_file")
        if sell_file:
            sold = missing = 0
            with open(sell_file, "r", encoding="utf-8") as fh:
                for line in fh:
                    raw = line.strip()
                    if not raw: continue
                    d = digits_only(raw)
                    d15 = normalize_imei(d) if callable(normalize_imei) else (d[:15] if len(d) >= 15 else d)
                    it = InventoryItem.all_objects.filter(
                        imei=d15, business_id=biz_id, current_location_id=loc_id
                    ).first()
                    if not it:
                        missing += 1
                        continue
                    changed = []
                    if getattr(it, "status", None) != "SOLD":
                        it.status = "SOLD"; changed.append("status")
                    if getattr(it, "sold_at", None) is None:
                        it.sold_at = timezone.now(); changed.append("sold_at")
                    if getattr(it, "is_active", True):
                        it.is_active = False; changed.append("is_active")
                    if changed and not dry:
                        it.save(update_fields=list(dict.fromkeys(changed)))
                    sold += 1
            self.stdout.write(self.style.SUCCESS(f"Bulk SOLD: {sold} | Not found in-scope: {missing}"))
            if dry:
                self.stdout.write(self.style.WARNING("DRY RUN: no changes were written."))









