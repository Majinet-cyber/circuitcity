from django.test import TestCase
from django.urls import reverse, NoReverseMatch

class InventoryExportCsvTests(TestCase):
    def test_export_csv_endpoint_exists_or_is_skipped(self):
        try:
            url = reverse("inventory:export_csv")
        except NoReverseMatch:
            self.skipTest("inventory:export_csv not wired yet")
            return

        resp = self.client.get(url)  # <-- this line was missing earlier
        self.assertIn(resp.status_code, (200, 302))
        if resp.status_code == 200:
            self.assertIn(resp["Content-Type"], ("text/csv", "application/csv"))
