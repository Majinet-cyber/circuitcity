from decimal import Decimal

from django.db import transaction

from core.services import get_business_settings

from .models import Commission


TWOPLACES = Decimal("0.01")


def money(value):
    return Decimal(value or 0).quantize(TWOPLACES)


def get_sale_amount(application, settings=None):
    settings = settings or get_business_settings()
    sale_amount = application.calculated_total_loan or Decimal("0")
    if sale_amount <= 0 and application.selected_cash_price:
        multiplier = application.selected_loan_multiplier or settings.loan_multiplier
        sale_amount = application.selected_cash_price * multiplier
    return money(sale_amount)


def calculate_commission_amount(sale_amount, percent):
    return money((sale_amount * Decimal(percent or 0)) / Decimal("100"))


@transaction.atomic
def process_application_approval(application, approved_by):
    settings = get_business_settings()
    sale_amount = get_sale_amount(application, settings)
    if sale_amount <= 0:
        return {
            "sale_amount": sale_amount,
            "merchant_commission": None,
            "manager_commission": None,
            "spin_granted": False,
        }

    manager_commission = None
    if approved_by:
        manager_amount = calculate_commission_amount(sale_amount, settings.manager_commission_percent)
        manager_commission, _ = Commission.objects.get_or_create(
            application=application,
            user=approved_by,
            role=Commission.ROLE_MANAGER,
            defaults={
                "commission_percent": settings.manager_commission_percent,
                "sale_amount": sale_amount,
                "amount": manager_amount,
                "status": Commission.STATUS_PENDING,
            },
        )

    return {
        "sale_amount": sale_amount,
        "merchant_commission": None,
        "manager_commission": manager_commission,
        "spin_granted": False,
    }


@transaction.atomic
def process_contract_completion(application):
    settings = get_business_settings()
    sale_amount = get_sale_amount(application, settings)
    if sale_amount <= 0:
        return {"sale_amount": sale_amount, "merchant_commission": None, "spin_granted": False}

    merchant_amount = calculate_commission_amount(sale_amount, settings.merchant_commission_percent)
    merchant_commission, _ = Commission.objects.get_or_create(
        application=application,
        user=application.created_by,
        role=Commission.ROLE_MERCHANT,
        defaults={
            "commission_percent": settings.merchant_commission_percent,
            "sale_amount": sale_amount,
            "amount": merchant_amount,
            "status": Commission.STATUS_PENDING,
        },
    )

    spin_granted = False
    if settings.spin_enabled:
        from rewards.services import award_spin_for_application

        spin_granted = award_spin_for_application(application, application.created_by)

    return {
        "sale_amount": sale_amount,
        "merchant_commission": merchant_commission,
        "spin_granted": spin_granted,
    }


def cancel_application_commissions(application):
    Commission.objects.filter(application=application).exclude(status=Commission.STATUS_PAID).update(
        status=Commission.STATUS_CANCELLED
    )
