# inventory/tests/test_mobile_money_providers.py
"""
Mobile Money Agent Vertical Tests
===================================

Tests cover:
- All provider types (Airtel, TNM, Bank, Other)
- Cash-in and cash-out transaction recording
- Commission recording
- Daily reconciliation shortage/surplus calculation
"""
from decimal import Decimal
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone

from tenants.models import Business
from inventory.business_kinds import BusinessKind
from inventory.models_mobilemoney import (
    MobileMoneyNetwork,
    MobileMoneyTransaction,
    MobileMoneyTxType,
    MobileMoneyReconciliation,
    TX_MOVEMENTS,
)

User = get_user_model()


def _make_business():
    import random
    uid = random.randint(1000, 9999)
    return Business.objects.create(
        name=f"Test MM Agent {uid}",
        business_kind=BusinessKind.MOBILE_MONEY,
    )


def _make_user():
    import random
    uid = random.randint(1000, 9999)
    return User.objects.create_user(
        username=f"mm_user_{uid}",
        password="test123",
    )


class MobileMoneyProviderTest(TestCase):
    """Test all provider types are supported."""

    def setUp(self):
        self.business = _make_business()
        self.user = _make_user()

    def test_airtel_money_provider(self):
        """Can create Airtel Money transaction."""
        tx = MobileMoneyTransaction.objects.create(
            business=self.business,
            network=MobileMoneyNetwork.AIRTEL,
            tx_type=MobileMoneyTxType.CASH_IN,
            amount=Decimal("10000"),
            reference_number="AIRTEL001",
            created_by=self.user,
        )
        self.assertEqual(tx.network, MobileMoneyNetwork.AIRTEL)

    def test_tnm_mpamba_provider(self):
        """Can create TNM Mpamba transaction."""
        tx = MobileMoneyTransaction.objects.create(
            business=self.business,
            network=MobileMoneyNetwork.TNM,
            tx_type=MobileMoneyTxType.CASH_IN,
            amount=Decimal("5000"),
            created_by=self.user,
        )
        self.assertEqual(tx.network, MobileMoneyNetwork.TNM)

    def test_bank_agent_provider(self):
        """Can create Bank Agent transaction."""
        tx = MobileMoneyTransaction.objects.create(
            business=self.business,
            network=MobileMoneyNetwork.BANK,
            tx_type=MobileMoneyTxType.CASH_IN,
            amount=Decimal("50000"),
            created_by=self.user,
        )
        self.assertEqual(tx.network, MobileMoneyNetwork.BANK)

    def test_other_custom_provider(self):
        """Can create Other/Custom provider transaction."""
        tx = MobileMoneyTransaction.objects.create(
            business=self.business,
            network=MobileMoneyNetwork.OTHER,
            tx_type=MobileMoneyTxType.CASH_IN,
            amount=Decimal("2000"),
            created_by=self.user,
        )
        self.assertEqual(tx.network, MobileMoneyNetwork.OTHER)

    def test_all_providers_have_choices(self):
        """All four provider types appear in MobileMoneyNetwork choices."""
        choice_values = [v for v, _ in MobileMoneyNetwork.choices]
        self.assertIn("airtel", choice_values)
        self.assertIn("tnm", choice_values)
        self.assertIn("bank", choice_values)
        self.assertIn("other", choice_values)


class MobileMoneyTransactionTest(TestCase):
    """Test cash-in and cash-out transaction recording."""

    def setUp(self):
        self.business = _make_business()
        self.user = _make_user()

    def test_cash_in_movement_definition(self):
        """TX_MOVEMENTS for cash_in: cash is positive (agent receives cash from customer)."""
        cash_sign, float_sign = TX_MOVEMENTS[MobileMoneyTxType.CASH_IN]
        self.assertEqual(cash_sign, 1, "Cash-in should add to cash (+1)")
        self.assertEqual(float_sign, -1, "Cash-in should reduce float (-1)")

    def test_cash_out_movement_definition(self):
        """TX_MOVEMENTS for cash_out: agent pays out cash, gains float."""
        cash_sign, float_sign = TX_MOVEMENTS[MobileMoneyTxType.CASH_OUT]
        self.assertEqual(cash_sign, -1, "Cash-out should subtract from cash (-1)")
        self.assertEqual(float_sign, 1, "Cash-out should add to float (+1)")

    def test_transaction_with_commission(self):
        """Can record a transaction with commission."""
        tx = MobileMoneyTransaction.objects.create(
            business=self.business,
            network=MobileMoneyNetwork.AIRTEL,
            tx_type=MobileMoneyTxType.CASH_IN,
            amount=Decimal("20000"),
            commission=Decimal("200"),
            created_by=self.user,
        )
        self.assertEqual(tx.commission, Decimal("200"))

    def test_transaction_all_types_creatable(self):
        """All major transaction types can be created."""
        tx_types = [
            MobileMoneyTxType.CASH_IN,
            MobileMoneyTxType.CASH_OUT,
            MobileMoneyTxType.BILL_PAYMENT,
            MobileMoneyTxType.FLOAT_PURCHASE,
            MobileMoneyTxType.REVERSAL,
        ]
        for tx_type in tx_types:
            tx = MobileMoneyTransaction.objects.create(
                business=self.business,
                network=MobileMoneyNetwork.AIRTEL,
                tx_type=tx_type,
                amount=Decimal("1000"),
                created_by=self.user,
            )
            self.assertEqual(tx.tx_type, tx_type)

    def test_commission_defaults_to_zero(self):
        """Commission defaults to 0 if not specified."""
        tx = MobileMoneyTransaction.objects.create(
            business=self.business,
            network=MobileMoneyNetwork.TNM,
            tx_type=MobileMoneyTxType.CASH_OUT,
            amount=Decimal("5000"),
        )
        self.assertEqual(tx.commission, Decimal("0.00"))


