# notifications/admin.py
from django.contrib import admin
from notifications.models import (
    Notification,
    WhatsAppPreference,
    NotificationPreference,
    NotificationEvent,
)


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ["audience", "user", "business", "category", "level", "created_at", "read_at"]
    list_filter = ["audience", "category", "level", "read_at", "created_at"]
    search_fields = ["message", "user__username", "user__email", "business__name"]
    readonly_fields = ["created_at", "read_at"]
    date_hierarchy = "created_at"


@admin.register(WhatsAppPreference)
class WhatsAppPreferenceAdmin(admin.ModelAdmin):
    list_display = ["user", "phone_number", "is_enabled", "created_at"]
    list_filter = ["is_enabled", "created_at"]
    search_fields = ["user__username", "user__email", "phone_number"]


@admin.register(NotificationPreference)
class NotificationPreferenceAdmin(admin.ModelAdmin):
    list_display = [
        "user",
        "welcome_emails",
        "instant_sale_email",
        "daily_summary_email",
        "important_alerts_email",
        "high_sales_alerts",
        "updated_at",
    ]
    list_filter = [
        "welcome_emails",
        "instant_sale_email",
        "daily_summary_email",
        "important_alerts_email",
        "high_sales_alerts",
    ]
    search_fields = ["user__username", "user__email"]
    readonly_fields = ["created_at", "updated_at"]


@admin.register(NotificationEvent)
class NotificationEventAdmin(admin.ModelAdmin):
    list_display = ["event_type", "recipient_email", "business", "status", "created_at", "sent_at"]
    list_filter = ["event_type", "status", "created_at", "sent_at", "business"]
    search_fields = ["recipient_email", "business__name", "dedupe_key", "last_error"]
    readonly_fields = ["created_at", "sent_at", "last_error"]
    date_hierarchy = "created_at"

    fieldsets = (
        ("Event Info", {"fields": ("event_type", "business", "recipient_email", "dedupe_key")}),
        ("Status", {"fields": ("status", "created_at", "sent_at", "last_error")}),
        ("Payload", {"fields": ("payload",), "classes": ("collapse",)}),
    )

    def get_queryset(self, request):
        """Optimize queryset with select_related for business."""
        qs = super().get_queryset(request)
        return qs.select_related("business")
