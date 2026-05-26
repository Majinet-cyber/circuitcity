from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.utils import assign_role
from applications.models import FinancingApplication


class ApprovalQueueTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.merchant = User.objects.create_user(username="merchant", password="test-pass-123")
        self.manager = User.objects.create_user(username="manager", password="test-pass-123")
        self.second_manager = User.objects.create_user(username="manager2", password="test-pass-123")
        assign_role(self.merchant, "merchant")
        assign_role(self.manager, "underwriter")
        assign_role(self.second_manager, "underwriter")

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

    def test_underwriter_url_names_resolve(self):
        self.assertEqual(reverse("underwriter_dashboard"), "/tengasale/underwriter/")
        self.assertEqual(reverse("underwriter_claim_next"), "/tengasale/underwriter/claim-next/")
        self.assertEqual(reverse("underwriter_queue"), "/tengasale/underwriter/queue/")
        self.assertEqual(reverse("underwriter_active_reviews"), "/tengasale/underwriter/active/")
        self.assertEqual(reverse("underwriter_completed_reviews"), "/tengasale/underwriter/completed/")
        app = self.create_pending()
        self.assertEqual(reverse("underwriter_address_check", args=[app.id]), f"/tengasale/underwriter/review/{app.id}/address-check/")
        self.assertEqual(reverse("underwriter_income_check", args=[app.id]), f"/tengasale/underwriter/review/{app.id}/income-check/")
        self.assertEqual(reverse("underwriter_confirm_approve", args=[app.id]), f"/tengasale/underwriter/review/{app.id}/confirm-approve/")

    def test_pending_review_with_no_claim_appears_in_queue(self):
        self.create_pending()
        self.client.login(username="manager", password="test-pass-123")

        response = self.client.get(reverse("underwriter_dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Hi, manager")
        self.assertContains(response, "CLAIM NEXT")
        self.assertContains(response, "Queue Rules")
        self.assertContains(response, "MY ACTIVE")

    def test_manager_can_claim_next_and_second_manager_cannot_claim_same_app(self):
        app = self.create_pending()
        self.client.login(username="manager", password="test-pass-123")

        response = self.client.get(reverse("underwriter_claim_next"))
        app.refresh_from_db()

        self.assertRedirects(response, reverse("underwriter_review_application", args=[app.id]))
        self.assertEqual(app.claimed_by, self.manager)
        self.assertEqual(app.status, "under_review")

        self.client.login(username="manager2", password="test-pass-123")
        response = self.client.get(reverse("underwriter_review_application", args=[app.id]), follow=True)

        self.assertContains(response, "This application is already under review by")

    def test_under_review_underwriter_dashboard_shows_underwriter(self):
        app = self.create_pending(status="under_review", claimed_by=self.manager, claimed_at=timezone.now())
        self.client.login(username="manager", password="test-pass-123")

        response = self.client.get(reverse("underwriter_dashboard"))

        self.assertContains(response, "Under Review")
        self.assertContains(response, app.application_number)

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
            reverse("underwriter_review_application", args=[app.id]),
            {
                "decision": "request_correction",
                "correction_fields": ["income_band", "exact_monthly_income"],
                "correction_notes": "Check income.",
            },
        )
        app.refresh_from_db()

        self.assertRedirects(response, reverse("underwriter_dashboard"))
        self.assertEqual(app.status, "correction_requested")
        self.assertEqual(app.correction_fields, ["income_band", "exact_monthly_income"])

        self.client.login(username="merchant", password="test-pass-123")
        response = self.client.get(reverse("application_corrections", args=[app.id]))

        self.assertContains(response, "Income band")
        self.assertContains(response, "Exact monthly income")
        self.assertContains(response, "Check income.")

    def test_review_detail_contains_expected_sections_and_actions(self):
        app = self.create_pending(status="under_review", claimed_by=self.manager)
        self.client.login(username="manager", password="test-pass-123")

        response = self.client.get(reverse("underwriter_review_application", args=[app.id]))

        for text in ["Customer", "Deal", "KYC images", "Location", "Income/work", "Contacts/next of kin", "Signature"]:
            self.assertContains(response, text)
        self.assertContains(response, "APPROVE")
        self.assertContains(response, "REJECT")
        self.assertContains(response, "SEND BACK FOR EDIT")
        self.assertContains(response, "ADDRESS CHECK")
        self.assertContains(response, "INCOME CHECK")

    def test_address_and_income_checks_save_answers(self):
        app = self.create_pending(status="under_review", claimed_by=self.manager)
        app.exact_monthly_income = 300000
        app.calculated_monthly_payment = 60000
        app.save()
        self.client.login(username="manager", password="test-pass-123")

        address_response = self.client.post(
            reverse("underwriter_address_check", args=[app.id]),
            {
                "spoke_to_neighbour": "yes",
                "neighbour_confirmed_location": "no",
                "can_locate_if_defaulted": "yes",
            },
        )
        income_response = self.client.post(
            reverse("underwriter_income_check", args=[app.id]),
            {
                "understands_income": "yes",
                "spoke_to_proof_contact": "yes",
                "proof_contact_confirmed_work": "yes",
                "proof_contact_confident": "no",
            },
        )
        app.refresh_from_db()

        self.assertRedirects(address_response, reverse("underwriter_review_application", args=[app.id]))
        self.assertRedirects(income_response, reverse("underwriter_review_application", args=[app.id]))
        self.assertTrue(app.address_check_answers["spoke_to_neighbour"])
        self.assertEqual(app.income_check_answers["affordability"], "Affordable")

    def test_confirm_approve_requires_post_to_approve(self):
        app = self.create_pending(status="under_review", claimed_by=self.manager)
        self.client.login(username="manager", password="test-pass-123")

        get_response = self.client.get(reverse("underwriter_confirm_approve", args=[app.id]))
        app.refresh_from_db()
        self.assertEqual(get_response.status_code, 200)
        self.assertEqual(app.status, "under_review")

        post_response = self.client.post(reverse("underwriter_confirm_approve", args=[app.id]))
        app.refresh_from_db()
        self.assertRedirects(post_response, reverse("underwriter_dashboard"))
        self.assertEqual(app.status, "approved")

    def test_manager_can_approve_and_reject(self):
        approve_app = self.create_pending(status="under_review", claimed_by=self.manager)
        reject_app = self.create_pending(
            status="under_review",
            claimed_by=self.manager,
            customer_name="Reject Customer",
            national_id="ABCDEFGH",
        )
        self.client.login(username="manager", password="test-pass-123")

        approve_response = self.client.post(reverse("underwriter_review_application", args=[approve_app.id]), {"decision": "approve"})
        reject_response = self.client.post(
            reverse("underwriter_review_application", args=[reject_app.id]),
            {"decision": "reject", "manager_comment": "Does not qualify."},
        )
        approve_app.refresh_from_db()
        reject_app.refresh_from_db()

        self.assertRedirects(approve_response, reverse("underwriter_dashboard"))
        self.assertRedirects(reject_response, reverse("underwriter_dashboard"))
        self.assertEqual(approve_app.status, "approved")
        self.assertEqual(reject_app.status, "rejected")

    def test_reject_requires_comment(self):
        app = self.create_pending(status="under_review", claimed_by=self.manager)
        self.client.login(username="manager", password="test-pass-123")

        response = self.client.post(reverse("underwriter_review_application", args=[app.id]), {"decision": "reject"})
        app.refresh_from_db()

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Underwriter comment is required when rejecting an application.")
        self.assertEqual(app.status, "under_review")

    def test_merchant_cannot_access_underwriter_dashboard(self):
        self.client.login(username="merchant", password="test-pass-123")

        response = self.client.get(reverse("underwriter_dashboard"))

        self.assertEqual(response.status_code, 403)
        self.assertContains(response, "That area is not available for your role.", status_code=403)
        self.assertContains(response, "Go to my dashboard", status_code=403)

    def test_merchant_cannot_access_underwriter_claim_action(self):
        self.client.login(username="merchant", password="test-pass-123")

        response = self.client.get(reverse("underwriter_claim_next"))

        self.assertEqual(response.status_code, 403)
        self.assertContains(response, "That area is not available for your role.", status_code=403)
        self.assertContains(response, "Go to my dashboard", status_code=403)

    def test_old_approvals_urls_redirect_to_underwriter_portal(self):
        app = self.create_pending(status="under_review", claimed_by=self.manager)

        self.assertRedirects(
            self.client.get("/approvals/"),
            reverse("underwriter_dashboard"),
            fetch_redirect_response=False,
        )
        self.assertRedirects(
            self.client.get("/approvals/claim-next/"),
            reverse("underwriter_claim_next"),
            fetch_redirect_response=False,
        )
        self.assertRedirects(
            self.client.get(f"/approvals/review/{app.id}/"),
            reverse("underwriter_review_application", args=[app.id]),
            fetch_redirect_response=False,
        )

    def test_active_and_completed_review_pages_render(self):
        self.create_pending(status="under_review", claimed_by=self.manager, claimed_at=timezone.now())
        self.create_pending(status="approved", reviewed_by=self.manager, reviewed_at=timezone.now())
        self.client.login(username="manager", password="test-pass-123")

        active_response = self.client.get(reverse("underwriter_active_reviews"))
        completed_response = self.client.get(reverse("underwriter_completed_reviews"))

        self.assertContains(active_response, "My Active Reviews")
        self.assertContains(completed_response, "Completed Reviews")

    def test_underwriter_cannot_exceed_five_active_applications(self):
        for index in range(5):
            self.create_pending(
                status="under_review",
                claimed_by=self.manager,
                claimed_at=timezone.now(),
                national_id=f"ABCDE{index:03d}",
            )
        pending = self.create_pending(national_id="ZZZZ9999")
        self.client.login(username="manager", password="test-pass-123")

        response = self.client.get(reverse("underwriter_claim_next"))
        pending.refresh_from_db()

        self.assertRedirects(response, reverse("underwriter_dashboard"))
        self.assertIsNone(pending.claimed_by)
        self.assertEqual(pending.status, "pending_review")

    def test_underwriter_queue_route_returns_200(self):
        self.create_pending()
        self.client.login(username="manager", password="test-pass-123")

        response = self.client.get(reverse("underwriter_queue"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Queue")
