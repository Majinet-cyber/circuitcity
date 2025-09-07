from django.core.management.base import BaseCommand
from insights.models import Badge

DEFAULTS = [
    dict(code="sales_beast", name="Sales Beast", emoji="🥇",
         description="30+ units in a week", rule={"metric":"units","window":"week","gte":30}),
    dict(code="fastest_10_today", name="Fastest Closer", emoji="🚀",
         description="First to 10 sales today", rule={"metric":"units","window":"day","gte":10,"first":True}),
    dict(code="premium_dealer", name="Premium Dealer", emoji="💎",
         description=">=22% margin and 15+ units in a month",
         rule={"metric":"margin","window":"month","gte_margin":0.22,"gte_units":15}),
    dict(code="streak_master_7", name="Streak Master", emoji="🔥",
         description="1+ sale daily for 7 days", rule={"metric":"streak","window":"day","gte":7}),
]

class Command(BaseCommand):
    help = "Seed default badges"

    def handle(self, *args, **opts):
        for b in DEFAULTS:
            Badge.objects.update_or_create(code=b["code"], defaults=b)
        self.stdout.write(self.style.SUCCESS(f"Seeded {len(DEFAULTS)} badges"))
