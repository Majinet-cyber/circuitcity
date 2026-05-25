from django.contrib import admin
from .models import Merchant


@admin.register(Merchant)
class MerchantAdmin(admin.ModelAdmin):
    list_display = ("business_name", "owner", "phone_number", "location", "is_active")
    list_filter = ("is_active",)
    search_fields = ("business_name", "owner__username", "phone_number")