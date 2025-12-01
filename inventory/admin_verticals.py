# inventory/admin_verticals.py
"""
Admin registration for verticals-specific models (Liquor, Gym, Clothing).
"""
from __future__ import annotations

from django.contrib import admin
from django.utils.html import format_html

try:
    from .models_verticals import (
        # Liquor
        LiquorSale, LiquorCredit, LiquorCreditPayment, LiquorStockEditRequest,
        LiquorExpense, LiquorWalletEntry,
        # Gym
        GymMember, GymPayment, GymMemberLog, GymSettings, GymWalletEntry,
        # Clothing
        ClothingSale, ClothingProductLog,
    )
except ImportError:
    # Models not yet migrated
    LiquorSale = LiquorCredit = LiquorCreditPayment = LiquorStockEditRequest = None
    LiquorExpense = LiquorWalletEntry = None
    GymMember = GymPayment = GymMemberLog = GymSettings = GymWalletEntry = None
    ClothingSale = ClothingProductLog = None


# ==============================================================================
# LIQUOR ADMINS
# ==============================================================================

if LiquorSale:
    @admin.register(LiquorSale)
    class LiquorSaleAdmin(admin.ModelAdmin):
        list_display = ("product", "unit", "quantity", "unit_price", "total_price", "sale_type", "is_credit", "sold_at", "sold_by")
        list_filter = ("sale_type", "unit", "is_credit", "sold_at")
        search_fields = ("product__name", "sold_by__username")
        date_hierarchy = "sold_at"
        ordering = ("-sold_at",)
        list_select_related = ("product", "sold_by", "business")
        autocomplete_fields = ("product", "sold_by")
        list_per_page = 50


if LiquorCredit:
    @admin.register(LiquorCredit)
    class LiquorCreditAdmin(admin.ModelAdmin):
        list_display = ("customer_name", "customer_phone", "amount", "amount_paid", "balance", "status", "created_at")
        list_filter = ("status", "created_at")
        search_fields = ("customer_name", "customer_phone")
        date_hierarchy = "created_at"
        ordering = ("-created_at",)
        list_select_related = ("business", "created_by")
        autocomplete_fields = ("created_by",)
        list_per_page = 50
        
        @admin.display(description="Balance")
        def balance(self, obj):
            return obj.balance


if LiquorCreditPayment:
    @admin.register(LiquorCreditPayment)
    class LiquorCreditPaymentAdmin(admin.ModelAdmin):
        list_display = ("credit", "amount", "transaction_id", "status", "paid_by", "created_at", "reviewed_by")
        list_filter = ("status", "created_at")
        search_fields = ("credit__customer_name", "transaction_id", "paid_by__username")
        date_hierarchy = "created_at"
        ordering = ("-created_at",)
        list_select_related = ("credit", "paid_by", "reviewed_by")
        autocomplete_fields = ("credit", "paid_by", "reviewed_by")
        list_per_page = 50
        readonly_fields = ("proof_file",)
        
        def has_add_permission(self, request):
            # Payments should be created through the app, not admin
            return request.user.is_superuser


if LiquorStockEditRequest:
    @admin.register(LiquorStockEditRequest)
    class LiquorStockEditRequestAdmin(admin.ModelAdmin):
        list_display = ("product", "status", "requested_by", "created_at", "reviewed_by", "reviewed_at")
        list_filter = ("status", "created_at")
        search_fields = ("product__name", "requested_by__username")
        date_hierarchy = "created_at"
        ordering = ("-created_at",)
        list_select_related = ("product", "requested_by", "reviewed_by", "business")
        autocomplete_fields = ("product", "requested_by", "reviewed_by")
        list_per_page = 50


if LiquorExpense:
    @admin.register(LiquorExpense)
    class LiquorExpenseAdmin(admin.ModelAdmin):
        list_display = ("description", "amount", "category", "created_at", "created_by")
        list_filter = ("category", "created_at")
        search_fields = ("description", "category")
        date_hierarchy = "created_at"
        ordering = ("-created_at",)
        list_select_related = ("business", "created_by")
        list_per_page = 50


