# inventory/admin_clothing_barcode.py
"""
Django admin for ClothingBarcodeUnit model.
"""
from django.contrib import admin
from django.utils.html import format_html

from .models_clothing_barcode import ClothingBarcodeUnit


@admin.register(ClothingBarcodeUnit)
class ClothingBarcodeUnitAdmin(admin.ModelAdmin):
    """Admin for clothing barcode units"""

    list_display = [
        "barcode",
        "size_display",
        "category",
        "status_badge",
        "selling_price",
        "cost_price",
        "profit_display",
        "location",
        "received_at",
        "sold_at",
    ]

    list_filter = [
        "status",
        "is_active",
        "category",
        "subcategory",
        "location",
        "received_at",
        "sold_at",
    ]

    search_fields = [
        "barcode",
        "size",
        "category",
        "subcategory",
        "brand",
        "color",
    ]

    readonly_fields = [
        "created_at",
        "updated_at",
        "created_by",
        "archived_at",
        "archived_by",
        "profit_display",
    ]

    fieldsets = (
        ("Barcode & Identification", {"fields": ("barcode", "business", "location", "product")}),
        ("Clothing Attributes", {"fields": ("category", "subcategory", "size", "color", "brand")}),
        ("Pricing", {"fields": ("cost_price", "selling_price", "profit_display")}),
        ("Status", {"fields": ("status", "received_at", "sold_at")}),
        ("Archive", {"fields": ("is_active", "archived_at", "archived_by"), "classes": ("collapse",)}),
        ("Audit", {"fields": ("created_at", "updated_at", "created_by"), "classes": ("collapse",)}),
    )

    def size_display(self, obj):
        """Display size with icon"""
        return format_html('<span style="font-weight:600;">Size {}</span>', obj.size)

    size_display.short_description = "Size"

    def status_badge(self, obj):
        """Display status with color badge"""
        if obj.status == "IN_STOCK":
            color = "#10b981"  # green
            icon = "✓"
        else:
            color = "#6b7280"  # gray
            icon = "✓"

        return format_html(
            '<span style="background:{};color:white;padding:4px 12px;border-radius:12px;font-size:11px;font-weight:600;">{} {}</span>',
            color,
            icon,
            obj.get_status_display(),
        )

    status_badge.short_description = "Status"

    def profit_display(self, obj):
        """Display profit with color"""
        profit = obj.profit
        if profit > 0:
            color = "#10b981"  # green
        elif profit < 0:
            color = "#ef4444"  # red
        else:
            color = "#6b7280"  # gray

        return format_html('<span style="color:{};font-weight:600;">MWK {:,.2f}</span>', color, profit)

    profit_display.short_description = "Profit"

    def get_queryset(self, request):
        """Optimize queryset with select_related"""
        qs = super().get_queryset(request)
        return qs.select_related("business", "location", "product", "created_by", "archived_by")

    def has_delete_permission(self, request, obj=None):
        """Prevent hard deletes - use archive instead"""
        return False
