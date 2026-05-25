from django.contrib import admin

from .models import SpinConfig, SpinGrant, SpinReward, SpinWallet


@admin.register(SpinWallet)
class SpinWalletAdmin(admin.ModelAdmin):
    list_display = ("user", "available_spins", "total_spins_earned", "total_spins_used")
    search_fields = ("user__username", "user__first_name", "user__last_name")


@admin.register(SpinGrant)
class SpinGrantAdmin(admin.ModelAdmin):
    list_display = ("user", "application", "created_at")
    search_fields = ("user__username", "application__application_number", "application__customer_name")
    readonly_fields = ("created_at",)


@admin.register(SpinReward)
class SpinRewardAdmin(admin.ModelAdmin):
    list_display = ("user", "amount", "reward_tier", "spin_date", "application")
    list_filter = ("reward_tier", "spin_date")
    search_fields = ("user__username", "application__application_number")
    readonly_fields = ("created_at",)


@admin.register(SpinConfig)
class SpinConfigAdmin(admin.ModelAdmin):
    list_display = ("is_enabled", "jackpot_amount", "jackpot_limit_per_week", "updated_at")
    readonly_fields = ("updated_at",)
