from django.http import JsonResponse
from .services import cfo_alerts, gamified_messages

def api_cfo_alerts(request):
    bid = request.user.active_business_id
    return JsonResponse({"alerts": cfo_alerts(bid)})

def api_gamify(request):
    bid = request.user.active_business_id
    return JsonResponse({"items": gamified_messages(bid)})


