"""Website admin — lead management for merchant and career applications."""
from django.contrib import admin
from .models import MerchantLead, CareerLead


@admin.register(MerchantLead)
class MerchantLeadAdmin(admin.ModelAdmin):
    list_display = [
        "business_name", "owner_full_name", "phone",
        "district", "business_type", "status", "created_at",
    ]
    list_filter = ["status", "district", "business_type", "has_business_registration"]
    search_fields = ["business_name", "owner_full_name", "phone", "district"]
    list_editable = ["status"]
    readonly_fields = ["created_at", "updated_at", "source"]
    ordering = ["-created_at"]
    date_hierarchy = "created_at"
    fieldsets = [
        ("Business", {
            "fields": ["business_name", "business_type", "area", "district", "has_business_registration"],
        }),
        ("Contact", {
            "fields": ["owner_full_name", "phone", "whatsapp_phone", "email"],
        }),
        ("Details", {
            "fields": ["estimated_monthly_phone_sales", "preferred_payout_method", "message"],
        }),
        ("Status", {
            "fields": ["status", "assigned_to", "source"],
        }),
        ("Timestamps", {
            "fields": ["created_at", "updated_at"],
            "classes": ["collapse"],
        }),
    ]


@admin.register(CareerLead)
class CareerLeadAdmin(admin.ModelAdmin):
    list_display = [
        "full_name", "phone", "district", "role_interested", "status", "created_at",
    ]
    list_filter = ["status", "role_interested", "district"]
    search_fields = ["full_name", "phone", "email", "district"]
    list_editable = ["status"]
    readonly_fields = ["created_at", "updated_at"]
    ordering = ["-created_at"]
    date_hierarchy = "created_at"
    fieldsets = [
        ("Applicant", {
            "fields": ["full_name", "phone", "email", "district"],
        }),
        ("Application", {
            "fields": ["role_interested", "note", "cv_file"],
        }),
        ("Status", {
            "fields": ["status", "assigned_to"],
        }),
        ("Timestamps", {
            "fields": ["created_at", "updated_at"],
            "classes": ["collapse"],
        }),
    ]
