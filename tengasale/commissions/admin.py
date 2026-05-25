from django.contrib import admin

from .models import Commission


@admin.register(Commission)
class CommissionAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "application",
        "role",
        "commission_percent",
        "sale_amount",
        "amount",
        "status",
        "created_at",
        "paid_at",
    )
    list_filter = ("role", "status", "created_at", "paid_at")
    search_fields = (
        "user__username",
        "user__first_name",
        "user__last_name",
        "application__application_number",
        "application__customer_name",
    )
    readonly_fields = ("created_at",)
