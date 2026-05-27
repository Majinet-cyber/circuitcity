# hq/tests/test_hq_contracts.py
"""
Regression tests for HQ contracts views.
Ensures /hq/contracts/ never crashes due to missing relations.
"""
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from tenants.models import Business
from hq.models import MerchantContract
from io import BytesIO

User = get_user_model()


class HQContractsViewTests(TestCase):
    """Test HQ contracts list and detail views."""

    def setUp(self):
        """Create test data."""
        # Create HQ user
        self.hq_user = User.objects.create_user(
            username="hq_admin", email="hq@test.com", password="testpass123", is_staff=True, is_superuser=True
        )

        # Create test businesses
        self.business_with_contract = Business.objects.create(
            name="Business With Contract", slug="biz-with-contract", status="ACTIVE"
        )

        self.business_without_contract = Business.objects.create(
            name="Business Without Contract", slug="biz-no-contract", status="ACTIVE"
        )

        self.business_with_subscription = Business.objects.create(
            name="Business With Subscription", slug="biz-with-sub", status="ACTIVE"
        )

        # Create a contract for one business
        self.contract = MerchantContract.objects.create(
            business=self.business_with_contract, title="Test Contract", notes="Test notes", uploaded_by=self.hq_user
        )

        self.client = Client()
        self.client.login(username="hq_admin", password="testpass123")

    def test_contracts_list_returns_200(self):
        """Test that /hq/contracts/ returns 200 for HQ user."""
        url = reverse("hq:contracts_list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertIn("businesses_with_status", response.context)

    def test_contracts_list_with_no_businesses(self):
        """Test contracts list works even with no businesses."""
        # Delete all businesses
        Business.objects.all().delete()

        url = reverse("hq:contracts_list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["businesses_with_status"]), 0)

    def test_contracts_list_with_no_contracts(self):
        """Test contracts list works when no business has contracts."""
        # Delete all contracts
        MerchantContract.objects.all().delete()

        url = reverse("hq:contracts_list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        # Should still show businesses
        self.assertGreater(len(response.context["businesses_with_status"]), 0)
        # All should have has_contract=False
        for item in response.context["businesses_with_status"]:
            self.assertFalse(item["has_contract"])
            self.assertIsNone(item["contract"])

    def test_contracts_list_shows_correct_status(self):
        """Test that contracts list correctly identifies businesses with/without contracts."""
        url = reverse("hq:contracts_list")
        response = self.client.get(url)

        businesses_with_status = response.context["businesses_with_status"]

        # Find our test businesses in the response
        biz_with_contract = next(
            (item for item in businesses_with_status if item["business"].id == self.business_with_contract.id), None
        )
        biz_without_contract = next(
            (item for item in businesses_with_status if item["business"].id == self.business_without_contract.id), None
        )

        # Verify contract status
        self.assertIsNotNone(biz_with_contract)
        self.assertTrue(biz_with_contract["has_contract"])
        self.assertIsNotNone(biz_with_contract["contract"])

        self.assertIsNotNone(biz_without_contract)
        self.assertFalse(biz_without_contract["has_contract"])
        self.assertIsNone(biz_without_contract["contract"])

    def test_contracts_list_filter_signed(self):
        """Test filtering for businesses with signed contracts."""
        url = reverse("hq:contracts_list") + "?status=signed"
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        businesses_with_status = response.context["businesses_with_status"]

        # Should only show businesses with contracts
        for item in businesses_with_status:
            self.assertTrue(item["has_contract"])

    def test_contracts_list_filter_unsigned(self):
        """Test filtering for businesses without contracts."""
        url = reverse("hq:contracts_list") + "?status=unsigned"
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        businesses_with_status = response.context["businesses_with_status"]

        # Should only show businesses without contracts
        for item in businesses_with_status:
            self.assertFalse(item["has_contract"])

    def test_contracts_list_search(self):
        """Test search functionality."""
        url = reverse("hq:contracts_list") + "?q=With+Contract"
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        businesses_with_status = response.context["businesses_with_status"]

        # Should find the business with "With Contract" in name
        business_names = [item["business"].name for item in businesses_with_status]
        self.assertIn("Business With Contract", business_names)

    def test_contracts_detail_with_contract(self):
        """Test detail view for business with existing contract."""
        url = reverse("hq:contracts_detail", kwargs={"business_id": self.business_with_contract.id})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(response.context["contract"])
        self.assertEqual(response.context["contract"].id, self.contract.id)

    def test_contracts_detail_without_contract(self):
        """Test detail view for business without contract."""
        url = reverse("hq:contracts_detail", kwargs={"business_id": self.business_without_contract.id})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.context["contract"])

    def test_contracts_detail_nonexistent_business(self):
        """Test detail view for nonexistent business returns 404."""
        url = reverse("hq:contracts_detail", kwargs={"business_id": 99999})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 404)

    def test_contracts_list_requires_hq_permission(self):
        """Test that non-HQ users cannot access contracts list."""
        # Create regular user
        regular_user = User.objects.create_user(username="regular", email="regular@test.com", password="testpass123")

        # Login as regular user
        self.client.logout()
        self.client.login(username="regular", password="testpass123")

        url = reverse("hq:contracts_list")
        response = self.client.get(url)

        # Should redirect or return 403
        self.assertIn(response.status_code, [302, 403])

    def test_contracts_list_requires_authentication(self):
        """Test that unauthenticated users cannot access contracts list."""
        self.client.logout()

        url = reverse("hq:contracts_list")
        response = self.client.get(url)

        # Should redirect to login
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_multiple_contracts_per_business(self):
        """Test that when a business has multiple contracts, the most recent is shown."""
        # Create a second contract for the same business
        newer_contract = MerchantContract.objects.create(
            business=self.business_with_contract, title="Newer Contract", notes="Newer notes", uploaded_by=self.hq_user
        )

        url = reverse("hq:contracts_list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        businesses_with_status = response.context["businesses_with_status"]

        # Find our business
        biz_item = next(
            (item for item in businesses_with_status if item["business"].id == self.business_with_contract.id), None
        )

        # Should show the newer contract (most recent)
        self.assertIsNotNone(biz_item)
        self.assertTrue(biz_item["has_contract"])
        self.assertEqual(biz_item["contract"].id, newer_contract.id)
        self.assertEqual(biz_item["contract"].title, "Newer Contract")

    def test_contracts_list_pagination(self):
        """Test that pagination works correctly."""
        # Create many businesses to trigger pagination
        for i in range(30):
            Business.objects.create(name=f"Test Business {i}", slug=f"test-biz-{i}", status="ACTIVE")

        url = reverse("hq:contracts_list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertIn("page_obj", response.context)

        # Default page size is 25
        self.assertLessEqual(len(response.context["businesses_with_status"]), 25)

    def test_no_merchant_contract_references_in_queryset(self):
        """Regression test: ensure no invalid 'merchant_contract' references."""
        url = reverse("hq:contracts_list")

        # This should not raise FieldError about merchant_contract
        try:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
        except Exception as e:
            self.fail(f"contracts_list raised exception: {e}")


class HQContractUploadTests(TestCase):
    """Test contract upload functionality."""

    def setUp(self):
        """Create test data."""
        self.hq_user = User.objects.create_user(
            username="hq_admin", email="hq@test.com", password="testpass123", is_staff=True, is_superuser=True
        )

        self.business = Business.objects.create(name="Test Business", slug="test-biz", status="ACTIVE")

        self.client = Client()
        self.client.login(username="hq_admin", password="testpass123")

    def test_contract_upload_creates_new_contract(self):
        """Test uploading a new contract."""
        url = reverse("hq:contracts_detail", kwargs={"business_id": self.business.id})

        # Create a fake PDF file
        pdf_content = b"%PDF-1.4 fake pdf content"
        pdf_file = BytesIO(pdf_content)
        pdf_file.name = "test_contract.pdf"

        response = self.client.post(url, {"contract_file": pdf_file, "notes": "Test upload"})

        # Should redirect to contracts list
        self.assertEqual(response.status_code, 302)

        # Contract should be created
        self.assertTrue(MerchantContract.objects.filter(business=self.business).exists())

        contract = MerchantContract.objects.filter(business=self.business).first()
        self.assertEqual(contract.notes, "Test upload")
        self.assertEqual(contract.uploaded_by, self.hq_user)
