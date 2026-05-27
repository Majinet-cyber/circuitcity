"""
Portal app tests — Phase 5.

Coverage:
- PaymentContract number uniqueness (TS-MW-XXXXXXXX)
- PayG number uniqueness (TSGXXXXXX)
- calculate_daily_price accuracy
- calculate_thirty_day_price accuracy
- Early settlement (3/6/9/12 months) discount calculations
- apply_payment_to_contract — arrears cleared first, days extended
- Portal search by contract number / PayG / national ID / phone
- Mock payment provider returns paid status
- Portal search page renders (200)
- Portal contract page renders (200) after seeding
"""

from decimal import Decimal
from datetime import date, timedelta

from django.test import TestCase, Client
from django.utils import timezone

from portal.models import PaymentContract, PaymentTransaction, generate_contract_number, generate_payg_number
from portal.services import (
    calculate_daily_price,
    calculate_thirty_day_price,
    calculate_remaining_amount,
    calculate_early_settlement_options,
    apply_payment_to_contract,
    search_payment_contract,
)
from portal.payment_providers import MockPaymentProvider


# ---------------------------------------------------------------------------
# Model number generation tests
# ---------------------------------------------------------------------------

class ContractNumberGenerationTest(TestCase):
    def test_contract_number_format(self):
        n = generate_contract_number()
        self.assertRegex(n, r"^TS-MW-\d{8}$")

    def test_payg_number_format(self):
        n = generate_payg_number()
        self.assertRegex(n, r"^TSG\d{6}$")

    def test_contract_number_uniqueness(self):
        nums = {generate_contract_number() for _ in range(20)}
        self.assertEqual(len(nums), 20)

    def test_payg_number_uniqueness(self):
        nums = {generate_payg_number() for _ in range(20)}
        self.assertEqual(len(nums), 20)

    def test_auto_assigned_on_save(self):
        c = PaymentContract.objects.create(
            customer_name="Auto Test",
            customer_phone="+265881234567",
            total_amount=Decimal("10000.00"),
        )
        self.assertRegex(c.contract_number, r"^TS-MW-\d{8}$")
        self.assertRegex(c.payg_number, r"^TSG\d{6}$")

    def test_no_duplicate_contract_numbers(self):
        c1 = PaymentContract.objects.create(
            customer_name="Test A",
            customer_phone="+265881111111",
            total_amount=Decimal("10000.00"),
        )
        c2 = PaymentContract.objects.create(
            customer_name="Test B",
            customer_phone="+265882222222",
            total_amount=Decimal("10000.00"),
        )
        self.assertNotEqual(c1.contract_number, c2.contract_number)
        self.assertNotEqual(c1.payg_number, c2.payg_number)


# ---------------------------------------------------------------------------
# Pricing calculation tests
# ---------------------------------------------------------------------------

class PricingCalculationTest(TestCase):
    def test_daily_price_standard(self):
        # MWK 45,000 over 12 months = 45000 / (12 * 30) = 45000 / 360 = 125
        result = calculate_daily_price(Decimal("45000"), 12)
        self.assertEqual(result, Decimal("125.00"))

    def test_daily_price_zero_term(self):
        result = calculate_daily_price(Decimal("45000"), 0)
        self.assertEqual(result, Decimal("0"))

    def test_daily_price_zero_amount(self):
        result = calculate_daily_price(Decimal("0"), 12)
        self.assertEqual(result, Decimal("0"))

    def test_thirty_day_price_standard(self):
        # 45000 / 12 = 3750
        result = calculate_thirty_day_price(Decimal("45000"), 12)
        self.assertEqual(result, Decimal("3750.00"))

    def test_thirty_day_price_zero_amount(self):
        result = calculate_thirty_day_price(Decimal("0"), 12)
        self.assertEqual(result, Decimal("0"))

    def test_thirty_day_price_rounding(self):
        # 10000 / 3 = 3333.33...
        result = calculate_thirty_day_price(Decimal("10000"), 3)
        self.assertEqual(result, Decimal("3333.33"))

    def test_remaining_amount(self):
        c = PaymentContract(total_amount=Decimal("10000"), amount_paid=Decimal("3000"))
        self.assertEqual(calculate_remaining_amount(c), Decimal("7000"))

    def test_remaining_amount_floor_zero(self):
        c = PaymentContract(total_amount=Decimal("5000"), amount_paid=Decimal("6000"))
        self.assertEqual(calculate_remaining_amount(c), Decimal("0"))


