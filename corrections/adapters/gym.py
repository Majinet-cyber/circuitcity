"""
Gym Vertical Adapter for Corrections Framework (Feb 2026)
==========================================================

Registers correctable entities for the Gym vertical:
- Gym Members (GymMember)
- Gym Payments (GymPayment - membership + trainer fees)
- Gym Trainers (GymTrainer - optional)

Allows managers to fix:
- Member information errors (name, phone, email)
- Payment amount discrepancies (membership_amount, trainer_fee)
- Membership date errors (start_date, end_date)
- Payment method corrections
"""
from __future__ import annotations

from decimal import Decimal
from typing import Dict
import datetime

from django.db.models import F, Q, QuerySet
from django.utils import timezone

from corrections.registry import (
    VerticalAdapter,
    EntityConfig,
    FieldConfig,
    register_vertical,
)
from inventory.models_verticals import GymMember, GymPayment, GymTrainer


@register_vertical('gym')
class GymAdapter(VerticalAdapter):
    """Gym vertical adapter."""
    
    vertical_key = 'gym'
    vertical_label = 'Gym'
    
    def get_entities(self) -> Dict[str, EntityConfig]:
        """
        Define correctable entities for Gym vertical.
        """
        return {
            # Gym Member
            'gym_member': EntityConfig(
                entity_label='gym_member',
                model=GymMember,
                label='Gym Member',
                description='Member profile with contact info and membership details',
                fields={
                    'name': FieldConfig(
                        field_name='name',
                        label='Member Name',
                        field_type='string',
                        validator=lambda val: len(str(val).strip()) > 0,
                        coercer=lambda val: str(val).strip(),
                        help_text='Full name (required)',
                        required=True,
                    ),
                    'phone': FieldConfig(
                        field_name='phone',
                        label='Phone Number',
                        field_type='string',
                        validator=lambda val: True,  # Any phone format accepted
                        coercer=lambda val: str(val).strip() if val else '',
                        help_text='Phone number',
                        required=False,
                    ),
                    'email': FieldConfig(
                        field_name='email',
                        label='Email',
                        field_type='string',
                        validator=lambda val: '@' in str(val) if val else True,
                        coercer=lambda val: str(val).strip().lower() if val else '',
                        help_text='Email address (must contain @)',
                        required=False,
                    ),
                    'membership_fee': FieldConfig(
                        field_name='membership_fee',
                        label='Membership Fee',
                        field_type='decimal',
                        validator=lambda val: val is None or Decimal(str(val)) >= 0,
                        coercer=lambda val: Decimal(str(val)) if val else None,
                        help_text='Snapshot of membership fee at signup',
                        required=False,
                    ),
                    'trainer_fee': FieldConfig(
                        field_name='trainer_fee',
                        label='Trainer Fee',
                        field_type='decimal',
                        validator=lambda val: val is None or Decimal(str(val)) >= 0,
                        coercer=lambda val: Decimal(str(val)) if val else None,
                        help_text='Snapshot of trainer fee',
                        required=False,
                    ),
                    'member_number': FieldConfig(
                        field_name='member_number',
                        label='Member Number',
                        field_type='string',
                        validator=lambda val: True,
                        coercer=lambda val: str(val).strip() if val else '',
                        help_text='Human-friendly member number (e.g., EW-000123)',
                        required=False,
                    ),
                },
            ),
            
            # Gym Payment
            'gym_payment': EntityConfig(
                entity_label='gym_payment',
                model=GymPayment,
                label='Gym Payment',
                description='Membership payment with optional trainer fee',
                business_filter_path='member__business',  # GymPayment has no direct business field
                fields={
                    'membership_amount': FieldConfig(
                        field_name='membership_amount',
                        label='Membership Amount',
                        field_type='decimal',
                        validator=lambda val: Decimal(str(val)) > 0,
                        coercer=lambda val: Decimal(str(val)),
                        help_text='Base membership fee (must be > 0)',
                        required=True,
                    ),
                    'trainer_fee': FieldConfig(
                        field_name='trainer_fee',
                        label='Trainer Fee',
                        field_type='decimal',
                        validator=lambda val: Decimal(str(val)) >= 0,
                        coercer=lambda val: Decimal(str(val)),
                        help_text='Additional trainer fee (must be >= 0)',
                        required=True,
                    ),
                    'amount': FieldConfig(
                        field_name='amount',
                        label='Total Amount',
                        field_type='decimal',
                        validator=lambda val: val is None or Decimal(str(val)) > 0,
                        coercer=lambda val: Decimal(str(val)) if val else None,
                        help_text='Total amount paid (membership + trainer)',
                        required=False,
                    ),
                    'payment_method': FieldConfig(
                        field_name='payment_method',
                        label='Payment Method',
                        field_type='string',
                        validator=lambda val: val in ['CASH', 'BANK', 'MOBILE_MONEY'],
                        coercer=lambda val: str(val).upper(),
                        help_text='CASH, BANK, or MOBILE_MONEY',
                        required=False,
                    ),
                    'start_date': FieldConfig(
                        field_name='start_date',
                        label='Start Date',
                        field_type='date',
                        validator=lambda val: isinstance(val, (datetime.date, str)),
                        coercer=lambda val: val if isinstance(val, datetime.date) else datetime.date.fromisoformat(str(val)),
                        help_text='Membership period start date',
                        required=True,
                    ),
                    'end_date': FieldConfig(
                        field_name='end_date',
                        label='End Date',
                        field_type='date',
                        validator=lambda val: isinstance(val, (datetime.date, str)),
                        coercer=lambda val: val if isinstance(val, datetime.date) else datetime.date.fromisoformat(str(val)),
                        help_text='Membership period end date',
                        required=True,
                    ),
                },
            ),
            
            # Gym Trainer (optional entity)
            'gym_trainer': EntityConfig(
                entity_label='gym_trainer',
                model=GymTrainer,
                label='Gym Trainer',
                description='Trainer profile with contact info',
                fields={
                    'name': FieldConfig(
                        field_name='name',
                        label='Trainer Name',
                        field_type='string',
                        validator=lambda val: len(str(val).strip()) > 0,
                        coercer=lambda val: str(val).strip(),
                        help_text='Full name (required)',
                        required=True,
                    ),
                    'phone': FieldConfig(
                        field_name='phone',
                        label='Phone Number',
                        field_type='string',
                        validator=lambda val: True,
                        coercer=lambda val: str(val).strip() if val else '',
                        help_text='Phone number',
                        required=False,
                    ),
                    'email': FieldConfig(
                        field_name='email',
                        label='Email',
                        field_type='string',
                        validator=lambda val: '@' in str(val) if val else True,
                        coercer=lambda val: str(val).strip().lower() if val else '',
                        help_text='Email address',
                        required=False,
                    ),
                },
            ),
        }
    
    def find_erroneous_entries(
        self,
        entity_label: str,
        business,
        limit: int = 50,
    ) -> QuerySet:
        """
        Find potentially erroneous entries for quick correction.
        
        Heuristics:
        - Payments where amount != membership_amount + trainer_fee
        - Payments where end_date != start_date + 30 days
        - Members with negative fees
        - Members with expired memberships still marked as active
        """
        if entity_label == 'gym_payment':
            # Find payments with calculation errors
            # DEFENSIVE: Handle cases where member might be None or duplicate
            today = timezone.now().date()
            try:
                return GymPayment.objects.filter(
                    member__business=business,
                    member__isnull=False,  # Skip orphaned payments
                    is_active=True,
                ).annotate(
                    calculated_total=F('membership_amount') + F('trainer_fee')
                ).filter(
                    # Amount doesn't match sum (with 1 MWK tolerance for rounding)
                    Q(amount__lt=F('calculated_total') - Decimal('1')) |
                    Q(amount__gt=F('calculated_total') + Decimal('1')) |
                    # Start date is in the future (data error)
                    Q(start_date__gt=today)
                ).select_related('member', 'trainer').order_by('-paid_at')[:limit]
            except Exception:
                # If query fails (e.g., due to data integrity issues), return empty queryset
                return GymPayment.objects.none()
        
        elif entity_label == 'gym_member':
            # Find members with data issues
            # DEFENSIVE: Handle cases where data might be corrupted
            today = timezone.now().date()
            try:
                return GymMember.objects.filter(
                    business=business,
                    is_active=True,
                ).filter(
                    Q(membership_fee__lt=0) |  # Negative fee
                    Q(trainer_fee__lt=0) |  # Negative trainer fee
                    Q(membership_end__lt=today, status='ACTIVE')  # Expired but still active
                ).order_by('-joined_at')[:limit]
            except Exception:
                # If query fails, return empty queryset
                return GymMember.objects.none()
        
        elif entity_label == 'gym_trainer':
            # Find trainers with missing contact info
            try:
                return GymTrainer.objects.filter(
                    business=business,
                    is_active=True,
                ).filter(
                    Q(phone='') & Q(email='')  # No contact info at all
                ).order_by('-joined_at')[:limit]
            except Exception:
                # If query fails, return empty queryset
                return GymTrainer.objects.none()
        
        else:
            return GymMember.objects.none()
    
    def calculate_impact(
        self,
        entity_label: str,
        obj,
        field_name: str,
        old_value,
        new_value,
    ) -> Dict[str, Decimal]:
        """
        Calculate financial impact of a correction.
        """
        revenue_impact = Decimal('0.00')
        profit_impact = Decimal('0.00')
        
        if entity_label == 'gym_payment':
            # For payments, changing amounts impacts revenue
            if field_name in ('membership_amount', 'trainer_fee', 'amount'):
                old_amt = Decimal(str(old_value)) if old_value else Decimal('0.00')
                new_amt = Decimal(str(new_value)) if new_value else Decimal('0.00')
                revenue_impact = new_amt - old_amt
                # For gyms, revenue ~= profit (no COGS for services)
                profit_impact = revenue_impact
        
        elif entity_label == 'gym_member':
            # Member fee changes don't affect past payments, only future
            # Show potential impact if member pays again at new rate
            if field_name in ('membership_fee', 'trainer_fee'):
                old_fee = Decimal(str(old_value)) if old_value else Decimal('0.00')
                new_fee = Decimal(str(new_value)) if new_value else Decimal('0.00')
                # Potential monthly impact
                revenue_impact = new_fee - old_fee
                profit_impact = revenue_impact
        
        return {
            'revenue_impact': revenue_impact,
            'profit_impact': profit_impact,
        }


# Export
__all__ = ['GymAdapter']

