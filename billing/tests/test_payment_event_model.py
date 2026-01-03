# billing/tests/test_payment_event_model.py
"""
Tests for PaymentEvent model - idempotency and audit trail.
"""
import hashlib
from decimal import Decimal

import pytest
from django.db import IntegrityError
from django.utils import timezone

from billing.models import PaymentEvent
from tests.helpers.tenant_setup import make_business, make_user


@pytest.mark.django_db
class TestPaymentEventModel:
    """Test PaymentEvent model creation and constraints."""

    def test_create_payment_event(self):
        """Test creating a PaymentEvent with all fields."""
        event = PaymentEvent.objects.create(
            provider=PaymentEvent.Provider.PAYCHANGU,
            event_id="evt_12345",
            idempotency_key="paychangu_tx123_payment.success_5000_MWK",
            reference="tx-ref-123",
            transaction_id="txn-456",
            event_type="payment.success",
            payload_json={"amount": "5000", "currency": "MWK"},
            signature_valid=True,
            status=PaymentEvent.Status.RECEIVED,
        )

        assert event.id is not None
        assert event.provider == PaymentEvent.Provider.PAYCHANGU
        assert event.idempotency_key == "paychangu_tx123_payment.success_5000_MWK"
        assert event.signature_valid is True
        assert event.status == PaymentEvent.Status.RECEIVED
        assert event.received_at is not None
        assert event.processed_at is None

    def test_idempotency_key_unique_constraint(self):
        """Test that idempotency_key must be unique."""
        idempotency_key = "unique_key_123"

        PaymentEvent.objects.create(
            provider=PaymentEvent.Provider.PAYCHANGU,
            idempotency_key=idempotency_key,
            reference="tx-1",
        )

        # Attempting to create another event with same idempotency_key should fail
        with pytest.raises(IntegrityError):
            PaymentEvent.objects.create(
                provider=PaymentEvent.Provider.PAYCHANGU,
                idempotency_key=idempotency_key,
                reference="tx-2",
            )

    def test_mark_processed(self):
        """Test marking event as processed."""
        event = PaymentEvent.objects.create(
            provider=PaymentEvent.Provider.PAYCHANGU,
            idempotency_key="test_processed_123",
            reference="tx-123",
            status=PaymentEvent.Status.RECEIVED,
        )

        assert event.status == PaymentEvent.Status.RECEIVED
        assert event.processed_at is None

        event.mark_processed()

        event.refresh_from_db()
        assert event.status == PaymentEvent.Status.PROCESSED
        assert event.processed_at is not None

    def test_mark_failed(self):
        """Test marking event as failed with error message."""
        event = PaymentEvent.objects.create(
            provider=PaymentEvent.Provider.PAYCHANGU,
            idempotency_key="test_failed_456",
            reference="tx-456",
            status=PaymentEvent.Status.RECEIVED,
        )

        error_msg = "Transaction verification failed"
        event.mark_failed(error_msg)

        event.refresh_from_db()
        assert event.status == PaymentEvent.Status.FAILED
        assert event.error_message == error_msg
        assert event.processed_at is not None

    def test_mark_ignored(self):
        """Test marking event as ignored."""
        event = PaymentEvent.objects.create(
            provider=PaymentEvent.Provider.PAYCHANGU,
            idempotency_key="test_ignored_789",
            reference="tx-789",
            status=PaymentEvent.Status.RECEIVED,
        )

        reason = "Transaction already processed"
        event.mark_ignored(reason)

        event.refresh_from_db()
        assert event.status == PaymentEvent.Status.IGNORED
        assert event.error_message == reason
        assert event.processed_at is not None

    def test_get_or_create_idempotency(self):
        """Test get_or_create pattern for idempotency."""
        idempotency_key = "test_idempotent_abc"

        # First call creates
        event1, created1 = PaymentEvent.objects.get_or_create(
            idempotency_key=idempotency_key,
            defaults={
                "provider": PaymentEvent.Provider.PAYCHANGU,
                "reference": "tx-abc",
                "event_type": "payment.success",
            },
        )

        assert created1 is True
        assert event1.status == PaymentEvent.Status.RECEIVED

        # Second call retrieves existing
        event2, created2 = PaymentEvent.objects.get_or_create(
            idempotency_key=idempotency_key,
            defaults={
                "provider": PaymentEvent.Provider.PAYCHANGU,
                "reference": "tx-abc-duplicate",
                "event_type": "payment.success",
            },
        )

        assert created2 is False
        assert event2.id == event1.id
        assert event2.reference == "tx-abc"  # Original reference, not duplicate

    def test_compute_idempotency_key_deterministic(self):
        """Test that idempotency key computation is deterministic."""
        provider = "paychangu"
        tx_ref = "tx-ref-123"
        event_type = "payment.success"
        amount = "5000"
        currency = "MWK"

        # Compute idempotency key (same logic as webhook will use)
        key_input = f"{provider}:{tx_ref}:{event_type}:{amount}:{currency}"
        idempotency_key = hashlib.sha256(key_input.encode()).hexdigest()

        # Create two events with same inputs
        event1 = PaymentEvent.objects.create(
            provider=PaymentEvent.Provider.PAYCHANGU,
            idempotency_key=idempotency_key,
            reference=tx_ref,
            event_type=event_type,
            payload_json={"amount": amount, "currency": currency},
        )

        # Verify we can't create duplicate
        with pytest.raises(IntegrityError):
            PaymentEvent.objects.create(
                provider=PaymentEvent.Provider.PAYCHANGU,
                idempotency_key=idempotency_key,
                reference=tx_ref,
                event_type=event_type,
                payload_json={"amount": amount, "currency": currency},
            )

    def test_event_ordering(self):
        """Test that events are ordered by received_at descending."""
        event1 = PaymentEvent.objects.create(
            provider=PaymentEvent.Provider.PAYCHANGU,
            idempotency_key="test_order_1",
            reference="tx-1",
        )

        event2 = PaymentEvent.objects.create(
            provider=PaymentEvent.Provider.PAYCHANGU,
            idempotency_key="test_order_2",
            reference="tx-2",
        )

        events = list(PaymentEvent.objects.all())
        # Most recent first
        assert events[0].id == event2.id
        assert events[1].id == event1.id

    def test_signature_valid_default_false(self):
        """Test that signature_valid defaults to False."""
        event = PaymentEvent.objects.create(
            provider=PaymentEvent.Provider.PAYCHANGU,
            idempotency_key="test_sig_default",
            reference="tx-sig",
        )

        assert event.signature_valid is False

    def test_meta_field_stores_arbitrary_data(self):
        """Test that meta field can store arbitrary JSON data."""
        event = PaymentEvent.objects.create(
            provider=PaymentEvent.Provider.PAYCHANGU,
            idempotency_key="test_meta_123",
            reference="tx-meta",
            meta={
                "business_id": "abc-123",
                "user_email": "test@example.com",
                "retry_count": 0,
            },
        )

        event.refresh_from_db()
        assert event.meta["business_id"] == "abc-123"
        assert event.meta["user_email"] == "test@example.com"
        assert event.meta["retry_count"] == 0


