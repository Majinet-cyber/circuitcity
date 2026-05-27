from django.contrib import admin
from django.utils.html import format_html

from .models import PaymentContract, PaymentTransaction
from .payment_providers import get_integration_status


@admin.register(PaymentContract)
class PaymentContractAdmin(admin.ModelAdmin):
    list_display = (
        "contract_number", "payg_number", "customer_name",
        "masked_phone_display", "total_amount", "amount_paid",
        "progress_bar", "status", "due_date", "created_at",
    )
    list_filter = ("status", "term_months", "created_at")
    search_fields = ("contract_number", "payg_number", "customer_name", "customer_phone", "customer_national_id")
    readonly_fields = ("contract_number", "payg_number", "progress_percent", "created_at", "updated_at")
    ordering = ("-created_at",)

    fieldsets = (
        ("Contract Identity", {
            "fields": ("contract_number", "payg_number", "status"),
        }),
        ("Customer", {
            "fields": ("customer_name", "customer_phone", "customer_national_id", "device_model"),
        }),
        ("Financials", {
            "fields": (
                "total_amount", "deposit_paid", "amount_paid", "progress_percent",
                "daily_price", "thirty_day_price", "term_months",
            ),
        }),
        ("Dates", {
            "fields": ("start_date", "due_date", "lock_date"),
        }),
        ("Early Settlement Discounts", {
            "fields": (
                "early_settlement_3m_discount",
                "early_settlement_6m_discount",
                "early_settlement_9m_discount",
            ),
            "classes": ("collapse",),
        }),
        ("Links", {
            "fields": ("financing_contract",),
            "classes": ("collapse",),
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )

    def masked_phone_display(self, obj):
        return obj.masked_phone
    masked_phone_display.short_description = "Phone"

    def progress_bar(self, obj):
        pct = obj.progress_percent
        color = "#168a45" if pct >= 80 else "#ff6a00" if pct >= 40 else "#d93025"
        return format_html(
            '<div style="width:100px;background:#eee;border-radius:4px;overflow:hidden;">'
            '<div style="width:{pct}%;background:{color};height:12px;"></div>'
            '</div> {pct}%',
            pct=pct, color=color,
        )
    progress_bar.short_description = "Progress"


@admin.register(PaymentTransaction)
class PaymentTransactionAdmin(admin.ModelAdmin):
    list_display = (
        "internal_reference", "payment_contract", "provider",
        "amount", "currency", "masked_phone_display",
        "status", "paid_at", "created_at",
    )
    list_filter = ("status", "provider", "currency", "created_at")
    search_fields = ("internal_reference", "provider_reference", "phone", "payment_contract__contract_number")
    readonly_fields = ("internal_reference", "raw_response", "created_at", "updated_at")
    ordering = ("-created_at",)

    def masked_phone_display(self, obj):
        return obj.masked_phone
    masked_phone_display.short_description = "Phone"
