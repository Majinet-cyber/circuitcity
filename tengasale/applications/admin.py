from django.contrib import admin
from .models import FinancingApplication


@admin.register(FinancingApplication)
class FinancingApplicationAdmin(admin.ModelAdmin):
    list_display = (
        "application_number",
        "customer_name",
        "customer_phone",
        "deal",
        "selected_cash_price",
        "calculated_total_loan",
        "created_by",
        "status",
        "created_at",
    )
    list_filter = ("status", "region", "deal__brand", "created_at")
    search_fields = (
        "application_number",
        "customer_name",
        "customer_phone",
        "national_id",
        "imei_number",
    )
    readonly_fields = ("application_number", "created_at", "submitted_at", "reviewed_at")
