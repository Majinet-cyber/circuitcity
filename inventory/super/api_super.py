# inventory/api_super.py (new module)
from django.http import JsonResponse
from django.contrib.auth.decorators import user_passes_test
from django.db.models import Sum, F, Q

@user_passes_test(lambda u: u.is_superuser)
def rebalancing_suggestions(_req):
    # Pseudologic: find SKUs with deficit in X tenants and surplus in Y tenants
    # Return ranked moves with impact score
    data = [
      {"sku":"iPhone 11 64GB", "from":"Air Easy", "to":"City Hub", "qty":12, "impact":"stockoutâ†“ 5 days"},
      {"sku":"Tecno Pova",     "from":"West 2",   "to":"East 1",   "qty":8,  "impact":"fill rateâ†‘ 12%"},
    ]
    return JsonResponse({"items": data})

@user_passes_test(lambda u: u.is_superuser)
def deadstock_catalog(_req):
    # Return aging > 90d list to seed Exchange
    data = []
    return JsonResponse({"items": data})


