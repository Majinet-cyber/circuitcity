from __future__ import annotations

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from tenants.models import Business
from wallet.business_memory import record_cash_bank_transaction, record_company_expense_once
from wallet.models import AdminPurchaseOrder, AdminPurchaseOrderItem, CashBankTransaction, PurchaseOrderStatus


class Command(BaseCommand):
    help = "Create clearly-labelled starter sample records for a truly new business. Never runs automatically."

    def add_arguments(self, parser):
        parser.add_argument("--business-id", type=int, required=True)
        parser.add_argument("--created-by", type=int, default=None)

    def handle(self, *args, **options):
        business = Business.objects.filter(pk=options["business_id"]).first()
        if not business:
            raise CommandError("Business not found.")

        user = None
        if options.get("created_by"):
            user = get_user_model().objects.filter(pk=options["created_by"]).first()

        from inventory.models import MerchProduct

        kind = getattr(business, "business_kind", "") or "general"
        product, product_created = MerchProduct.objects.get_or_create(
            business=business,
            name="Starter sample product",
            defaults={
                "kind": kind,
                "quantity_in_stock": 5,
                "cost_price": Decimal("10000.00"),
                "selling_price": Decimal("15000.00"),
                "category": "Starter sample data",
            },
        )

        cash = record_cash_bank_transaction(
            business=business,
            amount=Decimal("50000.00"),
            direction=CashBankTransaction.Direction.CASH_IN,
            category="Owner capital injection",
            payment_method="cash",
            tx_date=timezone.localdate(),
            description="Starter sample data - opening cash",
            related_sale_reference="starter-sample:opening-cash",
            created_by=user,
        )
        cost = record_company_expense_once(
            business=business,
            amount=Decimal("5000.00"),
            note="Starter sample data - basic operating cost",
            reference="starter-sample:expense",
            created_by=user,
            effective_date=timezone.localdate(),
            meta={"starter_sample_data": True},
        )

        po, po_created = AdminPurchaseOrder.objects.get_or_create(
            business=business,
            supplier_name="Starter sample supplier",
            notes="Starter sample data - removable training purchase order",
            defaults={
                "created_by": user,
                "status": PurchaseOrderStatus.SENT,
                "payment_terms": "Starter sample data only",
            },
        )
        if not po.items.exists():
            AdminPurchaseOrderItem.objects.create(
                po=po,
                product=product,
                quantity=2,
                unit_price=product.cost_price or Decimal("10000.00"),
                line_total=Decimal("20000.00"),
            )
            po.recompute_totals(save=True)

        self.stdout.write(
            self.style.SUCCESS(
                "Starter sample data ready: "
                f"product={'created' if product_created else 'existing'}, "
                f"cash={'created' if cash else 'existing'}, "
                f"cost={'created' if cost else 'existing'}, "
                f"purchase_order={'created' if po_created else 'existing'}."
            )
        )
