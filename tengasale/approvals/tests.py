from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from applications.models import FinancingApplication


class ApprovalQueueTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.merchant = User.objects.create_user(username="merchant", password="test-pass-123")
        self.manager = User.objects.create_user(username="manager", password="test-pass-123", is_staff=True)
        self.second_manager = User.objects.create_user(username="manager2", password="test-pass-123", is_staff=True)

    def create_pending(self, **overrides):
        data = {
            "created_by": self.merchant,
            "customer_name": "Jane Banda",
            "national_id": "RQXFVZC9",
            "status": "pending_review",
            "submitted_at": timezone.now(),
        }
        data.update(overrides)
        return FinancingApplication.objects.create(**data)

    def test_manager_home_url_name_resolves(self):
        self.assertEqual(reverse("manager_home"), "/approvals/")

    def test_pending_review_with_no_claim_appears_in_queue(self):
        self.create_pending()
        self.client.login(username="manager", password="test-pass-123")

        response = self.client.get(reverse("manager_home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Pending queue")
        self.assertContains(response, "1")

    def test_manager_can_claim_next_and_second_manager_cannot_claim_same_app(self):
        app = self.create_pending()
        self.client.login(username="manager", password="test-pass-123")

        response = self.client.get(reverse("claim_next"))
        app.refresh_from_db()

        self.assertRedirects(response, reverse("review_application", args=[app.id]))
        self.assertEqual(app.claimed_by, self.manager)
        self.assertEqual(app.status, "under_review")

        self.client.login(username="manager2", password="test-pass-123")
        response = self.client.get(reverse("review_application", args=[app.id]), follow=True)

        self.assertContains(response, "This application is already under review by")

    def test_merchant_submitted_page_shows_reviewer_name_for_under_review(self):
        app = self.create_pending(status="under_review", claimed_by=self.manager, claimed_at=timezone.now())
        self.client.login(username="merchant", password="test-pass-123")

        response = self.client.get(reverse("application_submitted", args=[app.id]))

        self.assertContains(response, "Being reviewed by")
        self.assertContains(response, "manager")

    def test_manager_can_send_back_with_correction_fields(self):
        app = self.create_pending(status="under_review", claimed_by=self.manager)
        self.client.login(username="manager", password="test-pass-123")

        response = self.client.post(
            reverse("review_application", args=[app.id]),
            {
                "decision": "request_correction",
                "correction_fields": ["income_band", "exact_monthly_income"],
                "correction_notes": "Check income.",
            },
        )
        app.refresh_from_db()

        self.assertRedirects(response, reverse("manager_home"))
        self.assertEqual(app.status, "correction_requested")
        self.assertEqual(app.correction_fields, ["income_band", "exact_monthly_income"])

        self.client.login(username="merchant", password="test-pass-123")
        response = self.client.get(reverse("application_corrections", args=[app.id]))

        self.assertContains(response, "Income band")
        self.assertContains(response, "Exact monthly income")
        self.assertContains(response, "Check income.")
