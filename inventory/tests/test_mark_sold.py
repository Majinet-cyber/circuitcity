# inventory/tests/test_mark_sold.py
from decimal import Decimal
from django.test import TestCase
from django.contrib.auth import get_user_model
from tenants.models import Location
from inventory.models import StockItem
from inventory.services.sales import mark_item_sold

class MarkSoldTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("u@test.com", "x")
        # create tenant, product, location, stock item…
        # self.loc = Location.objects.create(id=1, tenant=..., name="Air Easy")
        # self.item = StockItem.objects.create(code="677777777777777", tenant=..., product=..., status="in_stock", order_price=100, selling_price=200)

    def test_happy_path(self):
        res = mark_item_sold(
            code="677777777777777",
            price=Decimal("900000"),
            commission_pct=Decimal("7"),
            sold_at=None,
            location_id=self.loc.id,
            user=self.user,
        )
        self.assertTrue(res["sale_id"])
