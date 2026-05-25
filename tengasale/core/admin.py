from django.contrib import admin

from .models import BusinessSetting


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
