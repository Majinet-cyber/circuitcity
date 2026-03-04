# notifications/admin.py
from django.contrib import admin
from django.utils.html import format_html
from notifications.models import (
    BusinessEmailRecipient,
    DailySummarySettings,
    Notification,
    NotificationEvent,
    NotificationPreference,
    WhatsAppPreference,
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


# ==============================================================================
# Daily Summary — Recipients
# ==============================================================================

class BusinessEmailRecipientInline(admin.TabularInline):
    """Inline editor: add/remove recipients directly on the DailySummarySettings page."""
    model = BusinessEmailRecipient
    extra = 1
    fields = ("email", "name", "is_active")
    verbose_name = "Recipient"
    verbose_name_plural = "Email Recipients"


@admin.register(BusinessEmailRecipient)
class BusinessEmailRecipientAdmin(admin.ModelAdmin):
    list_display = ["email", "name", "business", "is_active", "created_at"]
    list_filter = ["is_active", "created_at", "business"]
    search_fields = ["email", "name", "business__name"]
    list_editable = ["is_active"]
    ordering = ["business__name", "email"]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("business")


# ==============================================================================
# Daily Summary — Settings
# ==============================================================================

@admin.register(DailySummarySettings)
class DailySummarySettingsAdmin(admin.ModelAdmin):
    list_display = [
        "business",
        "vertical_badge",
        "is_enabled",
        "send_hour_display",
        "timezone",
        "last_sent_date",
        "recipient_count",
        "updated_at",
    ]
    list_filter = ["is_enabled", "timezone", "send_hour"]
    search_fields = ["business__name"]
    list_editable = ["is_enabled"]
    readonly_fields = ["last_sent_date", "created_at", "updated_at"]
    ordering = ["business__name"]

    fieldsets = (
        (
            "Business",
            {"fields": ("business",)},
        ),
        (
            "Schedule",
            {
                "fields": ("is_enabled", "send_hour", "timezone"),
                "description": (
                    "The summary fires once per day when the Celery Beat "
                    "'daily-summary-emails' task runs at the configured hour "
                    "in the selected timezone."
                ),
            },
        ),
        (
            "Audit",
            {
                "fields": ("last_sent_date", "created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    inlines = [BusinessEmailRecipientInline]

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("business")
            .prefetch_related("business__daily_summary_recipients")
        )

    @admin.display(description="Vertical")
    def vertical_badge(self, obj):
        kind = getattr(obj.business, "business_kind", None) or "—"
        colours = {
            "gym": "#059669",
            "car_hire": "#7c3aed",
            "phones": "#1a56db",
            "grocery": "#0891b2",
            "pharmacy": "#db2777",
            "clothing": "#d97706",
            "liquor": "#b45309",
            "hardware": "#6b7280",
        }
        colour = colours.get(kind, "#6b7280")
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;border-radius:4px;font-size:11px">{}</span>',
            colour,
            kind,
        )

    @admin.display(description="Send at")
    def send_hour_display(self, obj):
        return f"{obj.send_hour:02d}:00"

    @admin.display(description="Recipients")
    def recipient_count(self, obj):
        count = obj.business.daily_summary_recipients.filter(is_active=True).count()
        return count if count > 0 else format_html(
            '<span style="color:#ef4444">0 — will not send</span>'
        )
