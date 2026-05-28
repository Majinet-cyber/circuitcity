import base64
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from accounts.utils import assign_role
from applications.models import FinancingApplication
from commissions.models import Commission
from deals.models import DeviceBrand, DeviceDeal
from rewards.models import SpinWallet

from .forms import ImeiForm
from .models import Contract


PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
    b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00"
    b"\x00\x0cIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe"
    b"\r\xefF\xb8\x00\x00\x00\x00IEND\xaeB`\x82"
)


def signature_data():
    return "data:image/png;base64," + base64.b64encode(PNG_BYTES).decode("ascii")


class ContractFlowTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.merchant = User.objects.create_user(username="merchant", password="test-pass-123")
        self.other = User.objects.create_user(username="other", password="test-pass-123")
        assign_role(self.merchant, "merchant")
        assign_role(self.other, "merchant")
        brand = DeviceBrand.objects.create(name="TECNO")
        self.deal = DeviceDeal.objects.create(
            brand=brand,
            model_name="Pop 10C",
            specs="2+64",
            min_cash_price=Decimal("300000.00"),
            max_cash_price=Decimal("400000.00"),
            default_cash_price=Decimal("350000.00"),
            cash_price=Decimal("350000.00"),
            deposit_percent=Decimal("13.00"),
            loan_multiplier=Decimal("2.50"),
            term_months=12,
            total_12_month_price=Decimal("875000.00"),
        )
        self.app = FinancingApplication.objects.create(
            created_by=self.merchant,
            status="approved",
            customer_name="Jane Banda",
            customer_phone="990870616",
            national_id="RQXFVZC9",
            deal=self.deal,
            selected_cash_price=Decimal("350000.00"),
            calculated_total_loan=Decimal("875000.00"),
            calculated_deposit_amount=Decimal("113750.00"),
            calculated_monthly_payment=Decimal("72916.67"),
            calculated_daily_payment=Decimal("2430.56"),
        )
        self.client.login(username="merchant", password="test-pass-123")

    def test_approved_app_routes_to_contract_terms(self):
        self.assertEqual(self.app.get_continue_url(), reverse("contract_terms", args=[self.app.id]))

    def test_contract_terms_requires_checkbox_and_creates_contract(self):
        response = self.client.post(reverse("contract_terms", args=[self.app.id]), {})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Contract.objects.exists())

        response = self.client.post(reverse("contract_terms", args=[self.app.id]), {"confirmed_terms": "on"})
        contract = Contract.objects.get(application=self.app)
        self.app.refresh_from_db()

        self.assertRedirects(response, reverse("contract_signature", args=[contract.id]))
        self.assertTrue(contract.terms_accepted_by_merchant)
        self.assertTrue(contract.contract_number.startswith("E"))
        self.assertEqual(len(contract.contract_number), 9)
        self.assertEqual(self.app.status, "contract_signature")

    def test_contract_numbers_are_unique(self):
        numbers = {Contract.from_application(self.app)[0].contract_number}
        for index in range(3):
            app = FinancingApplication.objects.create(
                created_by=self.merchant,
                status="approved",
                customer_name=f"Customer {index}",
            )
            numbers.add(Contract.from_application(app)[0].contract_number)

        self.assertEqual(len(numbers), 4)

    def test_contract_signature_requires_signature_and_terms(self):
        contract = Contract.from_application(self.app)[0]

        response = self.client.post(reverse("contract_signature", args=[contract.id]), {"customer_terms_accepted": "on"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Save the customer contract signature before continuing.")

        response = self.client.post(
            reverse("contract_signature", args=[contract.id]),
            {"signature_data": signature_data(), "customer_terms_accepted": "on"},
        )
        contract.refresh_from_db()
        self.app.refresh_from_db()

        self.assertRedirects(response, reverse("contract_imei", args=[contract.id]))
        self.assertTrue(contract.customer_contract_signature)
        self.assertTrue(contract.customer_terms_accepted)
        self.assertEqual(self.app.status, "imei_entry")

    def test_imei_must_be_exactly_15_digits(self):
        self.assertTrue(ImeiForm(data={"imei_number": "123456789012345"}).is_valid())
        self.assertFalse(ImeiForm(data={"imei_number": "1234567890123456"}).is_valid())
        self.assertFalse(ImeiForm(data={"imei_number": "12345abc9012345"}).is_valid())

    def test_progress_steps_complete_contract_and_award_merchant(self):
        contract = Contract.from_application(self.app)[0]
        contract.status = Contract.STATUS_IMEI_ENTERED
        contract.imei_number = "123456789012345"
        contract.save()

        self.client.get(reverse("contract_progress", args=[contract.id]))
        contract.refresh_from_db()
        self.app.refresh_from_db()
        self.assertEqual(contract.status, Contract.STATUS_CONTRACT_CREATED)
        self.assertEqual(self.app.status, "warranty_check")

        self.client.post(reverse("contract_progress", args=[contract.id]), {"action": "warranty"})
        self.client.post(reverse("contract_progress", args=[contract.id]), {"action": "locked"})
        response = self.client.post(reverse("contract_progress", args=[contract.id]), {"action": "deposit"})
        contract.refresh_from_db()
        self.app.refresh_from_db()

        self.assertRedirects(response, reverse("contract_complete", args=[contract.id]))
        self.assertTrue(contract.warranty_checked)
        self.assertTrue(contract.phone_locked)
        self.assertTrue(contract.deposit_paid)
        self.assertEqual(contract.status, Contract.STATUS_COMPLETE)
        self.assertEqual(self.app.status, "contract_complete")
        self.assertTrue(Commission.objects.filter(application=self.app, role=Commission.ROLE_MERCHANT).exists())
        self.assertEqual(SpinWallet.objects.get(user=self.merchant).available_spins, 1)

    def test_only_creator_or_staff_can_access_contract_flow(self):
        self.client.login(username="other", password="test-pass-123")

        response = self.client.get(reverse("contract_terms", args=[self.app.id]))

        self.assertEqual(response.status_code, 403)

    def test_contract_detail_requires_permission(self):
        contract = Contract.from_application(self.app)[0]
        self.client.login(username="other", password="test-pass-123")

        response = self.client.get(reverse("contract_detail", args=[contract.id]))

        self.assertEqual(response.status_code, 403)

    def test_contract_detail_shows_contract_number_and_amounts(self):
        contract = Contract.from_application(self.app)[0]

        response = self.client.get(reverse("contract_detail", args=[contract.id]))

        self.assertContains(response, contract.contract_number)
        self.assertContains(response, "Cash price")
        self.assertContains(response, "Merchant price / financed amount")
        self.assertContains(response, "Total loan")
        self.assertContains(response, "875,000")

    def test_view_contract_link_appears_only_when_contract_exists(self):
        no_contract_app = FinancingApplication.objects.create(created_by=self.merchant, status="completed")
        contract = Contract.from_application(self.app)[0]

        no_contract_response = self.client.get(reverse("application_detail", args=[no_contract_app.id]))
        contract_response = self.client.get(reverse("application_detail", args=[self.app.id]))

        self.assertNotContains(no_contract_response, "VIEW CONTRACT")
        self.assertContains(contract_response, "VIEW CONTRACT")
        self.assertContains(contract_response, reverse("contract_detail", args=[contract.id]))

    def test_contract_complete_page_shows_contract_number(self):
        contract = Contract.from_application(self.app)[0]
        contract.status = Contract.STATUS_COMPLETE
        contract.deposit_paid = True
        contract.save()
        self.app.status = "contract_complete"
        self.app.save(update_fields=["status"])

        response = self.client.get(reverse("contract_complete", args=[contract.id]))

        self.assertContains(response, "Contract complete")
        self.assertContains(response, contract.contract_number)
