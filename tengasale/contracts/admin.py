from django.contrib import admin

from .models import Contract


@admin.register(Contract)
class ContractAdmin(admin.ModelAdmin):
    list_display = ("contract_number", "customer_name", "merchant", "status", "created_at")
    search_fields = ("contract_number", "customer_name", "national_id", "imei_number")
    list_filter = ("status", "warranty_checked", "phone_locked", "deposit_paid")

# Register your models here.
