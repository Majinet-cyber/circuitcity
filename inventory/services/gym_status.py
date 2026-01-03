"""
Gym member status service - determines if a member is active or overdue.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Dict, Optional

from django.utils import timezone

from inventory.models_verticals import GymMember, GymPayment


def get_member_status(member: GymMember, today: Optional[date] = None) -> Dict[str, any]:
    """
    Get member status: ACTIVE or OVERDUE.

    A member is ACTIVE if they have at least one GymPayment whose period covers today.
    Otherwise, they are OVERDUE.

    Args:
        member: GymMember instance
        today: Date to check status for (defaults to today in local timezone)

    Returns:
        dict with keys:
            - status: "ACTIVE" or "OVERDUE"
            - next_payment_date: date or None (end_date of current payment if active, or None if overdue)
            - reason: str explanation
    """
    if today is None:
        today = timezone.localdate()

    # Find the most recent active payment whose period includes today
    active_payment = (
        GymPayment.objects.filter(
            member=member,
            is_active=True,
            start_date__lte=today,
            end_date__gte=today,
        )
        .order_by("-paid_at")
        .first()
    )

    if active_payment:
        return {
            "status": "ACTIVE",
            "next_payment_date": active_payment.end_date,
            "reason": f"Active membership until {active_payment.end_date}",
        }
    else:
        # Member is overdue - find their most recent payment to see when it expired
        last_payment = GymPayment.objects.filter(member=member, is_active=True).order_by("-end_date").first()

        if last_payment:
            return {
                "status": "OVERDUE",
                "next_payment_date": None,
                "reason": f"Membership expired on {last_payment.end_date}",
            }
        else:
            return {
                "status": "OVERDUE",
                "next_payment_date": None,
                "reason": "No payments recorded",
            }
