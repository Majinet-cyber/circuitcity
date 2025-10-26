from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from .utils import scope_qs_to_user

@login_required
def api_company_spend(request):
    qs = scope_qs_to_user(WalletEntry.objects.all(), request)
    total = qs.aggregate(total=Coalesce(Sum("amount"), 0))["total"]
    return JsonResponse({"total": float(total)})

@login_required
def api_company_ledger(request):
    qs = scope_qs_to_user(LedgerEntry.objects.select_related("store","user"), request).order_by("-created_at")
    data = [
        {
            "id": obj.id,
            "when": obj.created_at.isoformat(),
            "type": obj.kind,
            "store": getattr(obj.store, "name", None),
            "user": getattr(obj.user, "username", None),
            "amount": float(obj.amount),
        }
        for obj in qs[:50]
    ]
    return JsonResponse({"results": data})