if LiquorWalletEntry:
    @admin.register(LiquorWalletEntry)
    class LiquorWalletEntryAdmin(admin.ModelAdmin):
        list_display = ("description", "entry_type", "amount", "created_at", "created_by")
        list_filter = ("entry_type", "created_at")
        search_fields = ("description",)
        date_hierarchy = "created_at"
        ordering = ("-created_at",)
        list_select_related = ("business", "created_by")
        list_per_page = 50


# ==============================================================================
# GYM ADMINS
# ==============================================================================

if GymMember:
    @admin.register(GymMember)
    class GymMemberAdmin(admin.ModelAdmin):
        list_display = ("name", "phone", "email", "is_active", "is_archived", "joined_at", "membership_status")
        list_filter = ("is_active", "is_archived", "joined_at")
        search_fields = ("name", "phone", "email")
        date_hierarchy = "joined_at"
        ordering = ("-joined_at",)
        list_select_related = ("business", "archived_by")
        autocomplete_fields = ("archived_by",)
        list_per_page = 50
        
        @admin.display(description="Status")
        def membership_status(self, obj):
            status = obj.membership_status()
            if status == "Active":
                return format_html('<span style="color: green;">✓ Active</span>')
            else:
                return format_html('<span style="color: red;">✗ In Arrears</span>')


if GymPayment:
    @admin.register(GymPayment)
    class GymPaymentAdmin(admin.ModelAdmin):
        list_display = ("member", "amount", "start_date", "end_date", "is_active", "paid_at", "paid_by")
        list_filter = ("is_active", "paid_at", "start_date")
        search_fields = ("member__name", "member__phone")
        date_hierarchy = "paid_at"
        ordering = ("-paid_at",)
        list_select_related = ("member", "paid_by")
        autocomplete_fields = ("member", "paid_by")
        list_per_page = 50


if GymMemberLog:
    @admin.register(GymMemberLog)
    class GymMemberLogAdmin(admin.ModelAdmin):
        list_display = ("member", "action", "performed_by", "created_at")
        list_filter = ("action", "created_at")
        search_fields = ("member__name",)
        date_hierarchy = "created_at"
        ordering = ("-created_at",)
        list_select_related = ("member", "performed_by")
        list_per_page = 50
        
        def has_add_permission(self, request):
            # Logs are created automatically, not manually
            return False


if GymSettings:
    @admin.register(GymSettings)
    class GymSettingsAdmin(admin.ModelAdmin):
        list_display = ("business", "support_phone", "support_email", "default_membership_price")
        search_fields = ("business__name",)
        list_select_related = ("business",)


if GymWalletEntry:
    @admin.register(GymWalletEntry)
    class GymWalletEntryAdmin(admin.ModelAdmin):
        list_display = ("description", "entry_type", "amount", "created_at", "created_by")
        list_filter = ("entry_type", "created_at")
        search_fields = ("description",)
        date_hierarchy = "created_at"
        ordering = ("-created_at",)
        list_select_related = ("business", "created_by")
        list_per_page = 50


# ==============================================================================
# CLOTHING ADMINS
# ==============================================================================

if ClothingSale:
    @admin.register(ClothingSale)
    class ClothingSaleAdmin(admin.ModelAdmin):
        list_display = ("product", "quantity", "unit_price", "total_price", "sold_at", "sold_by")
        list_filter = ("sold_at",)
        search_fields = ("product__name", "sold_by__username")
        date_hierarchy = "sold_at"
        ordering = ("-sold_at",)
        list_select_related = ("product", "sold_by", "business")
        autocomplete_fields = ("product", "sold_by")
        list_per_page = 50


if ClothingProductLog:
    @admin.register(ClothingProductLog)
    class ClothingProductLogAdmin(admin.ModelAdmin):
        list_display = ("product", "action", "performed_by", "created_at")
        list_filter = ("action", "created_at")
        search_fields = ("product__name",)
        date_hierarchy = "created_at"
        ordering = ("-created_at",)
        list_select_related = ("product", "performed_by")
        list_per_page = 50
        
        def has_add_permission(self, request):
            # Logs are created automatically, not manually
            return False

