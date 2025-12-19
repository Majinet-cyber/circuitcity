# inventory/views_hardware.py
"""
Views for Hardware Store vertical.
Simple vertical: Costs, Stock In, Sell, Dashboard, Analytics only.
NO agents, wallets, or timelogs.
"""
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from core.verticals import require_vertical, get_vertical_context


@login_required
@require_vertical('hardware')
def hardware_dashboard(request):
    """Hardware store dashboard - main entry point."""
    context = get_vertical_context(request)
    context.update({
        'page_title': 'Hardware Dashboard',
    })
    return render(request, "verticals/hardware/dashboard.html", context)


@login_required
@require_vertical('hardware')
def hardware_products(request):
    """List/manage hardware products."""
    context = get_vertical_context(request)
    context.update({
        'page_title': 'Hardware Products',
    })
    return render(request, "verticals/hardware/products.html", context)


@login_required
@require_vertical('hardware')
def hardware_stock_in(request):
    """Record incoming hardware stock."""
    context = get_vertical_context(request)
    context.update({
        'page_title': 'Stock In',
    })
    return render(request, "verticals/hardware/stock_in.html", context)


@login_required
@require_vertical('hardware')
def hardware_sales(request):
    """Hardware sales list."""
    context = get_vertical_context(request)
    context.update({
        'page_title': 'Sales',
    })
    return render(request, "verticals/hardware/sales.html", context)


@login_required
@require_vertical('hardware')
def hardware_sell(request):
    """Record hardware sale."""
    context = get_vertical_context(request)
    context.update({
        'page_title': 'Sell',
    })
    return render(request, "verticals/hardware/sell.html", context)


@login_required
@require_vertical('hardware')
def hardware_costs(request):
    """Hardware costs/expenses."""
    context = get_vertical_context(request)
    context.update({
        'page_title': 'Costs',
    })
    return render(request, "verticals/hardware/costs.html", context)


@login_required
@require_vertical('hardware')
def hardware_reports(request):
    """Hardware analytics/reports."""
    context = get_vertical_context(request)
    context.update({
        'page_title': 'Reports',
    })
    return render(request, "verticals/hardware/analytics.html", context)


@login_required
@require_vertical('hardware')
def hardware_analytics(request):
    """Hardware analytics - alias for reports."""
    return hardware_reports(request)

