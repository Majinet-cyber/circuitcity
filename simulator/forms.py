from django import forms
from .models import Scenario


class ScenarioForm(forms.ModelForm):
    """
    Form for creating and editing Scenarios.
    Uses sensible defaults and numeric validations.
    """

    class Meta:
        model = Scenario
        fields = [
            "name",
            "baseline_monthly_units",
            "avg_unit_price",
            "variable_cost_pct",
            "monthly_fixed_costs",
            "monthly_growth_pct",
            "months",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Scenario name"}),
            "baseline_monthly_units": forms.NumberInput(attrs={"class": "form-control", "step": "1", "min": "0"}),
            "avg_unit_price": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0"}),
            "variable_cost_pct": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0", "max": "100"}),
            "monthly_fixed_costs": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0"}),
            "monthly_growth_pct": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0"}),
            "months": forms.NumberInput(attrs={"class": "form-control", "step": "1", "min": "1", "max": "60"}),
        }
        labels = {
            "baseline_monthly_units": "Baseline units / month",
            "avg_unit_price": "Avg unit price (MWK)",
            "variable_cost_pct": "Variable cost % of price",
            "monthly_fixed_costs": "Fixed monthly costs (MWK)",
            "monthly_growth_pct": "Monthly demand growth %",
            "months": "Months to simulate",
        }
        help_texts = {
            "monthly_growth_pct": "Expected monthly growth rate in demand.",
        }

    def clean_variable_cost_pct(self):
        v = self.cleaned_data.get("variable_cost_pct")
        if v is None:
            return 0.0
        if v < 0 or v > 100:
            raise forms.ValidationError("Variable cost % must be between 0 and 100.")
        return v

    def clean_months(self):
        m = self.cleaned_data.get("months")
        if not m or m <= 0:
            raise forms.ValidationError("Months must be at least 1.")
        return m


