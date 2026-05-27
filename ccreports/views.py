# ccreports/views.py
from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Tuple

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.template import TemplateDoesNotExist
from django.template.loader import get_template

# SSOT: Import context defaults to prevent KeyError failures
from reports.services.context_defaults import apply_default_report_context

__all__ = [
    "home", "sales_report", "inventory_report", "which_templates",
    "pl_report", "executive_summary", "credit_exposure_report",
    "sales_report_pdf", "inventory_report_pdf",
    "pl_report_pdf", "executive_summary_pdf",
]

log = logging.getLogger(__name__)


# --------------------------------------------------
# Internal helpers
# --------------------------------------------------
def _resolve_first(names: Iterable[str]) -> Tuple[str | None, str | None, List[str]]:
    """
    Try each template name until one resolves.
    Returns (chosen_name, origin_path, errors).
    """
    errors: List[str] = []
    for name in names:
        try:
            t = get_template(name)
            origin = getattr(getattr(t, "origin", None), "name", None)
            return name, origin, errors
        except TemplateDoesNotExist as e:
            errors.append(f"{name}: {e}")
        except Exception as e:
            errors.append(f"{name}: {e.__class__.__name__}: {e}")
    return None, None, errors


def _render_with_candidates(
    request: HttpRequest,
    candidates: Iterable[str],
    context: Dict[str, Any],
) -> HttpResponse:
    """
    Render the first template that exists from `candidates`.
    Also prints/logs which template/origin was used and sets response headers.
    """
    chosen, origin, errs = _resolve_first(candidates)

    if chosen:
        msg = f">> REPORTS USING TEMPLATE {chosen}: {origin or '(unknown origin)'}"
        print(msg)
        log.debug(msg)

        resp = render(request, chosen, context)
        resp["X-Reports-Template"] = chosen
        if origin:
            resp["X-Template-Origin"] = origin
        return resp

    # Nothing found - return a helpful error page (keeps you out of a raw 500)
    pretty = "\n".join(f"- {e}" for e in errs) or "(no details)"
    html = f"""
      <h1>Reports template not found</h1>
      <p>None of the candidate templates could be located. Looked for:</p>
      <pre style="white-space:pre-wrap">{pretty}</pre>
      <p>Create one of these files and refresh:</p>
      <ul>
        <li><code>templates/ccreports/...</code></li>
        <li><code>templates/reports/...</code></li>
      </ul>
    """.strip()
    print(">> REPORTS TEMPLATE RESOLVE FAILED\n" + pretty)
    log.error("REPORTS TEMPLATE RESOLVE FAILED: %s", pretty)
    return HttpResponse(html, status=500)


# --------------------------------------------------
# Views
# --------------------------------------------------
@login_required
def home(request: HttpRequest) -> HttpResponse:
    """
    Reports dashboard landing page.
    """
    # Delegate to the full reports.views.reports_home for complete functionality
    try:
        from reports.views import reports_home
        return reports_home(request)
    except ImportError:
        # Fallback: minimal context with SSOT defaults
        ctx: Dict[str, Any] = {
            "title": "Reports",
            "subtitle": "Overview",
        }
        
        # Apply SSOT defaults to prevent KeyError failures
        ctx = apply_default_report_context(ctx)
        
        # Try app-specific first, then generic folder for compatibility
        return _render_with_candidates(
            request,
            candidates=("ccreports/home.html", "reports/home.html"),
            context=ctx,
        )


@login_required
def sales_report(request: HttpRequest) -> HttpResponse:
    """
    Sales report view (safe defaults).
    """
    # Delegate to the full reports.views.sales_report for complete functionality
    try:
        from reports.views import sales_report as reports_sales
        return reports_sales(request)
    except ImportError:
        # Fallback: minimal context with SSOT defaults
        ctx: Dict[str, Any] = {
            "title": "Reports - Sales",
            "top_models": [],
            "agents": [],
            "recent_sales": [],
            "page_obj": None,
        }
        
        # Apply SSOT defaults to prevent KeyError failures
        ctx = apply_default_report_context(ctx)
        
        return _render_with_candidates(
            request,
            candidates=("ccreports/sales.html", "reports/sales.html"),
            context=ctx,
        )


@login_required
def inventory_report(request: HttpRequest) -> HttpResponse:
    """
    Inventory report view (safe defaults).
    """
    try:
        from reports.views import inventory_report as reports_inventory
        return reports_inventory(request)
    except ImportError:
        pass

    ctx: Dict[str, Any] = {
        "title": "Reports - Inventory",
        "low_stock": [],
        "ageing": [],
        "turnover": [],
        "groups": [],
        "snapshot": [],
        "page_obj": None,
    }
    
    # Apply SSOT defaults to prevent KeyError failures
    ctx = apply_default_report_context(ctx)
    
    return _render_with_candidates(
        request,
        candidates=("ccreports/inventory.html", "reports/inventory.html"),
        context=ctx,
    )


