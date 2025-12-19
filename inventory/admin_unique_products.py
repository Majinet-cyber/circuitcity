# inventory/admin_unique_products.py
"""
Django Admin registration for Unique Products models.
"""
from django.contrib import admin
from django.utils.html import format_html
from .models_unique_products import UniqueProduct, UniqueProductStockIn, UniqueSale


@admin.register(UniqueProduct)
class UniqueProductAdmin(admin.ModelAdmin):
    list_display = [
        "barcode_display",
        "name",
        "vertical",
        "quantity",
        "unit",
        "selling_price",
        "stock_value_display",
        "is_active",
        "business",
    ]
    list_filter = ["vertical", "is_active", "business"]
    search_fields = ["name", "barcode", "business__name"]
    readonly_fields = ["created_at", "updated_at", "created_by"]
    
    fieldsets = (
        ("Product Information", {
            "fields": ("business", "vertical", "barcode", "name", "description")
        }),
        ("Stock", {
            "fields": ("quantity", "unit")
        }),
        ("Pricing", {
            "fields": ("cost_price", "selling_price")
        }),
        ("Metadata", {
            "fields": ("is_active", "created_at", "updated_at", "created_by"),
            "classes": ("collapse",)
        }),
    )
    
    def barcode_display(self, obj):
        return format_html(
            '<code style="background:#eef2ff;padding:4px 8px;border-radius:4px;font-weight:700;color:#667eea;">{}</code>',
            obj.barcode
        )
    barcode_display.short_description = "Barcode"
    
    def stock_value_display(self, obj):
        value = obj.stock_value_cost
        color = "#10b981" if value > 0 else "#9ca3af"
        return format_html(
            '<span style="color:{};font-weight:600;">K{:,.0f}</span>',
            color, value
        )
    stock_value_display.short_description = "Stock Value"


@admin.register(UniqueProductStockIn)
class UniqueProductStockInAdmin(admin.ModelAdmin):
    list_display = [
        "added_at",
        "product",
        "quantity",
        "cost_price",
        "selling_price",
        "supplier",
        "business",
    ]
    list_filter = ["business", "added_at"]
    search_fields = ["product__name", "product__barcode", "supplier"]
    readonly_fields = ["added_at", "added_by"]
    
    fieldsets = (
        ("Stock In Details", {
            "fields": ("business", "product", "quantity", "cost_price", "selling_price")
        }),
        ("Additional Info", {
            "fields": ("supplier", "notes")
        }),
        ("Metadata", {
            "fields": ("added_at", "added_by"),
            "classes": ("collapse",)
        }),
    )


@admin.register(UniqueSale)
class UniqueSaleAdmin(admin.ModelAdmin):
    list_display = [
        "sold_at",
        "product",
        "quantity",
        "unit_price",
        "total_display",
        "profit_display",
        "payment_method",
        "sold_by",
        "business",
    ]
    list_filter = ["business", "payment_method", "sold_at", "is_deleted"]
    search_fields = ["product__name", "product__barcode", "customer_name", "customer_phone"]
    readonly_fields = ["sold_at", "sold_by", "total_amount", "total_cost", "profit"]
    
    fieldsets = (
        ("Sale Details", {
            "fields": ("business", "product", "quantity", "unit_price", "unit_cost")
        }),
        ("Calculated Values", {
            "fields": ("total_amount", "total_cost", "profit")
        }),
        ("Payment", {
            "fields": ("payment_method",)
        }),
        ("Customer (Optional)", {
            "fields": ("customer_name", "customer_phone"),
            "classes": ("collapse",)
        }),
        ("Metadata", {
            "fields": ("sold_at", "sold_by", "is_deleted"),
            "classes": ("collapse",)
        }),
    )
    
    def total_display(self, obj):
        return format_html(
            '<span style="color:#10b981;font-weight:600;">K{:,.0f}</span>',
            obj.total_amount
        )
    total_display.short_description = "Total"
    
    def profit_display(self, obj):
        color = "#10b981" if obj.profit >= 0 else "#ef4444"
        return format_html(
            '<span style="color:{};font-weight:600;">K{:,.0f}</span>',
            color, obj.profit
        )
    profit_display.short_description = "Profit"

