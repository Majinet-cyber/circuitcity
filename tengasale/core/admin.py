from django.contrib import admin

from .models import AuditLog, BusinessSetting, QueueRule


@admin.register(BusinessSetting)
class BusinessSettingAdmin(admin.ModelAdmin):
    list_display = (
        "merchant_commission_percent",
        "manager_commission_percent",
        "loan_multiplier",
        "spin_enabled",
        "updated_at",
    )
    readonly_fields = ("updated_at",)


@admin.register(QueueRule)
class QueueRuleAdmin(admin.ModelAdmin):
    list_display = (
        "country",
        "cooldown_minutes",
        "max_active_applications",
        "polling_interval_seconds",
        "inactive_pause_minutes",
        "waiting_edit_grace_minutes",
        "updated_at",
    )
    readonly_fields = ("updated_at",)


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("action", "user", "object_type", "object_id", "ip_address", "timestamp")
    list_filter = ("action", "object_type", "timestamp")
    search_fields = ("user__username", "object_id", "action")
    readonly_fields = ("user", "action", "object_type", "object_id", "detail", "ip_address", "timestamp")
    ordering = ("-timestamp",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
