from django import forms

class ScenarioForm(forms.Form):
    name = forms.CharField(max_length=120)

    # Demand / pricing
    demand_growth_pct = forms.FloatField(initial=0)
    price_change_pct = forms.FloatField(initial=0)
    base_price = forms.FloatField(min_value=0, initial=100.0)
    unit_cost = forms.FloatField(min_value=0, initial=60.0)

    # Inventory
    lead_time_days = forms.IntegerField(min_value=0, initial=7)
    reorder_point = forms.IntegerField(min_value=0, initial=10)
    initial_stock = forms.IntegerField(min_value=0, initial=50)
    horizon_days = forms.IntegerField(min_value=1, max_value=365, initial=30)

    # P&L & cash flow
    op_ex_pct_of_revenue = forms.FloatField(min_value=0, initial=10.0, label="Opex % of revenue")
    tax_rate_pct = forms.FloatField(min_value=0, max_value=60, initial=25.0)
    ar_days = forms.IntegerField(min_value=0, initial=7, label="AR days")
    ap_days = forms.IntegerField(min_value=0, initial=7, label="AP days")
    opening_cash = forms.FloatField(initial=0.0)
