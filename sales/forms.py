# sales/forms.py
"""
Forms for commission configuration and settings.
"""
from decimal import Decimal
from django import forms
from django.core.validators import MinValueValidator, MaxValueValidator

from .models import CommissionConfig


class CommissionSettingsForm(forms.ModelForm):
    """
    Form for manager to configure commission settings.
    Allows either percentage-based OR fixed amount per sale.
    """
    commission_mode = forms.ChoiceField(
        choices=[
            ("percentage", "Percentage of sale price"),
            ("fixed", "Fixed amount per sale"),
        ],
        widget=forms.RadioSelect,
        initial="percentage",
        label="Commission type",
    )
    
    base_commission_pct = forms.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        required=False,
        label="Commission percentage",
        help_text="e.g., 12.00 for 12%",
        widget=forms.NumberInput(attrs={
            "placeholder": "12.00",
            "step": "0.01",
            "min": "0",
            "max": "100",
        }),
    )
    
    fixed_commission_amount = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        required=False,
        label="Fixed commission amount",
        help_text="e.g., 5000 for a flat MWK 5,000 per sale",
        widget=forms.NumberInput(attrs={
            "placeholder": "5000.00",
            "step": "0.01",
            "min": "0",
        }),
    )
    
    class Meta:
        model = CommissionConfig
        fields = [
            "base_commission_pct",
            "fixed_commission_amount",
            "early_bonus_enabled",
            "early_bonus_per_30min",
            "lateness_penalties_enabled",
            "late_penalty_per_30min",
        ]
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Pre-populate commission_mode based on existing config
        if self.instance and self.instance.pk:
            if self.instance.fixed_commission_amount:
                self.initial["commission_mode"] = "fixed"
            else:
                self.initial["commission_mode"] = "percentage"
    
    def clean(self):
        cleaned_data = super().clean()
        mode = cleaned_data.get("commission_mode")
        pct = cleaned_data.get("base_commission_pct")
        fixed = cleaned_data.get("fixed_commission_amount")
        
        if mode == "percentage":
            # Ensure percentage is provided
            if pct is None or pct == 0:
                self.add_error("base_commission_pct", "Enter a commission percentage greater than 0.")
            # Clear fixed amount if percentage mode
            cleaned_data["fixed_commission_amount"] = None
        
        elif mode == "fixed":
            # Ensure fixed amount is provided
            if fixed is None or fixed == 0:
                self.add_error("fixed_commission_amount", "Enter a fixed commission amount greater than 0.")
            # Clear percentage if fixed mode
            # Keep a nominal percentage for backwards compatibility
            cleaned_data["base_commission_pct"] = Decimal("0.00")
        
        return cleaned_data

