import hashlib, hmac, json
from decimal import Decimal
from django.conf import settings
from django.utils import timezone
from .models import PaymentIntent, CashLedger
from .utils import generate_pdf_receipt, send_email

def create_or_get_intent(payee_type, payee_id, purpose, amount, currency, idempotency_key, user, scheduled_for=None, meta=None):
    obj, created = PaymentIntent.objects.get_or_create(
        idempotency_key=idempotency_key,
        defaults=dict(
            payee_type=payee_type, payee_id=str(payee_id), purpose=purpose,
            amount=Decimal(amount), currency=currency, status="CREATED",
            scheduled_for=scheduled_for, meta=meta or {}, created_by=user
        )
    )
    return obj

def approve_intent(intent: PaymentIntent, approver):
    intent.approved_by = approver
    intent.approved_at = timezone.now()
    intent.status = "PENDING"
    intent.save()
    # TODO: call Airtel Money API here and set external_ref
    intent.external_ref = f"airtel-{intent.id}"
    intent.save()
    return intent

def handle_airtel_webhook(payload: bytes, signature: str):
    secret = settings.AIRTEL_WEBHOOK_SECRET.encode()
    expected = hmac.new(secret, payload, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        return False

    data = json.loads(payload.decode())
    ext = data.get("external_ref")
    status = data.get("status")  # "PAID" or "FAILED"
    intent = PaymentIntent.objects.filter(external_ref=ext).first()
    if not intent:
        return False

    intent.status = status
    intent.save()

    if status == "PAID":
        # write to ledger + generate receipt + email
        CashLedger.objects.create(entry_type="outflow", branch=None, amount=intent.amount, currency=intent.currency,
                                  date=timezone.now().date(), ref_type=intent.purpose, ref_id=str(intent.id),
                                  notes=f"Auto payout to {intent.payee_type}:{intent.payee_id}")
        pdf_path = generate_pdf_receipt(intent)
        send_email(
            to=data.get("email") or settings.FINANCE_EMAIL,
            subject=f"Payout receipt - {intent.purpose}",
            body=f"Payout {intent.amount} {intent.currency} successful.",
            attachments=[pdf_path]
        )
    return True


