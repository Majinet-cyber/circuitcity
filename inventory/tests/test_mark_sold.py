# inventory/tests/test_mark_sold.py
from decimal import Decimal
import importlib
import pytest
from django.test import TestCase
from django.contrib.auth import get_user_model

# -----------------------
# Optional imports (be defensive)
# -----------------------
try:
    inv_models = importlib.import_module("inventory.models")
except Exception:  # inventory app missing?
    inv_models = None

StockItem = getattr(inv_models, "StockItem", None) if inv_models else None
# Some codebases name it InventoryItem instead of StockItem:
if StockItem is None and inv_models is not None:
    StockItem = getattr(inv_models, "InventoryItem", None)

Product = getattr(inv_models, "Product", None) if inv_models else None

try:
    ten_models = importlib.import_module("tenants.models")
except Exception:
    ten_models = None

Business = getattr(ten_models, "Business", None) if ten_models else None
Location = getattr(ten_models, "Location", None) if ten_models else None

# Service under test
try:
    sales_mod = importlib.import_module("inventory.services.sales")
    mark_item_sold = getattr(sales_mod, "mark_item_sold", None)
except Exception:
    mark_item_sold = None

User = get_user_model()

pytestmark = pytest.mark.django_db


class MarkSoldTests(TestCase):
    @pytest.mark.skipif(
        any(x is None for x in [StockItem, Business, Product, mark_item_sold]),
        reason="Required models/services not available (StockItem/Business/Product/mark_item_sold).",
    )
    def test_happy_path(self):
        """
        Minimal happy-path:
        - create Business, Product (+ Location if model exists)
        - create StockItem (or InventoryItem) with a known code
        - call mark_item_sold and assert a sale_id is returned
        """
        # Tenant / org
        biz = Business.objects.create(name="Test Biz")

        # Product (adjust fields here if your Product requires more)
        prod = Product.objects.create(name="Phone X", business=biz)

        # Location is optional: only create/use if model exists
        loc = Location.objects.create(name="HQ", business=biz) if Location else None

        # User who performs the sale
        user = User.objects.create_user("u@test.com", password="x")

        # Stock item (tweak field names if your model differs)
        code = "677777777777777"
        stock_kwargs = {
            "business": biz,
            "product": prod,
            "code": code,
        }

        # Common field names across codebases; provide conservative defaults
        # Add location if the model has such a field and we created one
        if hasattr(StockItem, "status"):
            stock_kwargs["status"] = "in_stock"
        if hasattr(StockItem, "order_price"):
            stock_kwargs["order_price"] = Decimal("100")
        if hasattr(StockItem, "selling_price"):
            stock_kwargs["selling_price"] = Decimal("200")
        if loc and hasattr(StockItem, "location"):
            stock_kwargs["location"] = loc

        item = StockItem.objects.create(**stock_kwargs)

        # Prepare call to service
        call_kwargs = dict(
            code=item.code,
            price=Decimal("900000"),
            commission_pct=Decimal("7"),
            sold_at=None,
            user=user,
        )
        if loc is not None:
            # Only include if your service signature expects/accepts it
            call_kwargs["location_id"] = loc.id

        res = mark_item_sold(**call_kwargs)
        assert res and res.get("sale_id"), "Expected mark_item_sold to return a sale_id"
