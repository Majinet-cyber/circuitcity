# cc/admin.py (create if not present)
from django.contrib import admin
from django_otp.admin import OTPAdminSite

class OTPRequiredAdminSite(OTPAdminSite):
    pass

admin.site.__class__ = OTPRequiredAdminSite