@login_required
def sales_report_pdf(request: HttpRequest) -> HttpResponse:
    try:
        from reports.views import sales_report_pdf as reports_sales_pdf
        return reports_sales_pdf(request)
    except ImportError:
        return HttpResponse("Sales report PDF is not available.", status=503, content_type="text/plain")


@login_required
def inventory_report_pdf(request: HttpRequest) -> HttpResponse:
    try:
        from reports.views import inventory_report_pdf as reports_inventory_pdf
        return reports_inventory_pdf(request)
    except ImportError:
        return HttpResponse("Stock report PDF is not available.", status=503, content_type="text/plain")


# --------------------------------------------------
# New premium report views (additive)
# --------------------------------------------------

def _get_business(request: HttpRequest):
    """Get active business from request (multi-tenant aware)."""
    biz = getattr(request, "business", None) or getattr(request, "active_business", None)
    if biz:
        return biz
    try:
        bid = request.session.get("active_business_id") or request.session.get("biz_id")
        if bid:
            from tenants.models import Business
            return Business.objects.filter(pk=bid).first()
    except Exception:
        pass
    return None


def _pl_data(business, start_date: date, end_date: date) -> Dict[str, Any]:
    """Collect P&L data for a date range. Graceful — returns zeros on error."""
    data: Dict[str, Any] = {
        "revenue": Decimal("0"),
        "cogs": Decimal("0"),
        "gross_profit": Decimal("0"),
        "expenses": Decimal("0"),
        "net_profit": Decimal("0"),
        "sales_count": 0,
        "avg_transaction": Decimal("0"),
        "top_products": [],
        "monthly_trend": [],
    }
    if not business:
        return data
    try:
        from django.db.models import Sum, Count, Avg, F
        from inventory.models import InventoryItem, Sale
        from django.db.models.functions import TruncMonth

        sales_qs = Sale.objects.filter(
            item__business=business,
            sold_at__date__gte=start_date,
            sold_at__date__lte=end_date,
        )

        agg = sales_qs.aggregate(
            total_revenue=Sum("price"),
            total_cogs=Sum("cost"),
            total_count=Count("id"),
        )
        revenue = agg["total_revenue"] or Decimal("0")
        cogs = agg["total_cogs"] or Decimal("0")
        count = agg["total_count"] or 0

        data["revenue"] = revenue
        data["cogs"] = cogs
        data["gross_profit"] = revenue - cogs
        data["sales_count"] = count
        data["avg_transaction"] = (revenue / count) if count else Decimal("0")

        # Top products by revenue
        try:
            top = (
                sales_qs
                .values("item__product__name", "item__product__model_number")
                .annotate(total=Sum("price"), units=Count("id"))
                .order_by("-total")[:10]
            )
            data["top_products"] = list(top)
        except Exception:
            pass

        # Monthly trend (last 6 months)
        try:
            trend = (
                Sale.objects.filter(
                    item__business=business,
                    sold_at__date__gte=start_date - timedelta(days=180),
                    sold_at__date__lte=end_date,
                )
                .annotate(month=TruncMonth("sold_at"))
                .values("month")
                .annotate(revenue=Sum("price"), cogs=Sum("cost"), count=Count("id"))
                .order_by("month")
            )
            data["monthly_trend"] = [
                {
                    "month": r["month"].strftime("%b %Y") if r["month"] else "",
                    "revenue": float(r["revenue"] or 0),
                    "cogs": float(r["cogs"] or 0),
                    "profit": float((r["revenue"] or 0) - (r["cogs"] or 0)),
                    "count": r["count"],
                }
                for r in trend
            ]
        except Exception:
            pass

    except Exception as e:
        log.warning("P&L data error: %s", e)

    data["net_profit"] = data["gross_profit"] - data["expenses"]
    return data


