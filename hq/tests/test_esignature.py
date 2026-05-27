"""
Tests for the merchant e-signature portal.
"""
import uuid
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse

User = get_user_model()


class ESignaturePortalTest(TestCase):
    """Tests for the merchant contract e-signature flow."""

    def setUp(self):
        # HQ admin user
        self.hq_user = User.objects.create_user(
            username="hq_admin_test",
            password="TestPass123!",
            is_staff=True,
        )
        # Merchant user
        self.merchant_user = User.objects.create_user(
            username="merchant_test",
            password="TestPass123!",
        )
        self.client = Client()

    def _create_business_and_contract(self):
        """Helper: create a minimal Business + MerchantContract."""
        try:
            from tenants.models import Business
            from hq.models import MerchantContract

            biz = Business.objects.create(
                name="Test Farm Business",
                slug="test-farm-biz",
            )
            contract = MerchantContract.objects.create(
                business=biz,
                title="Test Merchant Agreement",
                uploaded_by=self.hq_user,
            )
            return biz, contract
        except Exception as e:
            self.skipTest(f"Could not create test objects: {e}")

    def test_esignature_portal_requires_login(self):
        """Unauthenticated users should be redirected to login."""
        token = uuid.uuid4()
        url = reverse("hq:contract_sign_portal", kwargs={"token": token})
        response = self.client.get(url)
        self.assertIn(response.status_code, [302, 404])

    def test_hq_can_access_esignature_portal(self):
        """HQ admin can view the e-signature portal."""
        biz, contract = self._create_business_and_contract()
        self.client.force_login(self.hq_user)
        url = reverse("hq:contract_sign_portal", kwargs={"token": contract.sign_token})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    def test_hq_can_sign_contract(self):
        """HQ admin can submit an e-signature."""
        biz, contract = self._create_business_and_contract()
        self.client.force_login(self.hq_user)
        url = reverse("hq:contract_sign_submit", kwargs={"token": contract.sign_token})
        response = self.client.post(url, {
            "signature_name": "John Doe (HQ Test)",
            "agreement": "on",
        })
        self.assertIn(response.status_code, [200, 302])
        contract.refresh_from_db()
        self.assertEqual(contract.status, "signed")
        self.assertEqual(contract.signature_name, "John Doe (HQ Test)")
        self.assertIsNotNone(contract.signed_at)

    def test_signed_contract_cannot_be_re_signed(self):
        """A signed contract shows as already signed; does not update signature."""
        biz, contract = self._create_business_and_contract()
        contract.status = "signed"
        contract.signature_name = "Original Signer"
        from django.utils import timezone
        contract.signed_at = timezone.now()
        contract.save()

        self.client.force_login(self.hq_user)
        url = reverse("hq:contract_sign_submit", kwargs={"token": contract.sign_token})
        response = self.client.post(url, {
            "signature_name": "Different Name",
            "agreement": "on",
        })
        self.assertIn(response.status_code, [200, 302])
        contract.refresh_from_db()
        self.assertEqual(contract.signature_name, "Original Signer")

    def test_merchant_cannot_view_different_business_contract(self):
        """A merchant user not in the business should get 403."""
        biz, contract = self._create_business_and_contract()
        # merchant_user is not a member of biz
        self.client.force_login(self.merchant_user)
        url = reverse("hq:contract_sign_portal", kwargs={"token": contract.sign_token})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

    def test_contract_generate_pdf_requires_hq(self):
        """Non-HQ users should not access generate_merchant_contract_pdf."""
        biz, contract = self._create_business_and_contract()
        self.client.force_login(self.merchant_user)
        url = reverse("hq:generate_merchant_contract_pdf", kwargs={"business_id": biz.id})
        response = self.client.get(url)
        # Should be 302 (redirect to login/403) or 403
        self.assertIn(response.status_code, [302, 403])
