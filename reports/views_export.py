from __future__ import annotations
import csv
from datetime import timedelta
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import HttpResponse
from django.db.models import Sum, Count
from django.db.models.functions import Coalesce

from .views import ReportFilters, _is_staff_or_auditor
from sales.models import Sale
from inventory.models import InventoryItem

def _apply_filters(qs, f: ReportFilters):
    from .views_api import _apply_filters as _af
    return _af(qs, f)

def _csv_response(filename: str):
    resp = HttpResponse(content_type="text/csv")
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp

@login_required
@user_passes_test(_is_staff_or_auditor)
def export_sales_csv(request):
    f = ReportFilters.from_request(request)
    qs = _apply_filters(Sale.objects.select_related("agent"), f).order_by("-created_at")

    resp = _csv_response("sales_report.csv")
    w = csv.writer(resp)
    w.writerow(["Date","Agent","Model","Channel","Amount_MWK","Profit_MWK","Ad_Source"])
    for s in qs:
        w.writerow([s.created_at.date(), getattr(s.agent,"name",None), s.model, s.channel, s.amount, s.profit, getattr(s,"ad_source", "")])
    return resp

@login_required
@user_passes_test(_is_staff_or_auditor)
def export_expenses_csv(request):
    # If you have an Expense model, replace with real fields. Placeholder columns:
    resp = _csv_response("monthly_expenses.csv")
    w = csv.writer(resp)
    w.writerow(["Month","Category","Amount_MWK","Notes"])
    # TODO: plug in real Expense aggregations
    return resp

@login_required
@user_passes_test(_is_staff_or_auditor)
def export_inventory_csv(request):
    # Sold vs time vs model vs agent
    f = ReportFilters.from_request(request)
    sales = _apply_filters(Sale.objects.all(), f)
    by_model = (sales.values("model")
        .annotate(sold=Count("id"), revenue=Coalesce(Sum("amount"),0), profit=Coalesce(Sum("profit"),0))
        .order_by("-sold"))

    resp = _csv_response("inventory_sold_by_model.csv")
    w = csv.writer(resp)
    w.writerow(["Model","Units_Sold","Revenue_MWK","Profit_MWK"])
    for r in by_model:
        w.writerow([r["model"], r["sold"], r["revenue"], r["profit"]])
    return resp

@login_required
@user_passes_test(_is_staff_or_auditor)
def export_management_report_csv(request):
    # A compact management snapshot (KPI pack)
    f = ReportFilters.from_request(request)
    base = _apply_filters(Sale.objects.all(), f)
    kpis = base.aggregate(amount=Coalesce(Sum("amount"),0), profit=Coalesce(Sum("profit"),0), orders=Count("id"))

    resp = _csv_response("management_snapshot.csv")
    w = csv.writer(resp)
    w.writerow(["Metric","Value"])
    for k,v in kpis.items(): w.writerow([k, v])
    return resp
