from django.contrib import admin

from .models import CreditRiskAssessment, CustomerIdentityProfile, DeviceCheck, ExternalCheck, FraudCheck


@admin.register(CustomerIdentityProfile)
class CustomerIdentityProfileAdmin(admin.ModelAdmin):
    list_display = ["application", "verification_status", "emajinet_id", "created_at"]
    list_filter = ["verification_status"]
    search_fields = ["application__application_number", "application__customer_name"]
    readonly_fields = ["national_id_hash", "phone_hash", "created_at"]


@admin.register(CreditRiskAssessment)
class CreditRiskAssessmentAdmin(admin.ModelAdmin):
    list_display = [
        "application", "risk_band", "final_score", "recommended_deposit_percent",
        "affordability_score", "identity_score", "created_at",
    ]
    list_filter = ["risk_band"]
    search_fields = ["application__application_number", "application__customer_name"]
    readonly_fields = ["created_at", "updated_at"]


@admin.register(ExternalCheck)
class ExternalCheckAdmin(admin.ModelAdmin):
    list_display = ["application", "provider", "status", "request_reference", "created_at"]
    list_filter = ["provider", "status"]
    search_fields = ["application__application_number"]
    readonly_fields = ["created_at"]


@admin.register(FraudCheck)
class FraudCheckAdmin(admin.ModelAdmin):
    list_display = [
        "application", "risk_level", "recommended_action",
        "resolution_status", "checked_by", "created_at",
    ]
    list_filter = ["risk_level", "recommended_action", "resolution_status"]
    search_fields = ["application__application_number", "application__customer_name"]
    readonly_fields = ["national_id_hash", "phone_hash", "created_at", "result"]
    actions = ["mark_cleared", "mark_hq_override"]

    @admin.action(description="Mark selected checks as Cleared")
    def mark_cleared(self, request, queryset):
        queryset.update(resolution_status=FraudCheck.RESOLUTION_CLEARED, resolved_by=request.user)

    @admin.action(description="Mark selected checks as HQ Override (approved)")
    def mark_hq_override(self, request, queryset):
        queryset.update(resolution_status=FraudCheck.RESOLUTION_HQ_OVERRIDE, resolved_by=request.user)


@admin.register(DeviceCheck)
class DeviceCheckAdmin(admin.ModelAdmin):
    list_display = ["imei", "provider", "status", "warranty_status", "lock_eligible", "checked_at"]
    list_filter = ["provider", "status", "warranty_status", "lock_eligible"]
    search_fields = ["imei", "application__application_number"]
    readonly_fields = ["checked_at"]
