from django.http import JsonResponse
from django.utils import timezone

def inbox_json(request):
    """
    Lightweight, always-safe feed the header can consume.
    Return your real items here when ready.
    """
    limit = int(request.GET.get("limit", 50))

    # Example dummy items (replace with DB query later)
    now = timezone.localtime()
    sample = [
        {
            "type": "payment",  # dashboard-type
            "title": "Payment received",
            "body": "MK 120,000 from Walk-in customer",
            "url": "/wallet/",
            "created_human": now.strftime("%Y-%m-%d %H:%M"),
        },
        {
            "type": "stock_in",  # inventory-type
            "title": "Stock IN",
            "body": "Tecno Spark 40 · IMEI 35599… added to Store A",
            "url": "/inventory/list/",
            "created_human": now.strftime("%Y-%m-%d %H:%M"),
        },
        {
            "type": "stock_sold",
            "title": "Sold",
            "body": "Itel A50 sold by Agent Blessings (MK 95,000)",
            "url": "/inventory/scan-sold/",
            "created_human": now.strftime("%Y-%m-%d %H:%M"),
        },
        {
            "type": "low_stock",
            "title": "Low stock",
            "body": "Nokia 105 (Blue) — 3 units left in Store B",
            "url": "/inventory/list/?q=Nokia+105",
            "created_human": now.strftime("%Y-%m-%d %H:%M"),
        },
        {
            "type": "invoice",
            "title": "Invoice CC-1027",
            "body": "Overdue by 2 days (MK 340,000)",
            "url": "/reports/",
            "created_human": now.strftime("%Y-%m-%d %H:%M"),
        },
    ]
    return JsonResponse({"items": sample[:limit]})
