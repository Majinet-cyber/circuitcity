# tenants/admin.py
from django.contrib import admin
from .models import Business, Membership

@admin.register(Business)
class BusinessAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "status", "created_by", "created_at")
    list_filter = ("status",)
    search_fields = ("name", "slug", "subdomain")

@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "business", "role", "status", "created_at")
    list_filter = ("role", "status")
    search_fields = ("user__username", "business__name")
