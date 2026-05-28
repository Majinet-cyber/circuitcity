from django.contrib import admin
from .models import ManagerPayout, MerchantPayout, Wallet, WalletTransaction


@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = ("user", "balance", "total_earned", "total_paid", "total_wht_withheld", "status")


@admin.register(WalletTransaction)
class WalletTransactionAdmin(admin.ModelAdmin):
    list_display = ("wallet", "transaction_type", "amount", "contract_number", "created_at")
    list_filter = ("transaction_type", "created_at")
    search_fields = ("contract_number", "description")


@admin.register(ManagerPayout)
class ManagerPayoutAdmin(admin.ModelAdmin):
    list_display = (
        "wallet_user", "period_start", "period_end",
        "gross_amount", "wht_amount", "net_amount", "status", "paid_at",
    )
    list_filter = ("status",)
    readonly_fields = ("wht_amount", "net_amount")
    search_fields = ("wallet__user__username", "reference")

    def wallet_user(self, obj):
        return obj.wallet.user.username
    wallet_user.short_description = "User"


@admin.register(MerchantPayout)
class MerchantPayoutAdmin(admin.ModelAdmin):
    list_display = (
        "merchant", "contract_number", "device_description",
        "cash_price", "paid_amount", "status", "paid_at",
    )
    list_filter = ("status",)
    search_fields = ("merchant__username", "contract_number", "reference")
