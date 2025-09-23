# circuitcity/tenants/views_hq.py
from django.shortcuts import render
from django.http import HttpRequest, HttpResponse


def home(request: HttpRequest) -> HttpResponse:
    """
    HQ landing page.
    """
    try:
        return render(request, "tenants/hq_home.html")
    except Exception:
        return HttpResponse("<h1>HQ Home</h1><p>Coming soon.</p>")


def agents_list(request: HttpRequest) -> HttpResponse:
    """
    HQ → Agents management page.
    """
    try:
        return render(request, "tenants/agents_list.html")
    except Exception:
        return HttpResponse("<h1>HQ Agents</h1><p>Coming soon.</p>")


def stock_trends(request: HttpRequest) -> HttpResponse:
    """
    HQ → Stock trends / analytics page.
    """
    try:
        return render(request, "tenants/stock_trends.html")
    except Exception:
        return HttpResponse("<h1>HQ Stock Trends</h1><p>Coming soon.</p>")