@login_required
def pl_report(request: HttpRequest) -> HttpResponse:
    """Profit & Loss Statement — investor-grade."""
    business = _get_business(request)
    today = date.today()
    start_str = request.GET.get("start", (today.replace(day=1)).isoformat())
    end_str = request.GET.get("end", today.isoformat())
    try:
        start_date = date.fromisoformat(start_str)
        end_date = date.fromisoformat(end_str)
    except ValueError:
        start_date = today.replace(day=1)
        end_date = today

    pl = _pl_data(business, start_date, end_date)
    ctx: Dict[str, Any] = {
        "business": business,
        "title": "Profit & Loss Statement",
        "start_date": start_date,
        "end_date": end_date,
        "pl": pl,
        "gross_margin": (
            round(float(pl["gross_profit"]) / float(pl["revenue"]) * 100, 1)
            if pl["revenue"] else 0
        ),
        "net_margin": (
            round(float(pl["net_profit"]) / float(pl["revenue"]) * 100, 1)
            if pl["revenue"] else 0
        ),
    }
    ctx = apply_default_report_context(ctx)
    return _render_with_candidates(
        request,
        candidates=("ccreports/pl_report.html",),
        context=ctx,
    )


@login_required
def pl_report_pdf(request: HttpRequest) -> HttpResponse:
    """Download P&L as PDF using reportlab (graceful fallback if unavailable)."""
    try:
        import reportlab  # noqa
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet
        import io

        business = _get_business(request)
        today = date.today()
        start_date = today.replace(day=1)
        end_date = today
        pl = _pl_data(business, start_date, end_date)

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=40, leftMargin=40, topMargin=60, bottomMargin=60)
        styles = getSampleStyleSheet()
        story = []

        biz_name = getattr(business, "name", "Business") if business else "Business"
        story.append(Paragraph(f"<b>Profit & Loss Statement</b>", styles["Title"]))
        story.append(Paragraph(f"{biz_name} · {start_date.strftime('%d %b %Y')} to {end_date.strftime('%d %b %Y')}", styles["Normal"]))
        story.append(Spacer(1, 20))

        GREEN = colors.HexColor("#059669")
        table_data = [
            ["Metric", "Amount (MWK)"],
            ["Revenue", f"{pl['revenue']:,.0f}"],
            ["Cost of Goods Sold (COGS)", f"{pl['cogs']:,.0f}"],
            ["Gross Profit", f"{pl['gross_profit']:,.0f}"],
            ["Operating Expenses", f"{pl['expenses']:,.0f}"],
            ["Net Profit", f"{pl['net_profit']:,.0f}"],
        ]
        t = Table(table_data, colWidths=[300, 150])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), GREEN),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("ALIGN", (1, 0), (1, -1), "RIGHT"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f0fdf4")]),
            ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#bbf7d0")),
            ("PADDING", (0, 0), (-1, -1), 8),
        ]))
        story.append(t)
        doc.build(story)

        buffer.seek(0)
        fname = f"pl_report_{biz_name.replace(' ', '_')}_{today}.pdf"
        resp = HttpResponse(buffer, content_type="application/pdf")
        resp["Content-Disposition"] = f'attachment; filename="{fname}"'
        return resp

    except ImportError:
        return HttpResponse(
            "PDF export requires reportlab. Install it with: pip install reportlab",
            content_type="text/plain",
            status=501,
        )


@login_required
def executive_summary(request: HttpRequest) -> HttpResponse:
    """One-page executive summary — BHS + P&L + top products + credit."""
    business = _get_business(request)
    today = date.today()
    start_date = today.replace(day=1)
    end_date = today

    pl = _pl_data(business, start_date, end_date)

    health_score = None
    try:
        from dashboard.services_health import calculate_business_health_score
        health_score = calculate_business_health_score(business)
    except Exception as e:
        log.debug("BHS unavailable in exec summary: %s", e)

    credit_count = 0
    try:
        from layby.models import LaybyOrder
        credit_count = LaybyOrder.objects.filter(status="active").count()
    except Exception:
        pass

    ctx: Dict[str, Any] = {
        "business": business,
        "title": "Executive Summary",
        "report_date": today,
        "start_date": start_date,
        "end_date": end_date,
        "pl": pl,
        "health_score": health_score,
        "credit_count": credit_count,
        "gross_margin": (
            round(float(pl["gross_profit"]) / float(pl["revenue"]) * 100, 1)
            if pl["revenue"] else 0
        ),
    }
    ctx = apply_default_report_context(ctx)
    return _render_with_candidates(
        request,
        candidates=("ccreports/executive_summary.html",),
        context=ctx,
    )


