# sales/views_export.py
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.db.models import F
from django.shortcuts import render
from core.csvutils import stream_csv
from .utils import sales_qs_for_user

@login_required
def export_sales_csv(request):
    qs = sales_qs_for_user(request.user)

    # reuse existing filters from request.GET (example: date_from/date_to/location/product/agent)
    df = request.GET.get("date_from")
    dt = request.GET.get("date_to")
    if df: qs = qs.filter(created_at__date__gte=df)
    if dt: qs = qs.filter(created_at__date__lte=dt)
    loc = request.GET.get("location")
    if loc: qs = qs.filter(location__id=loc)
    prod = request.GET.get("product")
    if prod: qs = qs.filter(product__id=prod)
    agent = request.GET.get("agent")
    if agent: qs = qs.filter(user__id=agent)

    header = ["id","created_at","product","imei/serial","qty","unit_price","total","agent","location"]
    def rows():
        yield header
        for s in qs.select_related("product","location","user").iterator():
            yield [
                s.id,
                s.created_at.isoformat(),
                getattr(s.product, "name", ""),
                getattr(s, "serial_or_imei", ""),
                getattr(s, "quantity", 1),
                getattr(s, "unit_price", ""),
                getattr(s, "total_price", ""),
                getattr(s.user, "username", ""),
                getattr(s.location, "name", ""),
            ]
    return stream_csv(rows(), "sales.csv")
