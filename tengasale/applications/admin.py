from django.contrib import admin
from django.utils.html import format_html

from .models import FinancingApplication


@admin.register(FinancingApplication)
class FinancingApplicationAdmin(admin.ModelAdmin):
    list_display = (
        "application_number",
        "customer_name",
        "customer_phone",
        "deal",
        "calculated_total_loan",
        "created_by",
        "reviewed_by",
        "status_badge",
        "submitted_at",
        "reviewed_at",
    )
    list_filter = (
        "status",
        "review_status",
        "region",
        "deal__brand",
        "created_at",
        "submitted_at",
    )
    search_fields = (
        "application_number",
        "customer_name",
        "customer_phone",
        "national_id",
        "imei_number",
        "created_by__username",
        "reviewed_by__username",
    )
    readonly_fields = (
        "application_number", "created_at",
        "submitted_at", "reviewed_at",
    )
    ordering = ("-submitted_at",)
    date_hierarchy = "submitted_at"

    def status_badge(self, obj):
        colours = {
            "draft": "#7a828c",
            "pending_review": "#ff6a00",
            "under_review": "#0277bd",
            "approved": "#168a45",
            "rejected": "#d93025",
            "sent_back": "#8b5cf6",
            "completed": "#0d47a1",
            "contract_complete": "#0d47a1",
        }
        colour = colours.get(obj.status, "#7a828c")
        return format_html(
            '<span style="display:inline-block;padding:2px 8px;border-radius:6px;'
            'background:{colour};color:#fff;font-size:11px;font-weight:700;">{label}</span>',
            colour=colour,
            label=obj.get_status_display(),
        )
    status_badge.short_description = "Status"
