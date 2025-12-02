# wallet/forms.py
from __future__ import annotations
from decimal import Decimal
from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import TxnType, WalletTransaction, RecurrenceType

User = get_user_model()


class AdminCostForm(forms.ModelForm):
    """
    Form for admins/managers to add or edit cost transactions (once-off or recurring).
    """
    class Meta:
        model = WalletTransaction
        fields = [
            'type',
            'amount',
            'note',
            'effective_date',
            'is_recurring',
            'recurrence',
            'effective_from',
        ]
        widgets = {
            'effective_date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'effective_from': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'note': forms.Textarea(attrs={'rows': 3, 'class': 'form-control', 'placeholder': 'e.g., Rent for office space'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0.01'}),
            'type': forms.Select(attrs={'class': 'form-select'}),
            'recurrence': forms.Select(attrs={'class': 'form-select'}),
        }
        help_texts = {
            'amount': 'Cost amount (positive number, will be stored as expense)',
            'is_recurring': 'Check if this cost repeats monthly',
            'effective_from': 'Start date for recurring costs (leave blank for one-time costs)',
        }
    
    def __init__(self, *args, **kwargs):
        self.business = kwargs.pop('business', None)
        super().__init__(*args, **kwargs)
        
        # Limit transaction types to cost types only
        self.fields['type'].choices = [
            (TxnType.COST_ONCE_OFF, 'One-time Cost'),
            (TxnType.COST_RECURRING, 'Recurring Cost'),
        ]
        self.fields['type'].initial = TxnType.COST_ONCE_OFF
        
        # Make recurrence and effective_from optional (they'll be required conditionally)
        self.fields['recurrence'].required = False
        self.fields['effective_from'].required = False
    
    def clean_amount(self):
        """Ensure amount is positive."""
        amount = self.cleaned_data.get('amount')
        if amount is not None and amount <= Decimal('0.00'):
            raise ValidationError('Cost amount must be greater than zero.')
        return amount
    
    def clean(self):
        cleaned = super().clean()
        is_recurring = cleaned.get('is_recurring', False)
        effective_from = cleaned.get('effective_from')
        
        # For recurring costs, effective_from is required
        if is_recurring and not effective_from:
            self.add_error('effective_from', 'Start date is required for recurring costs.')
        
        # Auto-set type based on is_recurring
        if is_recurring:
            cleaned['type'] = TxnType.COST_RECURRING
        else:
            cleaned['type'] = TxnType.COST_ONCE_OFF
        
        return cleaned


class AgentWalletAdjustmentForm(forms.Form):
    """
    Form for admins/managers to manually adjust an agent's wallet balance.
    Can add money (credit) or deduct money (debit) with a required reason.
    """
    membership = forms.IntegerField(
        widget=forms.HiddenInput(),
        help_text="Agent membership ID"
    )
    amount = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0.01"),
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'step': '0.01',
            'min': '0.01',
            'placeholder': '0.00'
        }),
        help_text="Amount to add or deduct (positive number)"
    )
    is_deduction = forms.BooleanField(
        required=False,
        initial=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        help_text="Check to deduct (debit), leave unchecked to add (credit)"
    )
    reason = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Explain why this adjustment is needed...'
        }),
        help_text="Required: Reason for this manual adjustment (for audit trail)",
        min_length=10,
        max_length=500,
    )
    
    def clean_amount(self):
        """Ensure amount is positive."""
        amount = self.cleaned_data.get('amount')
        if amount is not None and amount <= Decimal('0.00'):
            raise ValidationError('Amount must be greater than zero.')
        return amount
    
    def clean_reason(self):
        """Ensure reason is meaningful."""
        reason = self.cleaned_data.get('reason', '').strip()
        if not reason:
            raise ValidationError('Reason is required for manual adjustments.')
        if len(reason) < 10:
            raise ValidationError('Reason must be at least 10 characters.')
        return reason
    
    def clean(self):
        """Validate the adjustment."""
        cleaned = super().clean()
        is_deduction = cleaned.get('is_deduction', False)
        amount = cleaned.get('amount')
        
        # If it's a deduction, check if agent has sufficient balance
        if is_deduction and amount:
            membership_id = cleaned.get('membership')
            if membership_id:
                try:
                    from tenants.models import Membership
                    from wallet.agent_models import get_or_create_agent_wallet
                    
                    membership = Membership.objects.get(pk=membership_id)
                    wallet = get_or_create_agent_wallet(membership)
                    
                    if wallet.balance < amount:
                        raise ValidationError(
                            f'Insufficient balance for deduction. '
                            f'Current balance: MK {wallet.balance}, '
                            f'Requested deduction: MK {amount}'
                        )
                except Membership.DoesNotExist:
                    raise ValidationError('Invalid membership.')
                except Exception as e:
                    raise ValidationError(f'Error validating balance: {e}')
        
        return cleaned
    
    def save(self, commit=True):
        instance = super().save(commit=False)
        
        # Set business if provided
        if self.business:
            instance.business = self.business
        
        # Costs are stored as negative amounts (expenses)
        if instance.amount > Decimal('0.00'):
            instance.amount = -instance.amount
        
        # Force COMPANY ledger for cost transactions
        instance.ledger = 'company'
        
        if commit:
            instance.save()
        return instance


class IssuePayslipForm(forms.Form):
    users = forms.ModelMultipleChoiceField(
        queryset=User.objects.filter(is_active=True).order_by("username"),
        widget=forms.SelectMultiple(attrs={"size": 12, "class": "form-select"})
    )
    period_start = forms.DateField(widget=forms.DateInput(attrs={"type":"date"}))
    period_end   = forms.DateField(widget=forms.DateInput(attrs={"type":"date"}))
    send_now     = forms.BooleanField(initial=True, required=False)

    # Optional quick scheduler
    schedule_monthly = forms.BooleanField(initial=False, required=False)
    schedule_day     = forms.IntegerField(min_value=1, max_value=31, initial=28, required=False)
    schedule_hour    = forms.IntegerField(min_value=0, max_value=23, initial=9, required=False)

    def clean(self):
        c = super().clean()
        if c.get("period_end") and c.get("period_start") and c["period_end"] < c["period_start"]:
            self.add_error("period_end", "End date must be after start date.")
        if c.get("schedule_monthly"):
            if not c.get("schedule_day") and not c.get("schedule_hour"):
                self.add_error("schedule_day", "Choose a day and hour for monthly auto-send.")
        return c

    @classmethod
    def initial_previous_month(cls):
        today = timezone.localdate()
        first_this = today.replace(day=1)
        last_prev = first_this - timezone.timedelta(days=1)
        start_prev = last_prev.replace(day=1)
        return {"period_start": start_prev, "period_end": last_prev}


