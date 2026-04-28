# integrations/admin.py
from django.contrib import admin

from .models import CreditSignal, DeveloperIntegration, WebhookEvent


@admin.register(DeveloperIntegration)
class DeveloperIntegrationAdmin(admin.ModelAdmin):
    list_display = ("name", "integration_type", "business", "is_active", "created_at")
    list_filter = ("integration_type", "is_active", "created_at")
    search_fields = ("name", "business__name")
    readonly_fields = ("created_at", "updated_at")
    ordering = ("-created_at",)


@admin.register(WebhookEvent)
class WebhookEventAdmin(admin.ModelAdmin):
    list_display = ("source", "event_type", "status", "received_at", "business")
    list_filter = ("source", "event_type", "status", "received_at")
    search_fields = ("source", "event_type", "error_message")
    readonly_fields = ("received_at", "processed_at", "payload")
    ordering = ("-received_at",)
    date_hierarchy = "received_at"


@admin.register(CreditSignal)
class CreditSignalAdmin(admin.ModelAdmin):
    list_display = ("signal_type", "customer_ref", "source", "score_impact", "occurred_at", "business")
    list_filter = ("signal_type", "source", "occurred_at", "created_at")
    search_fields = ("customer_ref", "source")
    readonly_fields = ("created_at", "payload")
    ordering = ("-occurred_at",)
    date_hierarchy = "occurred_at"