@pytest.mark.django_db
class TestPaymentEventIndexes:
    """Test that database indexes work correctly."""

    def test_query_by_provider_and_reference(self):
        """Test querying by provider and reference (indexed)."""
        PaymentEvent.objects.create(
            provider=PaymentEvent.Provider.PAYCHANGU,
            idempotency_key="test_idx_1",
            reference="tx-ref-abc",
        )

        PaymentEvent.objects.create(
            provider=PaymentEvent.Provider.STRIPE,
            idempotency_key="test_idx_2",
            reference="tx-ref-xyz",
        )

        # Query by provider and reference
        events = PaymentEvent.objects.filter(provider=PaymentEvent.Provider.PAYCHANGU, reference="tx-ref-abc")

        assert events.count() == 1
        assert events.first().reference == "tx-ref-abc"

    def test_query_by_status_and_received_at(self):
        """Test querying by status and received_at (indexed)."""
        event1 = PaymentEvent.objects.create(
            provider=PaymentEvent.Provider.PAYCHANGU,
            idempotency_key="test_idx_3",
            reference="tx-1",
            status=PaymentEvent.Status.RECEIVED,
        )

        event2 = PaymentEvent.objects.create(
            provider=PaymentEvent.Provider.PAYCHANGU,
            idempotency_key="test_idx_4",
            reference="tx-2",
            status=PaymentEvent.Status.PROCESSED,
        )

        # Query unprocessed events
        unprocessed = PaymentEvent.objects.filter(status=PaymentEvent.Status.RECEIVED).order_by("-received_at")

        assert unprocessed.count() == 1
        assert unprocessed.first().id == event1.id
