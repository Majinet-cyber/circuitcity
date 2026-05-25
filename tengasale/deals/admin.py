from django.contrib import admin
from .models import DeviceBrand, DeviceDeal


@admin.register(DeviceBrand)
class DeviceBrandAdmin(admin.ModelAdmin):
    list_display = ("name", "is_active")
    search_fields = ("name",)


@admin.register(DeviceDeal)
class DeviceDealAdmin(admin.ModelAdmin):
    list_display = (
        "brand",
        "model_name",
        "specs",
        "min_cash_price",
        "max_cash_price",
        "default_cash_price",
        "deposit_percent",
        "loan_multiplier",
        "term_months",
        "is_active",
    )
    list_filter = ("brand", "is_active")
    search_fields = ("model_name", "specs")
    list_editable = (
        "min_cash_price",
        "max_cash_price",
        "default_cash_price",
        "deposit_percent",
        "loan_multiplier",
        "term_months",
        "is_active",
    )
