# inventory/management/commands/send_low_stock_digest.py
from collections import defaultdict
from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand
from django.db.models import Count
from inventory.models import InventoryItem, Product, Location

class Command(BaseCommand):
    help = "Send daily low-stock digest per product/location to admins."

    def handle(self, *args, **opts):
        # Count in-stock by Product+Location
        counts = (
            InventoryItem.active.in_stock()
            .values("product_id", "current_location_id")
            .annotate(qty=Count("id"))
        )

        # Build a lookup: { (product_id, location_id) : qty }
        qty_map = {(c["product_id"], c["current_location_id"]): c["qty"] for c in counts}

        # Pull all products once
        prods = {p.id: p for p in Product.objects.all()}
        locs = {l.id: l for l in Location.objects.all()}

        # Collect lines per location that are below threshold
        by_location = defaultdict(list)
        for (pid, lid), qty in qty_map.items():
            p = prods.get(pid)
            l = locs.get(lid)
            if not p or not l:
                continue
            if qty < p.low_stock_threshold:
                by_location[l.name].append((p, qty))

        if not by_location:
            self.stdout.write(self.style.SUCCESS("No low-stock items today."))
            return

        lines = []
        for loc_name, items in sorted(by_location.items()):
            lines.append(f"Location: {loc_name}")
            for p, qty in sorted(items, key=lambda t: t[0].name or t[0].model):
                pname = p.name or f"{p.brand} {p.model} {p.variant}".strip()
                lines.append(f"  - {p.code} | {pname}  -> Qty: {qty}  (threshold: {p.low_stock_threshold})")
            lines.append("")

        body = "\n".join(lines).rstrip()
        subject = "Low stock digest"
        from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@example.com")

        # Recipients: settings.ADMINS + staff users with emails
        recips = [email for _, email in getattr(settings, "ADMINS", []) if email]
        if not recips:
            # Fallback: all staff emails
            from django.contrib.auth import get_user_model
            User = get_user_model()
            recips = list(User.objects.filter(is_staff=True).exclude(email="").values_list("email", flat=True))

        if not recips:
            self.stdout.write(self.style.WARNING("No recipients found for digest. Set ADMINS or staff emails."))
            return

        send_mail(subject, body, from_email, recips, fail_silently=False)
        self.stdout.write(self.style.SUCCESS(f"Sent low-stock digest to {', '.join(recips)}"))


