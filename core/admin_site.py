# core/admin_site.py
from django.contrib import admin

class StaffOnlyAdminSite(admin.AdminSite):
    site_header = "Circuit City — Admin"
    site_title = "Circuit City Admin"
    index_title = "Admin"

    def has_permission(self, request):
        # Absolutely no “Manager” or “Agent” here. Only staff/superusers.
        return bool(request.user and request.user.is_active and request.user.is_staff)

staff_admin_site = StaffOnlyAdminSite(name="staff_admin")
