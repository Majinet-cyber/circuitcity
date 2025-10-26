from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from .models_savedview import SavedView
import json

@login_required
@require_http_methods(["GET","POST"])
def api_saved_views(request, scope):
    if request.method=="GET":
        qs = SavedView.objects.filter(scope=scope).filter(Q(owner=request.user)|Q(is_shared=True))
        return JsonResponse({"views":[{"id":v.id,"name":v.name,"query":v.query,"shared":v.is_shared} for v in qs]})
    data = json.loads(request.body or "{}")
    v = SavedView.objects.create(
        owner=request.user, scope=scope, name=data.get("name","Untitled"),
        query=data.get("query",{}), is_shared=bool(data.get("shared"))
    )
    return JsonResponse({"ok":True,"id":v.id})


