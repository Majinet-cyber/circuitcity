# wallet/admin.py
from django.contrib import admin
from .models import (
    WalletTransaction,
    SalesTarget,
    AttendanceLog,
    BudgetRequest,
    Payslip,
    Payment,
    PayoutSchedule,
    AdminPurchaseOrder,
    AdminPurchaseOrderItem,
)

@admin.register(WalletTransaction)
class WalletTransactionAdmin(admin.ModelAdmin):
    list_display = ("created_at", "ledger", "agent", "type", "amount", "effective_date", "reference")
    list_filter = ("ledger", "type", "effective_date", "created_at")
    search_fields = ("note", "reference", "agent__username", "agent__first_name", "agent__last_name")
    autocomplete_fields = ("agent", "created_by")
    date_hierarchy = "created_at"
    ordering = ("-created_at",)

@admin.register(SalesTarget)
class SalesTargetAdmin(admin.ModelAdmin):
    list_display = ("agent", "year", "month", "target_count", "bonus_per_extra")
    list_filter = ("year", "month")
    search_fields = ("agent__username", "agent__first_name", "agent__last_name")
    autocomplete_fields = ("agent",)

@admin.register(AttendanceLog)
class AttendanceLogAdmin(admin.ModelAdmin):
    list_display = ("agent", "date", "check_in", "weekend", "note")
    list_filter = ("weekend", "date")
    search_fields = ("agent__username", "agent__first_name", "agent__last_name", "note")
    autocomplete_fields = ("agent",)
    date_hierarchy = "date"

@admin.register(BudgetRequest)
class BudgetRequestAdmin(admin.ModelAdmin):
    list_display = ("created_at", "agent", "title", "amount", "status", "decided_by", "decided_at")
    list_filter = ("status", "created_at")
    search_fields = ("title", "reason", "agent__username", "agent__first_name", "agent__last_name")
    autocomplete_fields = ("agent", "decided_by")
    ordering = ("-created_at",)

@admin.register(Payslip)
class PayslipAdmin(admin.ModelAdmin):
    list_display = ("issued_at", "agent", "year", "month", "gross", "net", "status", "reference")
    list_filter = ("status", "year", "month", "issued_at")
    search_fields = ("reference", "agent__username", "agent__first_name", "agent__last_name", "email_to")
    autocomplete_fields = ("agent", "created_by")
    date_hierarchy = "issued_at"
    ordering = ("-issued_at",)

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ("created_at", "payslip", "method", "amount", "status", "txn_ref", "processed_by", "processed_at")
    list_filter = ("status", "method", "created_at")
    search_fields = ("txn_ref", "payslip__reference", "payslip__agent__username")
    autocomplete_fields = ("payslip", "processed_by")
    ordering = ("-created_at",)

@admin.register(PayoutSchedule)
class PayoutScheduleAdmin(admin.ModelAdmin):
    list_display = ("name", "day_of_month", "at_hour", "active", "last_run_at", "created_by", "created_at")
    list_filter = ("active", "day_of_month", "at_hour")
    search_fields = ("name",)
    autocomplete_fields = ("users", "created_by")
    ordering = ("name",)

class AdminPurchaseOrderItemInline(admin.TabularInline):
    model = AdminPurchaseOrderItem
    extra = 0
    autocomplete_fields = ("product",)
    fields = ("product", "quantity", "unit_price", "line_total")
    readonly_fields = ()

@admin.register(AdminPurchaseOrder)
class AdminPurchaseOrderAdmin(admin.ModelAdmin):
    list_display = ("id", "created_at", "created_by", "supplier_name", "total", "currency", "status")
    list_filter = ("status", "currency", "created_at")
    search_fields = ("supplier_name", "supplier_email", "supplier_phone", "agent_name")
    autocomplete_fields = ("created_by",)
    inlines = [AdminPurchaseOrderItemInline]
    ordering = ("-created_at",)

@admin.register(AdminPurchaseOrderItem)
class AdminPurchaseOrderItemAdmin(admin.ModelAdmin):
    list_display = ("po", "product", "quantity", "unit_price", "line_total")
    list_filter = ("po__status",)
    search_fields = ("product__name", "po__supplier_name")
    autocomplete_fields = ("po", "product")
    ordering = ("-po__created_at",)


