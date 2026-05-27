from datetime import timedelta
from django.contrib import admin
from django.utils import timezone

from .models import (
    SubscriptionPlan,
    BusinessSubscription,
    Invoice,
    InvoiceItem,
    Payment,
    PaymentMethod,
    PaymentTransaction,
    PaymentEvent,
    WebhookEvent,
)


@admin.action(description="Add 7 days to current period / trial")
def add_7_days(modeladmin, request, queryset):
    for sub in queryset:
        anchor = sub.trial_end or sub.current_period_end or timezone.now()
        new_anchor = anchor + timedelta(days=7)
        if sub.status == BusinessSubscription.Status.TRIAL:
            sub.trial_end = new_anchor
            sub.current_period_end = new_anchor
        else:
            sub.current_period_end = new_anchor
        sub.next_billing_date = new_anchor
        sub.save(update_fields=["trial_end", "current_period_end", "next_billing_date", "updated_at"])


@admin.action(description="Reduce 7 days from current period / trial")
def minus_7_days(modeladmin, request, queryset):
    for sub in queryset:
        anchor = sub.trial_end or sub.current_period_end or timezone.now()
        new_anchor = anchor - timedelta(days=7)
        if sub.status == BusinessSubscription.Status.TRIAL:
            sub.trial_end = new_anchor
            sub.current_period_end = new_anchor
        else:
            sub.current_period_end = new_anchor
        sub.next_billing_date = new_anchor
        sub.save(update_fields=["trial_end", "current_period_end", "next_billing_date", "updated_at"])


@admin.register(BusinessSubscription)
class BusinessSubscriptionAdmin(admin.ModelAdmin):
    list_display = ("business", "plan", "status", "trial_end", "current_period_end", "next_billing_date", "started_at")
    list_filter = ("status", "plan")
    search_fields = ("business__name", "plan__name", "plan__code")
    actions = [add_7_days, minus_7_days]


@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "amount", "currency", "interval", "is_active", "sort_order")
    list_filter = ("is_active", "interval")
    search_fields = ("name", "code")


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ("number", "business", "status", "total", "currency", "issue_date", "due_date")
    list_filter = ("status",)
    search_fields = ("number", "business__name")


@admin.register(InvoiceItem)
class InvoiceItemAdmin(admin.ModelAdmin):
    list_display = ("invoice", "description", "qty", "unit_price", "line_total")


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("business", "invoice", "provider", "amount", "currency", "status", "created_at")
    list_filter = ("provider", "status")
    search_fields = ("business__name", "invoice__number", "reference", "external_id")


@admin.register(PaymentMethod)
class PaymentMethodAdmin(admin.ModelAdmin):
    list_display = ("business", "kind", "label", "is_default")


@admin.register(WebhookEvent)
class WebhookEventAdmin(admin.ModelAdmin):
    list_display = ("provider", "event_type", "external_id", "received_at", "processed")
    list_filter = ("provider", "processed")
    search_fields = ("external_id", "event_type")


@admin.register(PaymentTransaction)
class PaymentTransactionAdmin(admin.ModelAdmin):
    list_display = ("tx_ref", "business", "provider", "amount", "currency", "status", "created_at")
    list_filter = ("provider", "status", "payment_method")
    search_fields = ("tx_ref", "business__name", "charge_id")
    readonly_fields = ("created_at", "updated_at", "raw_webhook_payload")
    
    def has_add_permission(self, request):
        # Transactions should only be created via webhooks
        return False


@admin.register(PaymentEvent)
class PaymentEventAdmin(admin.ModelAdmin):
    list_display = ("idempotency_key", "provider", "reference", "status", "signature_valid", "received_at", "processed_at")
    list_filter = ("provider", "status", "signature_valid")
    search_fields = ("idempotency_key", "event_id", "reference")
    readonly_fields = ("received_at", "processed_at", "payload_json")
    
    fieldsets = (
        ("Event Info", {
            "fields": ("provider", "event_id", "idempotency_key", "reference")
        }),
        ("Status", {
            "fields": ("status", "signature_valid", "error_message")
        }),
        ("Timestamps", {
            "fields": ("received_at", "processed_at")
        }),
        ("Raw Data", {
            "fields": ("payload_json",),
            "classes": ("collapse",)
        }),
    )
    
    def has_add_permission(self, request):
        # Events should only be created via webhooks
        return False
