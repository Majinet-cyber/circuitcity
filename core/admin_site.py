# core/admin_site.py
from django.contrib import admin

class StaffOnlyAdminSite(admin.AdminSite):
    site_header = "Circuit City â€” Admin"
    site_title = "Circuit City Admin"
    index_title = "Admin"

    def has_permission(self, request):
        # Absolutely no â€œManagerâ€ or â€œAgentâ€ here. Only staff/superusers.
        return bool(request.user and request.user.is_active and request.user.is_staff)

staff_admin_site = StaffOnlyAdminSite(name="staff_admin")


