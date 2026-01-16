# inventory/verticals/farm_reports.py
"""
Farm Reports generation endpoints.
Implements real CSV export for Profit & Loss, Livestock, and Crop Season reports.
"""
from __future__ import annotations

import csv
from datetime import date, timedelta
from decimal import Decimal
from io import StringIO

from django.contrib.auth.decorators import login_required
from django.db.models import Count, Sum
from django.db.models.functions import Coalesce
from django.http import HttpRequest, HttpResponse
from django.utils import timezone

from inventory.authz import require_business_kind
from inventory.business_kinds import BusinessKind
from inventory.models_farm import (
    FarmCropSeason,
    FarmEntryType,
    FarmLedgerEntry,
    FarmLivestockBatch,
    FarmLivestockEvent,
    FarmSeasonStatus,
)
from tenants.utils import require_business


@login_required
@require_business
@require_business_kind(BusinessKind.FARM)
def profit_loss_report(request: HttpRequest) -> HttpResponse:
    """
    Generate Profit & Loss report as CSV.
    Monthly summary of income vs expenses.
    """
    from django.db import models
    
    business = request.business
    
    # Get date range from query params or default to last 12 months
    end_date = timezone.now().date()
    start_date = end_date - timedelta(days=365)
    
    # Get all ledger entries
    entries = FarmLedgerEntry.objects.filter(
        business=business,
        date__gte=start_date,
        date__lte=end_date,
    )
    
    # Calculate totals
    totals = entries.aggregate(
        total_income=Coalesce(
            Sum("amount_mwk", filter=~models.Q(entry_type=FarmEntryType.EXPENSE)),
            Decimal("0"),
        ),
        total_expenses=Coalesce(
            Sum("amount_mwk", filter=models.Q(entry_type=FarmEntryType.EXPENSE)),
            Decimal("0"),
        ),
        sales_count=Count("id", filter=models.Q(entry_type=FarmEntryType.SALE)),
        expense_count=Count("id", filter=models.Q(entry_type=FarmEntryType.EXPENSE)),
    )
    
    # Expense breakdown by category
    expense_by_category = (
        entries.filter(entry_type=FarmEntryType.EXPENSE)
        .values("category")
        .annotate(total=Sum("amount_mwk"))
        .order_by("-total")
    )
    
    # Income breakdown by enterprise type
    income_by_type = (
        entries.filter(entry_type=FarmEntryType.SALE)
        .values("enterprise_type")
        .annotate(total=Sum("amount_mwk"), count=Count("id"))
        .order_by("-total")
    )
    
    # Generate CSV
    output = StringIO()
    writer = csv.writer(output)
    
    # Header
    writer.writerow(["Farm Profit & Loss Report"])
    writer.writerow([f"Business: {business.name}"])
    writer.writerow([f"Period: {start_date} to {end_date}"])
    writer.writerow([f"Generated: {timezone.now().strftime('%Y-%m-%d %H:%M')}"])
    writer.writerow([])
    
    # Summary
    writer.writerow(["=== SUMMARY ==="])
    writer.writerow(["Metric", "Amount (MWK)"])
    writer.writerow(["Total Income", totals["total_income"]])
    writer.writerow(["Total Expenses", totals["total_expenses"]])
    writer.writerow(["Net Profit", totals["total_income"] - totals["total_expenses"]])
    writer.writerow(["Sales Count", totals["sales_count"]])
    writer.writerow(["Expense Count", totals["expense_count"]])
    writer.writerow([])
    
    # Expense breakdown
    writer.writerow(["=== EXPENSE BREAKDOWN ==="])
    writer.writerow(["Category", "Amount (MWK)"])
    for cat in expense_by_category:
        writer.writerow([cat["category"], cat["total"]])
    writer.writerow([])
    
    # Income breakdown
    writer.writerow(["=== INCOME BREAKDOWN ==="])
    writer.writerow(["Enterprise Type", "Amount (MWK)", "Count"])
    for inc in income_by_type:
        writer.writerow([inc["enterprise_type"], inc["total"], inc["count"]])
    writer.writerow([])
    
    # Transaction detail
    writer.writerow(["=== TRANSACTION DETAIL ==="])
    writer.writerow(["Date", "Type", "Category", "Description", "Amount (MWK)"])
    for entry in entries.order_by("-date")[:100]:  # Limit to 100 for performance
        writer.writerow([
            entry.date.isoformat(),
            entry.get_entry_type_display(),
            entry.category,
            entry.description,
            entry.amount_mwk,
        ])
    
    response = HttpResponse(output.getvalue(), content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="profit_loss_{end_date.isoformat()}.csv"'
    return response


@login_required
@require_business
@require_business_kind(BusinessKind.FARM)
def livestock_report(request: HttpRequest) -> HttpResponse:
    """
    Generate Livestock report as CSV.
    Batch counts, events, and valuation summary.
    """
    business = request.business
    
    # Get all batches
    batches = FarmLivestockBatch.objects.filter(business=business).order_by("-created_at")
    
    # Get all events
    events = FarmLivestockEvent.objects.filter(batch__business=business).order_by("-date")
    
    # Calculate summary
    total_animals = sum(b.count_current for b in batches if b.is_active)
    total_value = sum(
        b.estimated_value_mwk or Decimal("0") 
        for b in batches 
        if b.is_active and b.estimated_value_mwk
    )
    
    # Generate CSV
    output = StringIO()
    writer = csv.writer(output)
    
    # Header
    writer.writerow(["Farm Livestock Report"])
    writer.writerow([f"Business: {business.name}"])
    writer.writerow([f"Generated: {timezone.now().strftime('%Y-%m-%d %H:%M')}"])
    writer.writerow([])
    
    # Summary
    writer.writerow(["=== SUMMARY ==="])
    writer.writerow(["Total Active Batches", batches.filter(is_active=True).count()])
    writer.writerow(["Total Animals", total_animals])
    writer.writerow(["Estimated Total Value (MWK)", total_value or "N/A"])
    writer.writerow([])
    
    # Batch detail
    writer.writerow(["=== BATCH DETAIL ==="])
    writer.writerow(["Name", "Animal Type", "Current Count", "Status", "Est. Value (MWK)", "Created"])
    for batch in batches:
        writer.writerow([
            batch.name,
            batch.get_animal_type_display(),
            batch.count_current,
            "Active" if batch.is_active else "Inactive",
            batch.estimated_value_mwk or "N/A",
            batch.created_at.strftime("%Y-%m-%d"),
        ])
    writer.writerow([])
    
    # Recent events
    writer.writerow(["=== RECENT EVENTS (Last 50) ==="])
    writer.writerow(["Date", "Batch", "Event Type", "Count", "Unit Price", "Notes"])
    for event in events[:50]:
        writer.writerow([
            event.date.isoformat(),
            event.batch.name,
            event.get_event_type_display(),
            event.count,
            event.unit_price_mwk or "N/A",
            event.notes[:50] if event.notes else "",
        ])
    
    response = HttpResponse(output.getvalue(), content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="livestock_report_{timezone.now().date().isoformat()}.csv"'
    return response


@login_required
@require_business
@require_business_kind(BusinessKind.FARM)
def crop_season_report(request: HttpRequest) -> HttpResponse:
    """
    Generate Crop Season report as CSV.
    Season projections vs actuals summary.
    """
    from django.db import models
    
    business = request.business
    
    # Get all seasons
    seasons = FarmCropSeason.objects.filter(business=business).order_by("-start_date")
    
    # Calculate summary
    active_seasons = seasons.filter(status__in=[FarmSeasonStatus.PLANNING, FarmSeasonStatus.ACTIVE])
    completed_seasons = seasons.filter(status__in=[FarmSeasonStatus.HARVESTED, FarmSeasonStatus.CLOSED])
    
    total_projected = sum(
        s.projected_income_mwk or Decimal("0") 
        for s in seasons 
        if s.projected_income_mwk
    )
    total_actual = sum(
        s.actual_income_mwk or Decimal("0") 
        for s in seasons 
        if s.actual_income_mwk
    )
    
    # Generate CSV
    output = StringIO()
    writer = csv.writer(output)
    
    # Header
    writer.writerow(["Farm Crop Season Report"])
    writer.writerow([f"Business: {business.name}"])
    writer.writerow([f"Generated: {timezone.now().strftime('%Y-%m-%d %H:%M')}"])
    writer.writerow([])
    
    # Summary
    writer.writerow(["=== SUMMARY ==="])
    writer.writerow(["Total Seasons", seasons.count()])
    writer.writerow(["Active Seasons", active_seasons.count()])
    writer.writerow(["Completed Seasons", completed_seasons.count()])
    writer.writerow(["Total Projected Income (MWK)", total_projected])
    writer.writerow(["Total Actual Income (MWK)", total_actual or "Pending"])
    writer.writerow([])
    
    # Season detail
    writer.writerow(["=== SEASON DETAIL ==="])
    writer.writerow([
        "Name", "Crop", "Status", "Area", "Start Date", "End Date",
        "Projected Yield", "Actual Yield", "Projected Income (MWK)", "Actual Income (MWK)"
    ])
    for season in seasons:
        writer.writerow([
            season.name,
            season.get_crop_type_display(),
            season.get_status_display(),
            f"{season.area_value} {season.area_unit}",
            season.start_date.isoformat(),
            season.end_date.isoformat() if season.end_date else "Ongoing",
            f"{season.projected_yield or 'N/A'} {season.yield_unit}" if season.projected_yield else "N/A",
            f"{season.actual_yield or 'N/A'} {season.yield_unit}" if season.actual_yield else "N/A",
            season.projected_income_mwk or "N/A",
            season.actual_income_mwk or "N/A",
        ])
    writer.writerow([])
    
    # Get ledger entries linked to seasons
    writer.writerow(["=== EXPENSES BY SEASON ==="])
    writer.writerow(["Season", "Total Expenses (MWK)", "Entries Count"])
    for season in seasons:
        expenses = FarmLedgerEntry.objects.filter(
            crop_season=season,
            entry_type=FarmEntryType.EXPENSE,
        ).aggregate(
            total=Coalesce(Sum("amount_mwk"), Decimal("0")),
            count=Count("id"),
        )
        writer.writerow([
            season.name,
            expenses["total"],
            expenses["count"],
        ])
    
    response = HttpResponse(output.getvalue(), content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="crop_season_report_{timezone.now().date().isoformat()}.csv"'
    return response


@login_required
@require_business
@require_business_kind(BusinessKind.FARM)
def ledger_export(request: HttpRequest) -> HttpResponse:
    """Export full ledger as CSV."""
    business = request.business
    
    entries = FarmLedgerEntry.objects.filter(business=business).order_by("-date")
    
    output = StringIO()
    writer = csv.writer(output)
    
    writer.writerow([
        "Date", "Type", "Enterprise", "Category", "Description",
        "Amount (MWK)", "Quantity", "Unit", "Payment Method", "Notes"
    ])
    
    for entry in entries:
        writer.writerow([
            entry.date.isoformat(),
            entry.get_entry_type_display(),
            entry.get_enterprise_type_display(),
            entry.category,
            entry.description,
            entry.amount_mwk,
            entry.quantity or "",
            entry.get_unit_display() if entry.unit else "",
            entry.get_payment_method_display(),
            entry.notes[:100] if entry.notes else "",
        ])
    
    response = HttpResponse(output.getvalue(), content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="farm_ledger_{timezone.now().date().isoformat()}.csv"'
    return response


@login_required
@require_business
@require_business_kind(BusinessKind.FARM)
def livestock_export(request: HttpRequest) -> HttpResponse:
    """Export livestock batches as CSV."""
    business = request.business
    
    batches = FarmLivestockBatch.objects.filter(business=business).order_by("-created_at")
    
    output = StringIO()
    writer = csv.writer(output)
    
    writer.writerow([
        "Name", "Animal Type", "Current Count", "Active",
        "Avg Weight (kg)", "Price/kg (MWK)", "Price/Animal (MWK)", 
        "Est. Value (MWK)", "Notes", "Created"
    ])
    
    for batch in batches:
        writer.writerow([
            batch.name,
            batch.get_animal_type_display(),
            batch.count_current,
            "Yes" if batch.is_active else "No",
            batch.avg_weight_kg or "",
            batch.price_per_kg_mwk or "",
            batch.price_per_animal_mwk or "",
            batch.estimated_value_mwk or "",
            batch.notes[:100] if batch.notes else "",
            batch.created_at.strftime("%Y-%m-%d"),
        ])
    
    response = HttpResponse(output.getvalue(), content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="farm_livestock_{timezone.now().date().isoformat()}.csv"'
    return response


@login_required
@require_business
@require_business_kind(BusinessKind.FARM)
def crops_export(request: HttpRequest) -> HttpResponse:
    """Export crop seasons as CSV."""
    business = request.business
    
    seasons = FarmCropSeason.objects.filter(business=business).order_by("-start_date")
    
    output = StringIO()
    writer = csv.writer(output)
    
    writer.writerow([
        "Name", "Crop Type", "Status", "Start Date", "End Date",
        "Area", "Unit", "Projected Yield", "Actual Yield",
        "Projected Price/Unit", "Actual Price/Unit",
        "Projected Income", "Actual Income", "Notes"
    ])
    
    for season in seasons:
        writer.writerow([
            season.name,
            season.get_crop_type_display(),
            season.get_status_display(),
            season.start_date.isoformat(),
            season.end_date.isoformat() if season.end_date else "",
            season.area_value,
            season.area_unit,
            season.projected_yield or "",
            season.actual_yield or "",
            season.projected_price_per_unit_mwk or "",
            season.actual_price_per_unit_mwk or "",
            season.projected_income_mwk or "",
            season.actual_income_mwk or "",
            season.notes[:100] if season.notes else "",
        ])
    
    response = HttpResponse(output.getvalue(), content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="farm_crops_{timezone.now().date().isoformat()}.csv"'
    return response

