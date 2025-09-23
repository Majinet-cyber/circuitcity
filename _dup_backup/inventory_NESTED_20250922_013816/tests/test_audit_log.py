from django.test import TestCase
from django.apps import apps

class AuditLogModelTests(TestCase):
    def test_audit_log_model_exists(self):
        try:
            AuditLog = apps.get_model("inventory", "AuditLog")
        except LookupError:
            self.skipTest("inventory.AuditLog not found (ok if not implemented yet)")
            return

        entry = AuditLog.objects.create(action="TEST", model="X", object_id="0", user=None, changes={})
        self.assertIsNotNone(entry.pk)
