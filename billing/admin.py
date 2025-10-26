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


