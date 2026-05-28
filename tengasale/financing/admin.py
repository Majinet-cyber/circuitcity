from django.contrib import admin, messages

from . import services
from .models import (
    Customer,
    Device,
    DeviceCommand,
    DeviceStatusLog,
    FinancingContract,
    PaymentRecord,
    RepaymentSchedule,
    UnlockToken,
)


class RepaymentScheduleInline(admin.TabularInline):
    model = RepaymentSchedule
    extra = 0


class PaymentRecordInline(admin.TabularInline):
    model = PaymentRecord
    extra = 0
    readonly_fields = ("verification_status", "verified_by", "verified_at", "created_at")


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("full_name", "phone_number", "customer_id_number", "created_at")
    search_fields = ("full_name", "phone_number", "customer_id_number")


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ("brand", "model", "imei_1", "status", "assigned_customer", "created_at")
    list_filter = ("status", "brand")
    search_fields = ("brand", "model", "imei_1", "imei_2", "serial_number")


@admin.register(FinancingContract)
class FinancingContractAdmin(admin.ModelAdmin):
    list_display = ("customer", "device", "status", "next_due_date", "monthly_payment_amount", "created_by")
    list_filter = ("status", "next_due_date")
    search_fields = ("customer__full_name", "customer__phone_number", "device__imei_1")
    inlines = (RepaymentScheduleInline, PaymentRecordInline)
    actions = ("generate_unlock_token", "request_lock", "request_unlock")

    @admin.action(description="Generate unlock PIN")
    def generate_unlock_token(self, request, queryset):
        for contract in queryset:
            services.generate_unlock_token(contract, generated_by=request.user)
        self.message_user(request, "Unlock PIN generated for selected contracts.", messages.SUCCESS)

    @admin.action(description="Request mock lock")
    def request_lock(self, request, queryset):
        for contract in queryset:
            services.issue_device_command(contract, DeviceCommand.TYPE_LOCK, created_by=request.user)
        self.message_user(request, "Mock lock commands sent.", messages.SUCCESS)

    @admin.action(description="Request mock unlock")
    def request_unlock(self, request, queryset):
        for contract in queryset:
            services.issue_device_command(contract, DeviceCommand.TYPE_UNLOCK, created_by=request.user)
        self.message_user(request, "Mock unlock commands sent.", messages.SUCCESS)


@admin.register(RepaymentSchedule)
class RepaymentScheduleAdmin(admin.ModelAdmin):
    list_display = ("contract", "due_date", "amount_due", "amount_paid", "status", "paid_at")
    list_filter = ("status", "due_date")


@admin.register(PaymentRecord)
class PaymentRecordAdmin(admin.ModelAdmin):
    list_display = ("customer", "contract", "amount", "payment_method", "verification_status", "created_at")
    list_filter = ("verification_status", "payment_method")
    search_fields = ("customer__full_name", "transaction_reference", "contract__device__imei_1")
    actions = ("approve_payments", "reject_payments")

    @admin.action(description="Approve selected payments")
    def approve_payments(self, request, queryset):
        for payment in queryset:
            services.verify_payment(payment, verified_by=request.user)
        self.message_user(request, "Selected payments approved.", messages.SUCCESS)

    @admin.action(description="Reject selected payments")
    def reject_payments(self, request, queryset):
        for payment in queryset:
            services.reject_payment(payment, rejected_by=request.user, reason="Rejected from Django admin.")
        self.message_user(request, "Selected payments rejected.", messages.SUCCESS)


@admin.register(DeviceStatusLog)
class DeviceStatusLogAdmin(admin.ModelAdmin):
    list_display = ("device", "contract", "action", "status_before", "status_after", "created_at")
    list_filter = ("action", "created_at")
    search_fields = ("device__imei_1", "notes")


@admin.register(UnlockToken)
class UnlockTokenAdmin(admin.ModelAdmin):
    list_display = ("contract", "device", "token", "status", "valid_until", "generated_by")
    list_filter = ("status", "valid_until")
    search_fields = ("token", "device__imei_1", "customer__full_name")
    actions = ("revoke_tokens", "mark_tokens_used")

    @admin.action(description="Revoke selected unlock PINs")
    def revoke_tokens(self, request, queryset):
        queryset.update(status=UnlockToken.STATUS_REVOKED)
        self.message_user(request, "Selected unlock PINs revoked.", messages.SUCCESS)

    @admin.action(description="Mark selected unlock PINs used")
    def mark_tokens_used(self, request, queryset):
        for token in queryset:
            token.mark_used()
        self.message_user(request, "Selected unlock PINs marked as used.", messages.SUCCESS)


@admin.register(DeviceCommand)
class DeviceCommandAdmin(admin.ModelAdmin):
    list_display = ("device", "contract", "command_type", "provider", "status", "created_at", "completed_at")
    list_filter = ("command_type", "provider", "status")
    search_fields = ("device__imei_1", "error_message")
    readonly_fields = ("created_at", "completed_at")