class MobileMoneyReconciliationTest(TestCase):
    """Test daily reconciliation calculation."""

    def setUp(self):
        self.business = _make_business()
        self.user = _make_user()

    def test_reconciliation_creates_successfully(self):
        """Can create a daily reconciliation record."""
        today = timezone.localdate()
        recon = MobileMoneyReconciliation.objects.create(
            business=self.business,
            date=today,
            opening_cash=Decimal("50000"),
            opening_float=Decimal("100000"),
            total_cash_in=Decimal("30000"),
            total_cash_out=Decimal("35000"),
            actual_closing_cash=Decimal("45000"),
        )
        self.assertEqual(recon.date, today)
        self.assertEqual(recon.opening_cash, Decimal("50000"))

    def test_reconciliation_calculates_expected_closing_cash(self):
        """expected_closing_cash = opening_cash + total_cash_in - total_cash_out."""
        today = timezone.localdate()
        recon = MobileMoneyReconciliation.objects.create(
            business=self.business,
            date=today,
            opening_cash=Decimal("50000"),
            total_cash_in=Decimal("30000"),
            total_cash_out=Decimal("10000"),
            actual_closing_cash=Decimal("70000"),
        )
        expected = Decimal("50000") + Decimal("30000") - Decimal("10000")
        self.assertEqual(recon.expected_closing_cash, expected)

    def test_reconciliation_calculates_difference(self):
        """difference = actual_closing_cash - expected_closing_cash (negative = shortage)."""
        today = timezone.localdate()
        recon = MobileMoneyReconciliation.objects.create(
            business=self.business,
            date=today,
            opening_cash=Decimal("50000"),
            total_cash_in=Decimal("30000"),
            total_cash_out=Decimal("10000"),
            actual_closing_cash=Decimal("65000"),  # expected = 70000, so difference = -5000
        )
        self.assertEqual(recon.difference, Decimal("-5000"))

    def test_reconciliation_shortage_status_label(self):
        """status_label is 'shortage' when difference is significantly negative."""
        today = timezone.localdate()
        recon = MobileMoneyReconciliation.objects.create(
            business=self.business,
            date=today,
            opening_cash=Decimal("50000"),
            total_cash_in=Decimal("30000"),
            total_cash_out=Decimal("10000"),
            actual_closing_cash=Decimal("60000"),  # expected=70000, diff=-10000
        )
        self.assertEqual(recon.status_label, "shortage")

    def test_reconciliation_balanced_status_label(self):
        """status_label is 'balanced' when difference is zero."""
        today = timezone.localdate()
        recon = MobileMoneyReconciliation.objects.create(
            business=self.business,
            date=today,
            opening_cash=Decimal("50000"),
            total_cash_in=Decimal("20000"),
            total_cash_out=Decimal("10000"),
            actual_closing_cash=Decimal("60000"),  # expected=60000, diff=0
        )
        self.assertEqual(recon.status_label, "balanced")

    def test_reconciliation_unique_per_day(self):
        """Can only have one reconciliation per business per day."""
        from django.db import IntegrityError
        today = timezone.localdate()
        MobileMoneyReconciliation.objects.create(
            business=self.business,
            date=today,
            opening_cash=Decimal("10000"),
            actual_closing_cash=Decimal("10000"),
        )
        with self.assertRaises(IntegrityError):
            MobileMoneyReconciliation.objects.create(
                business=self.business,
                date=today,
                opening_cash=Decimal("20000"),
                actual_closing_cash=Decimal("20000"),
            )
