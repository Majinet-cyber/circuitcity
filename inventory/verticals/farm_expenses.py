# inventory/verticals/farm_expenses.py
"""
Farm Expenses view with gamified category cards and Malawi-specific quick-picks.
"""
from __future__ import annotations

from decimal import Decimal
from io import StringIO
import csv

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from inventory.authz import require_business_kind
from inventory.business_kinds import BusinessKind
from inventory.models_farm import (
    FarmLedgerEntry,
    FarmEntryType,
    FarmExpenseCategory,
    FarmUnit,
    FarmPaymentMethod,
)
from tenants.utils import require_business
from inventory.verticals import base


@login_required
@require_business
@require_business_kind(BusinessKind.FARM)
def expenses_landing(request: HttpRequest) -> HttpResponse:
    """
    Farm Expenses landing page with category cards.
    """
    ctx = base.base_context(request)
    business = ctx.get("business")
    
    from inventory.services.farm_filters import parse_farm_filters, get_available_filter_options
    filter_state = parse_farm_filters(request, business)
    filter_options = get_available_filter_options(business)
    
    ctx.update({
        "active_tab": "expenses",
        "hero_title": "Farm Expenses",
        "hero_blurb": "Track and categorize your farm costs",
        "filter_state": filter_state,
        "filter_options": filter_options,
        "expense_categories": FarmExpenseCategory.choices,
    })
    
    return render(request, "verticals/farm/expenses_landing.html", ctx)


@login_required
@require_business
@require_business_kind(BusinessKind.FARM)
@require_http_methods(["GET", "POST"])
def expenses_record(request: HttpRequest) -> HttpResponse:
    """Record a new farm expense."""
    ctx = base.base_context(request)
    business = ctx.get("business")
    
    if request.method == "POST":
        try:
            amount = Decimal(request.POST.get("amount", "0"))
            entry = FarmLedgerEntry.objects.create(
                business=business,
                date=request.POST.get("date") or timezone.now().date(),
                entry_type=FarmEntryType.EXPENSE,
                enterprise_type=request.POST.get("enterprise_type", "general"),
                category=request.POST.get("category", "other"),
                description=request.POST.get("description", ""),
                amount_mwk=amount,
                quantity=request.POST.get("quantity") or None,
                unit=request.POST.get("unit", "item"),
                payment_method=request.POST.get("payment_method", "cash"),
                notes=request.POST.get("notes", ""),
                created_by=request.user,
            )
            messages.success(request, f"Expense of MWK {amount:,.2f} recorded successfully.")
            return redirect("verticals:farm_expenses")
        except Exception as e:
            messages.error(request, f"Error recording expense: {e}")
    
    ctx.update({
        "active_tab": "expenses",
        "hero_title": "Record Expense",
        "expense_categories": FarmExpenseCategory.choices,
        "payment_methods": FarmPaymentMethod.choices,
        "units": FarmUnit.choices,
    })
    
    return render(request, "verticals/farm/expenses_record.html", ctx)


@login_required
@require_business
@require_business_kind(BusinessKind.FARM)
def expenses_export(request: HttpRequest) -> HttpResponse:
    """Export expenses as CSV."""
    ctx = base.base_context(request)
    business = ctx.get("business")
    
    from inventory.services.farm_filters import parse_farm_filters, apply_filters_to_ledger
    filter_state = parse_farm_filters(request, business)
    
    # Get filtered expenses
    expenses = FarmLedgerEntry.objects.filter(
        business=business,
        entry_type=FarmEntryType.EXPENSE,
    )
    expenses = apply_filters_to_ledger(expenses, filter_state)
    expenses = expenses.order_by("-date")
    
    # Create CSV
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["Date", "Category", "Description", "Amount (MWK)", "Notes"])
    
    for expense in expenses:
        writer.writerow([
            expense.date.isoformat(),
            expense.get_category_display() if hasattr(expense, 'get_category_display') else expense.category,
            expense.description,
            expense.amount_mwk,
            expense.notes,
        ])
    
    response = HttpResponse(output.getvalue(), content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="farm_expenses_{filter_state.range_label}.csv"'
    return response