# ---------------------------------------------------------------------------
# Early settlement tests
# ---------------------------------------------------------------------------

class EarlySettlementTest(TestCase):
    def setUp(self):
        self.contract = PaymentContract(
            total_amount=Decimal("45000"),
            amount_paid=Decimal("0"),
            daily_price=Decimal("125"),
            thirty_day_price=Decimal("3750"),
            term_months=12,
            early_settlement_3m_discount=Decimal("25"),
            early_settlement_6m_discount=Decimal("15"),
            early_settlement_9m_discount=Decimal("8"),
            start_date=date.today(),
        )

    def test_returns_four_options(self):
        opts = calculate_early_settlement_options(self.contract)
        self.assertEqual(len(opts), 4)

    def test_3_month_discount(self):
        opts = calculate_early_settlement_options(self.contract)
        opt = next(o for o in opts if o["term_months"] == 3)
        expected_remaining = Decimal("45000") * Decimal("0.75")
        self.assertEqual(opt["remaining_to_pay"], expected_remaining.quantize(Decimal("0.01")))

    def test_6_month_discount(self):
        opts = calculate_early_settlement_options(self.contract)
        opt = next(o for o in opts if o["term_months"] == 6)
        expected_remaining = Decimal("45000") * Decimal("0.85")
        self.assertEqual(opt["remaining_to_pay"], expected_remaining.quantize(Decimal("0.01")))

    def test_12_month_no_discount(self):
        opts = calculate_early_settlement_options(self.contract)
        opt = next(o for o in opts if o["term_months"] == 12)
        self.assertEqual(opt["discount_percent"], Decimal("0"))
        self.assertEqual(opt["remaining_to_pay"], Decimal("45000"))

    def test_partial_paid_reduces_remaining(self):
        self.contract.amount_paid = Decimal("10000")
        opts = calculate_early_settlement_options(self.contract)
        opt = next(o for o in opts if o["term_months"] == 3)
        expected_remaining = Decimal("35000") * Decimal("0.75")
        self.assertEqual(opt["remaining_to_pay"], expected_remaining.quantize(Decimal("0.01")))


# ---------------------------------------------------------------------------
# Payment allocation tests
# ---------------------------------------------------------------------------

class PaymentAllocationTest(TestCase):
    def _make_contract(self, **kwargs):
        defaults = dict(
            customer_name="Test Customer",
            customer_phone="+265880000001",
            total_amount=Decimal("45000"),
            amount_paid=Decimal("0"),
            daily_price=Decimal("125"),
            thirty_day_price=Decimal("3750"),
            term_months=12,
            start_date=date.today(),
            status="active",
        )
        defaults.update(kwargs)
        return PaymentContract.objects.create(**defaults)

    def test_payment_increases_amount_paid(self):
        c = self._make_contract()
        apply_payment_to_contract(c, Decimal("3750"))
        c.refresh_from_db()
        self.assertEqual(c.amount_paid, Decimal("3750"))

    def test_payment_does_not_exceed_remaining(self):
        c = self._make_contract(amount_paid=Decimal("44500"))
        result = apply_payment_to_contract(c, Decimal("1000"))
        c.refresh_from_db()
        self.assertEqual(c.amount_paid, c.total_amount)
        self.assertEqual(result["applied"], Decimal("500"))

    def test_payment_completes_contract(self):
        c = self._make_contract(amount_paid=Decimal("44000"))
        apply_payment_to_contract(c, Decimal("1000"))
        c.refresh_from_db()
        self.assertEqual(c.status, "completed")

    def test_daily_price_extends_due_date(self):
        start = date.today() - timedelta(days=5)
        c = self._make_contract(start_date=start)
        apply_payment_to_contract(c, Decimal("125"))  # 1 day
        c.refresh_from_db()
        self.assertIsNotNone(c.due_date)

    def test_zero_payment_rejected(self):
        c = self._make_contract()
        result = apply_payment_to_contract(c, Decimal("0"))
        self.assertEqual(result["applied"], Decimal("0"))


