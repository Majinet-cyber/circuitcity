from datetime import datetime, time, timedelta

from django.db import transaction
from django.utils import timezone

from integrations.mock_lock_provider import MockLockProvider
from .models import (
    Device,
    DeviceCommand,
    DeviceStatusLog,
    FinancingContract,
    PaymentRecord,
    RepaymentSchedule,
    UnlockToken,
)


def unlock_valid_until_from_contract(contract):
    due_date = contract.next_due_date or timezone.localdate() + timedelta(days=30)
    return timezone.make_aware(datetime.combine(due_date, time.max))


def generate_unlock_token(contract, generated_by=None, valid_until=None):
    valid_until = valid_until or unlock_valid_until_from_contract(contract)
    token = UnlockToken.objects.create(
        contract=contract,
        device=contract.device,
        customer=contract.customer,
        valid_until=valid_until,
        generated_by=generated_by,
    )
    DeviceStatusLog.objects.create(
        device=contract.device,
        contract=contract,
        action=DeviceStatusLog.ACTION_UNLOCK_GENERATED,
        status_before=contract.device.status,
        status_after=contract.device.status,
        notes="Unlock PIN generated. Native device unlock integration pending.",
        created_by=generated_by,
    )
    return token


def apply_payment_to_schedule(contract, amount):
    remaining = amount
    for row in contract.repayment_schedule.exclude(status=RepaymentSchedule.STATUS_PAID).order_by("due_date", "id"):
        if remaining <= 0:
            break
        applied = min(row.balance_due, remaining)
        row.amount_paid += applied
        remaining -= applied
        if row.amount_paid >= row.amount_due:
            row.status = RepaymentSchedule.STATUS_PAID
            row.paid_at = timezone.now()
        elif row.amount_paid > 0:
            row.status = RepaymentSchedule.STATUS_PARTIALLY_PAID
        row.save(update_fields=["amount_paid", "status", "paid_at"])
    return remaining


@transaction.atomic
def verify_payment(payment, verified_by=None):
    if payment.verification_status == PaymentRecord.STATUS_VERIFIED:
        return payment, payment.contract.latest_unlock_token

    payment.verification_status = PaymentRecord.STATUS_VERIFIED
    payment.verified_by = verified_by
    payment.verified_at = timezone.now()
    payment.rejection_reason = ""
    payment.save(update_fields=["verification_status", "verified_by", "verified_at", "rejection_reason"])

    contract = payment.contract
    apply_payment_to_schedule(contract, payment.amount)
    next_unpaid = contract.repayment_schedule.exclude(status=RepaymentSchedule.STATUS_PAID).order_by("due_date", "id").first()
    previous_device_status = contract.device.status

    if next_unpaid:
        contract.next_due_date = next_unpaid.due_date
        contract.status = FinancingContract.STATUS_ACTIVE
    else:
        contract.status = FinancingContract.STATUS_COMPLETED
        contract.device.status = Device.STATUS_COMPLETED
        contract.device.save(update_fields=["status"])

    contract.save(update_fields=["next_due_date", "status", "updated_at"])

    if contract.device.status != Device.STATUS_COMPLETED:
        contract.device.status = Device.STATUS_UNLOCKED
        contract.device.save(update_fields=["status"])

    DeviceStatusLog.objects.create(
        device=contract.device,
        contract=contract,
        action=DeviceStatusLog.ACTION_PAYMENT_VERIFIED,
        status_before=previous_device_status,
        status_after=contract.device.status,
        notes=f"Payment {payment.id} verified manually.",
        created_by=verified_by,
    )
    token = generate_unlock_token(contract, generated_by=verified_by)
    issue_device_command(contract, DeviceCommand.TYPE_UNLOCK, created_by=verified_by, valid_until=token.valid_until)
    return payment, token


@transaction.atomic
def reject_payment(payment, rejected_by=None, reason=""):
    payment.verification_status = PaymentRecord.STATUS_REJECTED
    payment.verified_by = rejected_by
    payment.verified_at = timezone.now()
    payment.rejection_reason = reason
    payment.save(update_fields=["verification_status", "verified_by", "verified_at", "rejection_reason"])
    return payment


def issue_device_command(contract, command_type, created_by=None, provider_name=DeviceCommand.PROVIDER_MOCK, valid_until=None):
    command = DeviceCommand.objects.create(
        device=contract.device,
        contract=contract,
        command_type=command_type,
        provider=provider_name,
        status=DeviceCommand.STATUS_SENT,
        request_payload={"contract_id": contract.id, "device_id": contract.device_id},
        created_by=created_by,
    )
    provider = MockLockProvider()
    try:
        if command_type == DeviceCommand.TYPE_LOCK:
            result = provider.lock_device(contract.device)
            action = DeviceStatusLog.ACTION_LOCK_REQUESTED
        elif command_type == DeviceCommand.TYPE_UNLOCK:
            result = provider.unlock_device(contract.device, valid_until or unlock_valid_until_from_contract(contract))
            action = DeviceStatusLog.ACTION_UNLOCK_REQUESTED
        elif command_type == DeviceCommand.TYPE_REGISTER:
            result = provider.register_device(contract.device, contract)
            action = DeviceStatusLog.ACTION_REGISTERED
        elif command_type == DeviceCommand.TYPE_REFRESH_STATUS:
            result = provider.get_device_status(contract.device)
            action = DeviceStatusLog.ACTION_UNLOCK_REQUESTED
        else:
            result = {"success": True, "message": f"Mock {command_type} command accepted."}
            action = DeviceStatusLog.ACTION_UNLOCK_REQUESTED
        command.status = DeviceCommand.STATUS_SUCCESSFUL if result.get("success") else DeviceCommand.STATUS_FAILED
        command.response_payload = result
        command.completed_at = timezone.now()
        command.save(update_fields=["status", "response_payload", "completed_at"])
        DeviceStatusLog.objects.create(
            device=contract.device,
            contract=contract,
            action=action,
            status_before=contract.device.status,
            status_after=contract.device.status,
            notes=result.get("message", ""),
            created_by=created_by,
        )
    except Exception as exc:
        command.status = DeviceCommand.STATUS_FAILED
        command.error_message = str(exc)
        command.completed_at = timezone.now()
        command.save(update_fields=["status", "error_message", "completed_at"])
    return command


def build_repayment_schedule(contract):
    if contract.repayment_schedule.exists():
        return
    start = contract.start_date
    for month in range(contract.term_months):
        RepaymentSchedule.objects.create(
            contract=contract,
            due_date=start + timedelta(days=30 * (month + 1)),
            amount_due=contract.monthly_payment_amount,
        )
