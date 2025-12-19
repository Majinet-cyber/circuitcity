# inventory/views_cement.py
"""
Views for Cement vertical.
Simple vertical: Costs, Stock In, Sell, Dashboard, Analytics only.
NO agents, wallets, or timelogs.
"""
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from core.verticals import require_vertical, get_vertical_context


@login_required
@require_vertical('cement')
def cement_dashboard(request):
    """Cement store dashboard - main entry point."""
    context = get_vertical_context(request)
    context.update({
        'page_title': 'Cement Dashboard',
    })
    return render(request, "verticals/cement/dashboard.html", context)


@login_required
@require_vertical('cement')
def cement_products(request):
    """List/manage cement products."""
    context = get_vertical_context(request)
    context.update({
        'page_title': 'Cement Products',
    })
    return render(request, "verticals/cement/products.html", context)


@login_required
@require_vertical('cement')
def cement_stock_in(request):
    """Record incoming cement stock."""
    context = get_vertical_context(request)
    context.update({
        'page_title': 'Stock In',
    })
    return render(request, "verticals/cement/stock_in.html", context)


@login_required
@require_vertical('cement')
def cement_sales(request):
    """Cement sales list."""
    context = get_vertical_context(request)
    context.update({
        'page_title': 'Sales',
    })
    return render(request, "verticals/cement/sales.html", context)


@login_required
@require_vertical('cement')
def cement_sell(request):
    """Record cement sale."""
    context = get_vertical_context(request)
    context.update({
        'page_title': 'Sell',
    })
    return render(request, "verticals/cement/sell.html", context)


@login_required
@require_vertical('cement')
def cement_costs(request):
    """Cement costs/expenses."""
    context = get_vertical_context(request)
    context.update({
        'page_title': 'Costs',
    })
    return render(request, "verticals/cement/costs.html", context)


@login_required
@require_vertical('cement')
def cement_reports(request):
    """Cement analytics/reports."""
    context = get_vertical_context(request)
    context.update({
        'page_title': 'Reports',
    })
    return render(request, "verticals/cement/analytics.html", context)


@login_required
@require_vertical('cement')
def cement_analytics(request):
    """Cement analytics - alias for reports."""
    return cement_reports(request)

