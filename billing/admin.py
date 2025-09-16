# billing/admin.py
from __future__ import annotations

import json
from django.contrib import admin
from .models import (
    SubscriptionPlan,
    BusinessSubscription,
    Invoice,
    InvoiceItem,
    Payment,
    PaymentMethod,
    WebhookEvent,
)

@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "amount", "currency", "interval", "is_active", "sort_order")
    list_filter = ("interval", "is_active", "currency")
    search_fields = ("code", "name")
    ordering = ("sort_order", "amount", "name")


@admin.register(BusinessSubscription)
class BusinessSubscriptionAdmin(admin.ModelAdmin):
    list_display = ("business", "plan", "status", "payment_method",
                    "current_period_start", "current_period_end", "next_billing_date", "last_payment_at")
    list_filter = ("status", "payment_method", "plan")
    search_fields = ("business__name",)
    autocomplete_fields = ("plan",)
    date_hierarchy = "current_period_start"


class InvoiceItemInline(admin.TabularInline):
    model = InvoiceItem
    extra = 0
    readonly_fields = ("line_total",)


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ("number", "business", "issue_date", "due_date", "total", "status", "paid_at")
    list_filter = ("status", "currency")
    search_fields = ("number", "business__name")
    date_hierarchy = "issue_date"
    inlines = [InvoiceItemInline]
    readonly_fields = ("subtotal", "tax_amount", "total", "created_at", "updated_at")


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("invoice", "business", "provider", "amount", "currency", "status", "processed_at", "created_at")
    list_filter = ("provider", "status", "currency")
    search_fields = ("invoice__number", "business__name", "reference", "external_id")
    date_hierarchy = "created_at"


@admin.register(PaymentMethod)
class PaymentMethodAdmin(admin.ModelAdmin):
    list_display = ("business", "kind", "label", "is_default", "created_at")
    list_filter = ("kind", "is_default")
    search_fields = ("business__name", "label")


# ---------- Webhook Events ----------
@admin.register(WebhookEvent)
class WebhookEventAdmin(admin.ModelAdmin):
    list_display = ("provider", "event_type", "external_id", "received_at", "processed")
    list_filter = ("provider", "processed")
    search_fields = ("provider", "event_type", "external_id")
    date_hierarchy = "received_at"

    # Show a pretty JSON view of payload
    readonly_fields = ("provider", "event_type", "external_id", "received_at", "processed", "payload_pretty")
    fields = ("provider", "event_type", "external_id", "received_at", "processed", "payload_pretty")

    def payload_pretty(self, obj):
        try:
            return json.dumps(obj.payload, indent=2, sort_keys=True, ensure_ascii=False)
        except Exception:
            return str(obj.payload)

    payload_pretty.short_description = "Payload"
