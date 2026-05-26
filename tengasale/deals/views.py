from django.shortcuts import render
from accounts.decorators import merchant_required
from .models import DeviceDeal


@merchant_required
def all_deals(request):
    deals = DeviceDeal.objects.filter(is_active=True, brand__is_active=True).select_related("brand").order_by(
        "brand__name",
        "model_name",
        "specs",
    )
    deal_options = [
        {
            "id": deal.id,
            "brand": deal.brand.name,
            "model_name": deal.model_name,
            "specs": deal.specs,
            "min_cash_price": str(deal.min_cash_price),
            "max_cash_price": str(deal.max_cash_price),
            "default_cash_price": str(deal.default_cash_price or deal.cash_price),
            "deposit_percent": str(deal.deposit_percent),
            "loan_multiplier": str(deal.loan_multiplier),
            "term_months": deal.term_months,
        }
        for deal in deals
    ]
    brand_names = ["TECNO", "itel", "Redmi"]
    for deal in deals:
        if deal.brand.name not in brand_names:
            brand_names.append(deal.brand.name)

    return render(
        request,
        "deals/all_deals.html",
        {
            "deals": deals,
            "deal_options": deal_options,
            "brand_names": brand_names,
        },
    )
