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
        LiquorSale,
        LiquorCredit,
        LiquorCreditPayment,
        LiquorStockEditRequest,
        LiquorExpense,
        LiquorWalletEntry,
        LiquorShift,
        LiquorShiftStock,
        # Gym
        GymMember,
        GymPayment,
        GymMemberLog,
        GymSettings,
        GymWalletEntry,
        GymTrainer,
        GymCheckIn,
        # Clothing
        ClothingSale,
        ClothingProductLog,
        # Cement
        CementSale,
        CementCost,
        # Groceries
        GrocerySale,
    )
except ImportError:
    # Models not yet migrated
    LiquorSale = LiquorCredit = LiquorCreditPayment = LiquorStockEditRequest = None
    LiquorExpense = LiquorWalletEntry = LiquorShift = LiquorShiftStock = None
    GymMember = GymPayment = GymMemberLog = GymSettings = GymWalletEntry = GymTrainer = GymCheckIn = None
    ClothingSale = ClothingProductLog = None
    CementSale = CementCost = None
    GrocerySale = None


# ==============================================================================
# LIQUOR ADMINS
# ==============================================================================

if LiquorSale:

    @admin.register(LiquorSale)
    class LiquorSaleAdmin(admin.ModelAdmin):
        list_display = (
            "product",
            "unit",
            "quantity",
            "unit_price",
            "total_price",
            "sale_type",
            "is_credit",
            "sold_at",
            "sold_by",
        )
        list_filter = ("sale_type", "unit", "is_credit", "sold_at")
        search_fields = ("product__name", "sold_by__username")
        date_hierarchy = "sold_at"
        ordering = ("-sold_at",)
        list_select_related = ("product", "sold_by", "business")
        raw_id_fields = ("product", "sold_by")
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
        raw_id_fields = ("product", "requested_by", "reviewed_by")
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


if LiquorShift:

    @admin.register(LiquorShift)
    class LiquorShiftAdmin(admin.ModelAdmin):
        list_display = (
            "id",
            "barman",
            "status",
            "started_at",
            "ended_at",
            "total_sales_amount",
            "total_profit_amount",
            "missing_stock_value",
        )
        list_filter = ("status", "started_at")
        search_fields = ("barman__username", "barman__first_name", "barman__last_name")
        date_hierarchy = "started_at"
        ordering = ("-started_at",)
        list_select_related = ("business", "location", "barman", "created_by")
        raw_id_fields = ("barman", "created_by", "location")
        readonly_fields = (
            "started_at",
            "ended_at",
            "total_sales_amount",
            "total_cost_amount",
            "total_profit_amount",
            "total_credit_amount",
            "total_free_amount",
            "missing_stock_value",
        )
        list_per_page = 50

        fieldsets = (
            ("Shift Info", {"fields": ("business", "location", "barman", "created_by", "status")}),
            ("Timing", {"fields": ("started_at", "ended_at")}),
            (
                "Financials",
                {
                    "fields": (
                        "total_sales_amount",
                        "total_cost_amount",
                        "total_profit_amount",
                        "total_credit_amount",
                        "total_free_amount",
                        "missing_stock_value",
                    )
                },
            ),
            ("Notes", {"fields": ("opening_notes", "closing_notes")}),
        )


if LiquorShiftStock:

    @admin.register(LiquorShiftStock)
    class LiquorShiftStockAdmin(admin.ModelAdmin):
        list_display = ("shift", "product", "snapshot_type", "bottles_count", "shots_count", "recorded_at")
        list_filter = ("snapshot_type", "recorded_at")
        search_fields = ("product__name", "shift__id")
        date_hierarchy = "recorded_at"
        ordering = ("-recorded_at",)
        list_select_related = ("shift", "product", "recorded_by")
        raw_id_fields = ("shift", "product", "recorded_by")
        list_per_page = 100


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


if GymTrainer:

    @admin.register(GymTrainer)
    class GymTrainerAdmin(admin.ModelAdmin):
        list_display = ("name", "phone", "email", "business", "is_active", "joined_at")
        list_filter = ("is_active", "joined_at", "business")
        search_fields = ("name", "phone", "email")
        date_hierarchy = "joined_at"
        ordering = ("name",)
        list_select_related = ("business",)
        list_per_page = 50


if GymCheckIn:

    @admin.register(GymCheckIn)
    class GymCheckInAdmin(admin.ModelAdmin):
        list_display = ("member", "timestamp", "checked_in_by", "business")
        list_filter = ("timestamp", "business")
        search_fields = ("member__name", "member__phone")


# Import TrainerFee
try:
    from inventory.models_verticals import TrainerFee
except ImportError:
    TrainerFee = None

if TrainerFee:

    @admin.register(TrainerFee)
    class TrainerFeeAdmin(admin.ModelAdmin):
        list_display = ("trainer", "member", "amount", "period_start", "period_end", "created_at", "business")
        list_filter = ("created_at", "business", "trainer")
        search_fields = ("trainer__name", "member__name", "member__phone")
        date_hierarchy = "created_at"
        ordering = ("-created_at",)
        list_select_related = ("trainer", "member", "business", "recorded_by")
        autocomplete_fields = ("business", "trainer", "member")
        readonly_fields = ("created_at",)
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
        raw_id_fields = ("product", "sold_by")
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


# ==============================================================================
# CEMENT ADMINS
# ==============================================================================

if CementSale:

    @admin.register(CementSale)
    class CementSaleAdmin(admin.ModelAdmin):
        list_display = (
            "product",
            "quantity",
            "unit_price",
            "total_price",
            "profit",
            "payment_method",
            "sold_at",
            "sold_by",
        )
        list_filter = ("payment_method", "sold_at")
        search_fields = ("product__name", "sold_by__username", "notes")
        date_hierarchy = "sold_at"
        ordering = ("-sold_at",)
        list_select_related = ("product", "sold_by", "business")
        raw_id_fields = ("product", "sold_by")
        readonly_fields = ("profit",)
        list_per_page = 50


if CementCost:

    @admin.register(CementCost)
    class CementCostAdmin(admin.ModelAdmin):
        list_display = ("description", "category", "amount", "cost_date", "business", "created_by", "created_at")
        list_filter = ("category", "cost_date", "created_at")
        search_fields = ("description", "notes", "business__name")
        date_hierarchy = "cost_date"
        ordering = ("-cost_date", "-created_at")
        list_select_related = ("business", "location", "created_by")
        raw_id_fields = ("business", "location", "created_by")
        list_per_page = 50


# ==============================================================================
# GROCERIES ADMINS
# ==============================================================================

if GrocerySale:

    @admin.register(GrocerySale)
    class GrocerySaleAdmin(admin.ModelAdmin):
        list_display = (
            "product",
            "quantity",
            "sale_mode",
            "unit_price",
            "total_price",
            "profit",
            "payment_method",
            "sold_at",
            "sold_by",
        )
        list_filter = ("sale_mode", "payment_method", "sold_at")
        search_fields = ("product__name", "sold_by__username", "notes")
        date_hierarchy = "sold_at"
        ordering = ("-sold_at",)
        list_select_related = ("product", "sold_by", "business")
        raw_id_fields = ("product", "sold_by")
        readonly_fields = ("profit",)
        list_per_page = 50
