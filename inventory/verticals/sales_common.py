"""
Shared sales history functionality for all verticals.
This module provides reusable helpers to avoid duplication across phones, liquor, pharmacy, etc.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional, Protocol

from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import QuerySet, Sum, Count, Q
from django.http import HttpResponse
from django.utils import timezone


# ===============================================================================
# ADAPTER PROTOCOL
# ===============================================================================


class SaleAdapter(Protocol):
    """
    Protocol defining the interface a vertical must implement to use shared sales history.
    """

    @property
    def sale_model(self):
        """Return the Sale model class (e.g., PhoneSale, LiquorSale)"""
        ...

    @property
    def timestamp_field(self) -> str:
        """Return the name of the timestamp field (e.g., 'sold_at', 'created_at')"""
        ...

    @property
    def cost_field(self) -> Optional[str]:
        """Return the name of the total cost field, or None if not available"""
        ...

    @property
    def total_price_field(self) -> str:
        """Return the name of the total price/revenue field"""
        ...

    @property
    def payment_method_field(self) -> str:
        """Return the name of the payment method field"""
        ...

    @property
    def cashier_field(self) -> str:
        """Return the name of the cashier/sold_by field"""
        ...

    @property
    def location_field(self) -> Optional[str]:
        """Return the name of the location field, or None if not available"""
        ...

    def get_base_queryset(self, business, location=None) -> QuerySet:
        """Return base queryset filtered by business and optionally location"""
        ...

    def get_search_fields(self) -> List[str]:
        """Return list of field names to search (e.g., ['product__name', 'notes'])"""
        ...

    def get_item_label(self, sale) -> str:
        """Return a human-readable label for the item sold"""
        ...

    def get_extra_csv_columns(self) -> List[str]:
        """Return list of extra column headers for CSV export"""
        ...

    def get_extra_csv_values(self, sale) -> List[str]:
        """Return list of extra column values for CSV export"""
        ...


# ===============================================================================
# DATE RANGE PARSING
# ===============================================================================


def parse_period(request) -> tuple[date, date, str, str]:
    """
    Parse date range from request GET parameters.
    Supports: today, 7d (last 7 days), mtd (month-to-date), custom (start/end dates).

    Returns:
        Tuple of (start_date, end_date, range_type, custom_params_str)
    """
    range_type = request.GET.get("range", "7d")  # Default to last 7 days
    start_param = request.GET.get("start", "")
    end_param = request.GET.get("end", "")

    today = timezone.now().date()

    if range_type == "today":
        start_date = today
        end_date = today
    elif range_type == "7d":
        start_date = today - timedelta(days=6)
        end_date = today
    elif range_type == "mtd":
        start_date = today.replace(day=1)
        end_date = today
    elif range_type == "custom" and start_param and end_param:
        try:
            start_date = datetime.strptime(start_param, "%Y-%m-%d").date()
            end_date = datetime.strptime(end_param, "%Y-%m-%d").date()
        except ValueError:
            # Fallback to 7d if invalid
            start_date = today - timedelta(days=6)
            end_date = today
            range_type = "7d"
    else:
        # Default to 7d
        start_date = today - timedelta(days=6)
        end_date = today
        range_type = "7d"

    custom_params = f"start={start_date}&end={end_date}" if start_param and end_param else ""

    return start_date, end_date, range_type, custom_params


# ===============================================================================
# SEARCH FILTERING
# ===============================================================================


def apply_search(queryset: QuerySet, search_term: str, fields: List[str]) -> QuerySet:
    """
    Apply search filter across multiple fields using Q objects.

    Args:
        queryset: Base queryset to filter
        search_term: Search string from user
        fields: List of field paths to search (e.g., ['product__name', 'notes'])

    Returns:
        Filtered queryset
    """
    if not search_term or not fields:
        return queryset

    q_objects = Q()
    for field in fields:
        q_objects |= Q(**{f"{field}__icontains": search_term})

    return queryset.filter(q_objects)


# ===============================================================================
# SUMMARY STATISTICS
# ===============================================================================


def compute_summary(queryset: QuerySet, adapter: SaleAdapter) -> Dict[str, Any]:
    """
    Compute summary statistics for a sales queryset.

    Returns:
        Dictionary with total_revenue, total_cost, total_sales, total_items
    """
    aggregations = {
        "total_revenue": Sum(adapter.total_price_field),
        "total_sales": Count("id"),
    }

    # Add cost aggregation if available
    if adapter.cost_field:
        aggregations["total_cost"] = Sum(adapter.cost_field)

    # Check if there's a quantity field
    if hasattr(queryset.model, "quantity"):
        aggregations["total_items"] = Sum("quantity")
    else:
        # For phones (individual items), count == items
        aggregations["total_items"] = Count("id")

    summary = queryset.aggregate(**aggregations)

    return {
        "total_revenue": summary.get("total_revenue") or Decimal("0.00"),
        "total_cost": summary.get("total_cost") or Decimal("0.00"),
        "total_sales": summary.get("total_sales") or 0,
        "total_items": summary.get("total_items") or 0,
    }


# ===============================================================================
# TREND DATA
# ===============================================================================


def build_trend(queryset: QuerySet, start_date: date, end_date: date, adapter: SaleAdapter) -> Dict[str, List]:
    """
    Build trend data for Chart.js.

    Returns:
        Dictionary with 'labels', 'revenue', 'count' lists
    """
    labels = []
    revenue_values = []
    count_values = []

    current_date = start_date
    while current_date <= end_date:
        # Filter sales for this specific date
        day_filter = {f"{adapter.timestamp_field}__date": current_date}
        day_sales = queryset.filter(**day_filter)

        day_revenue = day_sales.aggregate(total=Sum(adapter.total_price_field))["total"] or Decimal("0.00")
        day_count = day_sales.count()

        labels.append(current_date.strftime("%b %d"))
        revenue_values.append(float(day_revenue))
        count_values.append(day_count)

        current_date += timedelta(days=1)

    return {
        "labels": labels,
        "revenue": revenue_values,
        "count": count_values,
    }


# ===============================================================================
# CSV EXPORT
# ===============================================================================


def export_to_csv(
    queryset: QuerySet,
    adapter: SaleAdapter,
    filename: str,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> HttpResponse:
    """
    Export sales queryset to CSV with proper headers and formatting.

    Args:
        queryset: Sales queryset to export
        adapter: Vertical-specific adapter
        filename: Base filename (will add timestamp)
        start_date: Optional start date for filtering
        end_date: Optional end date for filtering

    Returns:
        HttpResponse with CSV content
    """
    # Apply date filters if provided
    if start_date:
        queryset = queryset.filter(**{f"{adapter.timestamp_field}__date__gte": start_date})
    if end_date:
        queryset = queryset.filter(**{f"{adapter.timestamp_field}__date__lte": end_date})

    # Order by timestamp descending
    queryset = queryset.order_by(f"-{adapter.timestamp_field}")

    # Create CSV response
    timestamp_str = timezone.now().strftime("%Y%m%d_%H%M")
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{filename}_{timestamp_str}.csv"'

    writer = csv.writer(response)

    # Base headers
    headers = [
        "Timestamp",
        "Date",
        "Time",
        "Sale ID",
        "Item",
        "Qty",
        "Unit Price",
        "Total",
        "Payment Method",
        "Cashier",
    ]

    # Add extra columns from adapter
    extra_headers = adapter.get_extra_csv_columns()
    headers.extend(extra_headers)

    # Add location if available
    if adapter.location_field:
        headers.append("Location")

    writer.writerow(headers)

    # Write data rows
    for sale in queryset:
        # Get timestamp
        timestamp = getattr(sale, adapter.timestamp_field)
        if timestamp:
            local_timestamp = timezone.localtime(timestamp)
            timestamp_str = local_timestamp.strftime("%Y-%m-%d %H:%M:%S")
            date_str = local_timestamp.strftime("%Y-%m-%d")
            time_str = local_timestamp.strftime("%H:%M:%S")
        else:
            timestamp_str = date_str = time_str = ""

        # Get item label
        item_label = adapter.get_item_label(sale)

        # Get quantity (if available)
        qty = getattr(sale, "quantity", 1)

        # Get prices
        total_price = getattr(sale, adapter.total_price_field, Decimal("0.00"))
        unit_price = total_price / Decimal(qty) if qty > 0 else total_price

        # Get payment method
        payment_field = getattr(sale, adapter.payment_method_field, "")
        if hasattr(sale, "get_" + adapter.payment_method_field + "_display"):
            payment_method = getattr(sale, "get_" + adapter.payment_method_field + "_display")()
        else:
            payment_method = payment_field

        # Get cashier
        cashier_obj = getattr(sale, adapter.cashier_field, None)
        cashier = cashier_obj.username if cashier_obj else "System"

        # Base row
        row = [
            timestamp_str,
            date_str,
            time_str,
            sale.id,
            item_label,
            qty,
            f"{unit_price:.2f}",
            f"{total_price:.2f}",
            payment_method,
            cashier,
        ]

        # Add extra values from adapter
        extra_values = adapter.get_extra_csv_values(sale)
        row.extend(extra_values)

        # Add location if available
        if adapter.location_field:
            location_obj = getattr(sale, adapter.location_field, None)
            location_name = location_obj.name if location_obj else "N/A"
            row.append(location_name)

        writer.writerow(row)

    return response


# ===============================================================================
# PAGINATED SALES VIEW
# ===============================================================================


def get_paginated_sales(
    queryset: QuerySet,
    adapter: SaleAdapter,
    page_number: int = 1,
    per_page: int = 50,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    search_query: str = "",
    sale_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Get paginated sales with filters applied.

    Args:
        queryset: Base queryset
        adapter: Vertical adapter
        page_number: Page number to return
        per_page: Number of items per page
        start_date: Optional start date filter
        end_date: Optional end date filter
        search_query: Optional search string
        sale_id: Optional sale ID to highlight

    Returns:
        Dictionary with sales page, summary, highlighted_sale_id
    """
    # Apply date filters
    if start_date:
        queryset = queryset.filter(**{f"{adapter.timestamp_field}__date__gte": start_date})
    if end_date:
        queryset = queryset.filter(**{f"{adapter.timestamp_field}__date__lte": end_date})

    # Apply search filter
    if search_query:
        search_fields = adapter.get_search_fields()
        queryset = apply_search(queryset, search_query, search_fields)

    # Check if highlighted sale exists in filtered results
    highlighted_sale_id = None
    if sale_id:
        try:
            highlighted_sale_id = int(sale_id)
            if not queryset.filter(id=highlighted_sale_id).exists():
                highlighted_sale_id = None
        except (ValueError, TypeError):
            pass

    # Order by timestamp descending
    queryset = queryset.order_by(f"-{adapter.timestamp_field}")

    # Compute summary before pagination
    summary = compute_summary(queryset, adapter)

    # Paginate
    paginator = Paginator(queryset, per_page)

    try:
        sales_page = paginator.page(page_number)
    except PageNotAnInteger:
        sales_page = paginator.page(1)
    except EmptyPage:
        sales_page = paginator.page(paginator.num_pages if paginator.num_pages > 0 else 1)

    return {
        "sales": sales_page,
        "summary": summary,
        "highlighted_sale_id": highlighted_sale_id,
    }
