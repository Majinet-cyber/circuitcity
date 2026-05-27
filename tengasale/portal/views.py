"""
Customer Payment Portal views — /pay/
"""

from decimal import Decimal

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import PaymentContract, PaymentTransaction
from .payment_providers import get_payment_provider
from .services import (
    apply_payment_to_contract,
    calculate_early_settlement_options,
    calculate_lock_date,
    calculate_remaining_amount,
    search_payment_contract,
)


def portal_search(request):
    """Landing / search page."""
    error = request.GET.get("error")
    return render(request, "portal/search.html", {
        "error": error,
        "query": request.GET.get("q", ""),
    })


def portal_search_post(request):
    """Process search and redirect to contract page."""
    q = request.GET.get("q", "").strip()
    if not q:
        return redirect("portal_search")

    contract = search_payment_contract(q)
    if contract:
        return redirect("portal_contract", contract_number=contract.contract_number)

    return render(request, "portal/search.html", {
        "searched": True,
        "query": q,
        "error": "No contract found matching that number, ID, or phone.",
    })


def portal_contract(request, contract_number):
    """Contract detail page — shows balance, payment form, early settlement."""
    contract = get_object_or_404(PaymentContract, contract_number=contract_number)

    remaining = calculate_remaining_amount(contract)
    early_options = calculate_early_settlement_options(contract)

    # Warning lock date
    lock_warning = None
    if contract.lock_date:
        days_until_lock = (contract.lock_date - timezone.localdate()).days
        if days_until_lock <= 7:
            lock_warning = {
                "date": contract.lock_date,
                "amount": contract.daily_price * max(days_until_lock, 0) if contract.daily_price else remaining,
                "days": days_until_lock,
            }

    recent_transactions = contract.transactions.filter(
        status=PaymentTransaction.STATUS_PAID
    ).order_by("-paid_at")[:10]

    return render(request, "portal/contract.html", {
        "contract": contract,
        "remaining": remaining,
        "early_options": early_options,
        "lock_warning": lock_warning,
        "recent_transactions": recent_transactions,
        "providers": [
            ("airtel_money", "Airtel Money"),
            ("tnm_mpamba", "TNM Mpamba"),
        ],
    })


@require_POST
def portal_payment(request, contract_number):
    """Initiate a payment."""
    contract = get_object_or_404(PaymentContract, contract_number=contract_number)

    if contract.status == PaymentContract.STATUS_COMPLETED:
        messages.info(request, "This contract is fully paid.")
        return redirect("portal_contract", contract_number=contract_number)

    # Parse form
    provider_name = request.POST.get("provider", "mock")
    phone_raw = request.POST.get("phone", "").strip()
    amount_raw = request.POST.get("amount", "0").strip()

    try:
        amount = Decimal(amount_raw)
    except Exception:
        messages.error(request, "Invalid amount.")
        return redirect("portal_contract", contract_number=contract_number)

    if amount < Decimal("100"):
        messages.error(request, "Minimum payment is MWK 100.")
        return redirect("portal_contract", contract_number=contract_number)

    remaining = calculate_remaining_amount(contract)
    if amount > remaining:
        amount = remaining

    # Build phone with +265 prefix
    phone = phone_raw.replace(" ", "")
    if not phone.startswith("+265") and not phone.startswith("265"):
        phone = f"+265{phone.lstrip('0')}"

    # Create transaction
    tx = PaymentTransaction.objects.create(
        payment_contract=contract,
        provider=provider_name,
        amount=amount,
        currency="MWK",
        phone=phone,
        status=PaymentTransaction.STATUS_PENDING,
    )

    # Initiate with provider
    provider = get_payment_provider(provider_name)
    result = provider.create_payment_intent(
        amount=amount,
        phone=phone,
        reference=tx.internal_reference,
        description=f"TengaSale contract {contract_number}",
    )

    tx.provider_reference = result.provider_reference
    tx.raw_response = result.raw

    if result.success:
        # For mock provider: immediately mark as paid and apply to contract
        if provider_name == "mock" or getattr(provider, "mode", "") == "mock":
            tx.status = PaymentTransaction.STATUS_PAID
            tx.paid_at = timezone.now()
            tx.save(update_fields=["provider_reference", "status", "paid_at", "raw_response"])
            apply_payment_to_contract(contract, amount)
            messages.success(
                request,
                f"Payment of MWK {amount:,.2f} applied successfully. [{tx.internal_reference}]"
            )
        else:
            tx.status = PaymentTransaction.STATUS_PROCESSING
            tx.save(update_fields=["provider_reference", "status", "raw_response"])
            if result.redirect_url:
                return redirect(result.redirect_url)
            messages.info(request, "Payment is being processed. Check back shortly.")
    else:
        tx.status = PaymentTransaction.STATUS_FAILED
        tx.save(update_fields=["provider_reference", "status", "raw_response"])
        messages.error(request, f"Payment failed: {result.message}")

    return redirect("portal_contract", contract_number=contract_number)


def portal_history(request, contract_number):
    """Payment history for a contract."""
    contract = get_object_or_404(PaymentContract, contract_number=contract_number)
    transactions = contract.transactions.order_by("-created_at")[:50]
    return render(request, "portal/history.html", {
        "contract": contract,
        "transactions": transactions,
    })


def portal_support(request):
    return render(request, "portal/support.html", {})