@login_required
def executive_summary_pdf(request: HttpRequest) -> HttpResponse:
    """Download executive summary as PDF."""
    try:
        import reportlab  # noqa
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet
        import io

        business = _get_business(request)
        today = date.today()
        pl = _pl_data(business, today.replace(day=1), today)

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=40, leftMargin=40, topMargin=60, bottomMargin=60)
        styles = getSampleStyleSheet()
        story = []

        biz_name = getattr(business, "name", "Business") if business else "Business"
        story.append(Paragraph(f"<b>Executive Summary</b>", styles["Title"]))
        story.append(Paragraph(f"{biz_name} · Generated {today.strftime('%d %B %Y')}", styles["Normal"]))
        story.append(Spacer(1, 20))

        GREEN = colors.HexColor("#059669")
        table_data = [
            ["Metric", "Value"],
            ["Revenue (MTD)", f"MWK {pl['revenue']:,.0f}"],
            ["Gross Profit (MTD)", f"MWK {pl['gross_profit']:,.0f}"],
            ["Net Profit (MTD)", f"MWK {pl['net_profit']:,.0f}"],
            ["Sales Transactions", str(pl["sales_count"])],
        ]
        t = Table(table_data, colWidths=[300, 150])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), GREEN),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("ALIGN", (1, 0), (1, -1), "RIGHT"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f0fdf4")]),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#bbf7d0")),
            ("PADDING", (0, 0), (-1, -1), 8),
        ]))
        story.append(t)
        doc.build(story)

        buffer.seek(0)
        fname = f"executive_summary_{biz_name.replace(' ', '_')}_{today}.pdf"
        resp = HttpResponse(buffer, content_type="application/pdf")
        resp["Content-Disposition"] = f'attachment; filename="{fname}"'
        return resp

    except ImportError:
        return HttpResponse(
            "PDF export requires reportlab. Install it with: pip install reportlab",
            content_type="text/plain",
            status=501,
        )


@login_required
def credit_exposure_report(request: HttpRequest) -> HttpResponse:
    """Credit/layby portfolio overview — aging analysis."""
    business = _get_business(request)
    today = date.today()

    orders_data: List[Dict[str, Any]] = []
    summary: Dict[str, Any] = {
        "total_active": 0,
        "total_value": Decimal("0"),
        "total_outstanding": Decimal("0"),
        "total_completed": 0,
        "total_cancelled": 0,
        "aging_0_30": 0,
        "aging_31_60": 0,
        "aging_61_90": 0,
        "aging_over_90": 0,
    }

    if business:
        try:
            from layby.models import LaybyOrder
            Membership = None
            try:
                from tenants.models import Membership as M
                Membership = M
            except ImportError:
                pass

            qs = LaybyOrder.objects.prefetch_related("payments").order_by("-created_at")
            if Membership is not None:
                biz_user_ids = Membership.objects.filter(
                    business=business, status="ACTIVE"
                ).values_list("user_id", flat=True)
                qs = qs.filter(created_by_id__in=list(biz_user_ids))

            summary["total_active"] = qs.filter(status="active").count()
            summary["total_completed"] = qs.filter(status="completed").count()
            summary["total_cancelled"] = qs.filter(status="cancelled").count()

            for order in qs.filter(status="active"):
                age = (today - order.created_at.date()).days
                outstanding = order.balance
                summary["total_value"] += order.total_price or Decimal("0")
                summary["total_outstanding"] += outstanding

                if age <= 30:
                    summary["aging_0_30"] += 1
                elif age <= 60:
                    summary["aging_31_60"] += 1
                elif age <= 90:
                    summary["aging_61_90"] += 1
                else:
                    summary["aging_over_90"] += 1

                orders_data.append({
                    "ref": order.ref,
                    "customer": order.customer_name,
                    "phone": order.customer_phone,
                    "value": order.total_price,
                    "outstanding": outstanding,
                    "age_days": age,
                    "term_months": order.term_months,
                    "status": order.status,
                    "is_overdue": age > (order.term_months or 3) * 30,
                })
        except Exception as e:
            log.warning("Credit exposure data error: %s", e)

    ctx: Dict[str, Any] = {
        "business": business,
        "title": "Credit Exposure Report",
        "report_date": today,
        "orders": orders_data[:100],
        "summary": summary,
    }
    ctx = apply_default_report_context(ctx)
    return _render_with_candidates(
        request,
        candidates=("ccreports/credit_exposure.html",),
        context=ctx,
    )


# --------------------------------------------------
# Debug endpoint
# --------------------------------------------------
@login_required
def which_templates(request: HttpRequest) -> HttpResponse:
    """
    Show where each reports template is being resolved from.
    """

    def origin_for(cands: Iterable[str]) -> Dict[str, Any]:
        chosen, origin, errs = _resolve_first(cands)
        return {
            "candidates": list(cands),
            "chosen": chosen,
            "origin": origin,
            "errors": errs,
        }

    data = {
        "home": origin_for(("ccreports/home.html", "reports/home.html")),
        "sales": origin_for(("ccreports/sales.html", "reports/sales.html")),
        "inventory": origin_for(("ccreports/inventory.html", "reports/inventory.html")),
    }
    return JsonResponse(data, json_dumps_params={"indent": 2})
