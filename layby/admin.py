# layby/admin.py
from __future__ import annotations

from decimal import Decimal
from django.contrib import admin

from .models import LaybyOrder, LaybyPayment


# ---------- Inlines ----------
class LaybyPaymentInline(admin.TabularInline):
    model = LaybyPayment
    extra = 0
    fields = ("amount", "method", "tx_ref", "received_at", "received_by")
    readonly_fields = ("received_at",)
    ordering = ("-id",)


# ---------- LaybyOrder ----------
@admin.register(LaybyOrder)
class LaybyOrderAdmin(admin.ModelAdmin):
    """
    Admin tuned to the current LaybyOrder model (ref, customer, id_number, item_name, sku,
    term_months, total_price, deposit_amount, status, created_by, created_at/updated_at).
    Includes computed amount_paid and balance, and inline payments.
    """
    list_display = (
        "ref",
        "customer_name",
        "customer_phone",
        "id_number",
        "item_name",
        "sku",
        "status",
        "term_months",
        "total_price",
        "deposit_amount",
        "amount_paid_admin",
        "balance_admin",
        "created_by",
        "created_at",
    )
    list_filter = ("status", "created_by", "created_at")
    search_fields = ("ref", "customer_name", "customer_phone", "id_number", "sku", "item_name")
    ordering = ("-id",)
    inlines = [LaybyPaymentInline]
    readonly_fields = ("created_at", "updated_at", "amount_paid_admin", "balance_admin")

    fieldsets = (
        ("Identifiers", {"fields": ("ref", "status", "created_by")}),
        ("Customer", {"fields": ("customer_name", "customer_phone", "id_number", "id_photo",
                                 "kin1_name", "kin1_phone", "kin2_name", "kin2_phone")}),
        ("Product", {"fields": ("item_name", "sku")}),
        ("Terms & Pricing", {"fields": ("term_months", "total_price", "deposit_amount",
                                        "amount_paid_admin", "balance_admin")}),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )

    @admin.display(description="Amount Paid")
    def amount_paid_admin(self, obj: LaybyOrder) -> Decimal:
        return obj.amount_paid

    @admin.display(description="Balance")
    def balance_admin(self, obj: LaybyOrder) -> Decimal:
        return obj.balance


# ---------- LaybyPayment ----------
@admin.register(LaybyPayment)
class LaybyPaymentAdmin(admin.ModelAdmin):
    list_display = ("order", "amount", "method", "tx_ref", "received_at", "received_by")
    list_filter = ("method", "received_at", "received_by")
    search_fields = ("order__ref", "tx_ref")
    ordering = ("-id",)
    readonly_fields = ("received_at",)


