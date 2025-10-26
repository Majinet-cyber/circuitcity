from django.http import JsonResponse
from django.contrib.postgres.search import TrigramSimilarity
from inventory.models import SKU
from accounts.models import Agent

def api_global_search(request):
    q = (request.GET.get("q") or "").strip()
    if not q:
        return JsonResponse({"skus": [], "agents": []})
    skus = list(
        SKU.objects.annotate(sim=TrigramSimilarity("name", q))
        .filter(sim__gt=0.2)
        .order_by("-sim")
        .values("id","name","code")[:8]
    )
    agents = list(
        Agent.objects.annotate(sim=TrigramSimilarity("full_name", q))
        .filter(sim__gt=0.2)
        .order_by("-sim")
        .values("id","full_name")[:6]
    )
    return JsonResponse({"skus": skus, "agents": agents})


