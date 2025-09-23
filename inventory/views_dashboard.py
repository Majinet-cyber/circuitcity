# circuitcity/inventory/views_dashboard.py
from django.shortcuts import render
from django.http import HttpRequest, HttpResponse, JsonResponse


def inventory_dashboard(request: HttpRequest) -> HttpResponse:
    """
    Inventory dashboard view.

    - If Accept header asks for JSON → return a small JSON stub.
    - Otherwise render a template (inventory/dashboard.html).
    - Falls back to a plain HttpResponse if the template is missing.
    """
    if request.headers.get("accept", "").startswith("application/json"):
        return JsonResponse({"ok": True, "message": "Inventory dashboard ready"})

    try:
        return render(request, "inventory/dashboard.html")
    except Exception:
        return HttpResponse(
            "<h1>Inventory Dashboard</h1><p>Coming soon.</p>"
        )
