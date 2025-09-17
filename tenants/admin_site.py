from django.contrib.admin import AdminSite

class SuperuserOnlyAdminSite(AdminSite):
    site_header = "Circuit City Superadmin"
    site_title = "Superadmin"
    index_title = "Superadmin"

    def has_permission(self, request):
        return request.user.is_active and request.user.is_superuser

superadmin_site = SuperuserOnlyAdminSite(name="superadmin")
