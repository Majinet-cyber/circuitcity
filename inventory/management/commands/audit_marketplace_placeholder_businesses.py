from django.core.management.base import BaseCommand

from billing.models import BusinessSubscription
from inventory.services.marketplace_leads import PLACEHOLDER_BUSINESS_NAMES
from tenants.models import Business


class Command(BaseCommand):
    help = "Audit placeholder marketplace tenant businesses, with optional safe suspension."

    def add_arguments(self, parser):
        parser.add_argument(
            "--suspend-id",
            type=int,
            action="append",
            default=[],
            help="Suspend a specific placeholder business id after audit. Can be passed more than once.",
        )

    def handle(self, *args, **options):
        slugs = {
            "marketplace",
            "marketplace-leads",
            "marketplace-lead-agent",
            "marketplace-module",
        }
        qs = Business.objects.filter(name__iexact="__never__")
        for name in PLACEHOLDER_BUSINESS_NAMES:
            qs = qs | Business.objects.filter(name__iexact=name)
        for slug in slugs:
            qs = qs | Business.objects.filter(slug__iexact=slug)

        businesses = qs.distinct().order_by("name")
        count = businesses.count()
        self.stdout.write(f"Placeholder marketplace businesses found: {count}")
        for business in businesses:
            subscription_count = BusinessSubscription.objects.filter(business=business).count()
            listing_count = getattr(business, "marketplace_listings", Business.objects.none()).count()
            lead_count = getattr(business, "marketplace_leads", Business.objects.none()).count()
            self.stdout.write(
                f"- id={business.id} name={business.name!r} slug={business.slug!r} "
                f"subscriptions={subscription_count} listings={listing_count} leads={lead_count}"
            )
        if count:
            self.stdout.write(
                self.style.WARNING(
                    "Dry-run by default. To hide a confirmed placeholder from active tenant flows, "
                    "rerun with --suspend-id=<id>. This does not delete listings, leads, or subscriptions."
                )
            )

        for business_id in options["suspend_id"]:
            business = businesses.filter(id=business_id).first()
            if not business:
                self.stdout.write(self.style.ERROR(f"Refusing to suspend id={business_id}: not a placeholder match."))
                continue
            if business.status == "SUSPENDED":
                self.stdout.write(f"id={business.id} already suspended.")
                continue
            business.status = "SUSPENDED"
            business.save(update_fields=["status"])
            self.stdout.write(self.style.SUCCESS(f"Suspended placeholder business id={business.id} ({business.name})."))
