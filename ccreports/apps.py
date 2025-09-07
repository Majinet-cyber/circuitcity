from django.apps import AppConfig

class ReportsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "ccreports"        # package name on disk
    label = "cc_reports"      # internal label (avoid 'reports' clash)
    verbose_name = "Reports"