# ---------------------------------------------------------------------------
# Search tests
# ---------------------------------------------------------------------------

class PortalSearchTest(TestCase):
    def setUp(self):
        self.contract = PaymentContract.objects.create(
            customer_name="Mary Banda",
            customer_phone="+265881234567",
            customer_national_id="MW12345678",
            total_amount=Decimal("20000"),
        )

    def test_search_by_contract_number(self):
        result = search_payment_contract(self.contract.contract_number)
        self.assertEqual(result.pk, self.contract.pk)

    def test_search_by_payg_number(self):
        result = search_payment_contract(self.contract.payg_number)
        self.assertEqual(result.pk, self.contract.pk)

    def test_search_by_national_id(self):
        result = search_payment_contract("MW12345678")
        self.assertEqual(result.pk, self.contract.pk)

    def test_search_by_phone_last_9_digits(self):
        result = search_payment_contract("881234567")
        self.assertEqual(result.pk, self.contract.pk)

    def test_search_by_full_phone(self):
        result = search_payment_contract("+265881234567")
        self.assertEqual(result.pk, self.contract.pk)

    def test_search_returns_none_for_unknown(self):
        result = search_payment_contract("ZZZNOTHINGHERE")
        self.assertIsNone(result)

    def test_empty_query_returns_none(self):
        result = search_payment_contract("")
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# Mock payment provider test
# ---------------------------------------------------------------------------

class MockPaymentProviderTest(TestCase):
    def setUp(self):
        self.provider = MockPaymentProvider()

    def test_create_payment_intent_succeeds(self):
        result = self.provider.create_payment_intent(
            amount=Decimal("3750"),
            phone="+265881234567",
            reference="TS-PAY-TEST0001",
        )
        self.assertTrue(result.success)
        self.assertIn("MOCK-", result.provider_reference)

    def test_verify_payment_returns_paid(self):
        result = self.provider.verify_payment("MOCK-TS-PAY-TEST0001")
        self.assertTrue(result.paid)

    def test_mode_is_mock(self):
        self.assertEqual(self.provider.mode, "mock")

    def test_is_configured(self):
        self.assertTrue(self.provider.is_configured)


# ---------------------------------------------------------------------------
# Portal page smoke tests
# ---------------------------------------------------------------------------

class PortalPageTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.contract = PaymentContract.objects.create(
            customer_name="Test User",
            customer_phone="+265889990001",
            total_amount=Decimal("30000"),
            amount_paid=Decimal("5000"),
            daily_price=Decimal("83.33"),
            thirty_day_price=Decimal("2500"),
        )

    def test_search_page_renders(self):
        res = self.client.get("/pay/")
        self.assertEqual(res.status_code, 200)

    def test_contract_page_renders(self):
        res = self.client.get(f"/pay/contract/{self.contract.contract_number}/")
        self.assertEqual(res.status_code, 200)

    def test_history_page_renders(self):
        res = self.client.get(f"/pay/contract/{self.contract.contract_number}/history/")
        self.assertEqual(res.status_code, 200)

    def test_support_page_renders(self):
        res = self.client.get("/pay/support/")
        self.assertEqual(res.status_code, 200)

    def test_search_by_contract_number_redirects(self):
        res = self.client.get("/pay/search/", {"q": self.contract.contract_number})
        self.assertRedirects(res, f"/pay/contract/{self.contract.contract_number}/")

    def test_search_not_found_shows_error(self):
        res = self.client.get("/pay/search/", {"q": "TS-MW-99999999"})
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, "No contract found")

    def test_404_for_invalid_contract(self):
        res = self.client.get("/pay/contract/TS-MW-99999999/")
        self.assertEqual(res.status_code, 404)
