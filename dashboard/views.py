# dashboard/views.py
from __future__ import annotations

from datetime import datetime, timedelta, time, date
from decimal import Decimal
from importlib import import_module

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import (
    Sum, F, DecimalField, CharField, ExpressionWrapper, Count, Case, When, QuerySet, Q, Value
)
from django.db.models.functions import TruncMonth
from django.http import JsonResponse, HttpResponseRedirect
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse, NoReverseMatch
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods
from django.views.decorators.cache import never_cache

from tenants.utils import require_business  # ✅ tenant guard

from inventory.models import InventoryItem
from sales.models import Sale
from reports.kpis import compute_sales_kpis
from inventory.utils_verticals import get_vertical_kind, get_vertical_dashboard_url, get_onboarding_steps

# Gamification imports
try:
    from hq.utils_gamification import (
        get_agent_rank_for_user,
        get_gamification_message,
        get_current_milestone,
        get_next_milestone,
        check_and_award_milestones
    )
    from hq.utils_dates import get_period_from_request
    GAMIFICATION_AVAILABLE = True
except ImportError:
    GAMIFICATION_AVAILABLE = False

# 🔗 Single source of truth (inventory)
from inventory.constants import IN_STOCK_Q, SOLD_Q
from inventory.queries import business_metrics, inventory_qs_for_user, inventory_qs_tenant

# Date range parsing for dashboard filters
try:
    from inventory.verticals.base import parse_date_range_from_request
    DATE_FILTER_AVAILABLE = True
except ImportError:
    DATE_FILTER_AVAILABLE = False

# Cache optional inventory models module once (safer / faster)
try:
    inv_models = import_module("inventory.models")
except Exception:
    inv_models = None

# ---- Optional wallet model (graceful if missing) ----
try:
    # WalletTxn often lives in inventory.models
    from inventory.models import WalletTxn
except Exception:
    try:
        from wallets.models import WalletTxn  # fallback path if you moved it
    except Exception:
        WalletTxn = None

# ---- Optional OTP decorator (no-op fallback if not available) ----
try:
    from accounts.decorators import otp_required  # type: ignore
except Exception:  # pragma: no cover
    def otp_required(view_func):
        return view_func


# ---------------------------
# Helpers
# ---------------------------
def _is_staff(user) -> bool:
    return user.is_authenticated and user.is_staff


def _namespace_exists(namespace: str) -> bool:
    """
    Check if a URL namespace is registered (safe for templates).
    Returns True if the namespace exists, False otherwise.
    """
    try:
        from django.urls import get_resolver
        resolver = get_resolver()
        # Check namespace_dict if available
        if hasattr(resolver, 'namespace_dict') and namespace in resolver.namespace_dict:
            return True
        # Fallback: try to reverse a likely common pattern
        try:
            reverse(f'{namespace}:home')
            return True
        except NoReverseMatch:
            pass
        # Try index as fallback
        try:
            reverse(f'{namespace}:index')
            return True
        except NoReverseMatch:
            pass
        return False
    except Exception:
        return False


def _start_of_day(d: date, tz):
    """Return tz-aware start of day for a date."""
    return datetime.combine(d, time.min, tzinfo=tz)


def _first_of_next_month(d: date):
    """Return a date for the first day of the next month (no calendar import)."""
    return (d.replace(day=28) + timedelta(days=4)).replace(day=1)


def _initials(user):
    """Initials from full name or username."""
    full = (getattr(user, "get_full_name", lambda: "")() or user.get_username()).strip()
    parts = full.split()
    if not parts:
        uname = user.get_username() or "User"
        return (uname[:2]).upper()
    return (parts[0][0] + (parts[1][0] if len(parts) > 1 else "")).upper()


def _get_greeting():
    """Return time-of-day greeting based on current hour."""
    now = timezone.localtime()
    hour = now.hour
    if hour < 12:
        return "Good morning"
    elif hour < 18:
        return "Good afternoon"
    else:
        return "Good evening"


def _reverse_agent_detail(user_id: int) -> str | None:
    """
    Try namespaced URL first, then legacy alias (for older templates).
    Returns None if neither exists.
    """
    try:
        return reverse("dashboard:admin_agent_detail", args=[user_id])
    except NoReverseMatch:
        try:
            return reverse("admin_agent_detail", args=[user_id])
        except NoReverseMatch:
            return None


def _wallet_summary_for(user):
    """
    Compact wallet summary for templates. Returns None if WalletTxn model
    isn't available so existing pages render unchanged.

    Shape:
    {
      "balance": <float>,
      "month": {"commission": <float>, "advance": <float>, "adjustment": <float>, "total": <float>},
      "month_label": "Aug 2025",
    }
    """
    if WalletTxn is None:
        return None

    today = timezone.localdate()
    month_start = today.replace(day=1)

    qs = WalletTxn.objects.filter(user=user)

    # If your WalletTxn has kind='DEBIT'/'CREDIT', convert to signed;
    # otherwise we assume 'amount' is already signed.
    fields = {getattr(f, "name", None) for f in WalletTxn._meta.get_fields()}
    signed_expr = F("amount")
    if "kind" in fields:
        signed_expr = Case(
            When(kind="DEBIT", then=-F("amount")),
            default=F("amount"),
            output_field=DecimalField(max_digits=14, decimal_places=2),
        )

    # Lifetime balance
    balance = qs.aggregate(v=Sum(signed_expr))["v"] or 0

    # This-month aggregates
    month_qs = qs.filter(created_at__date__gte=month_start, created_at__date__lte=today)

    def _sum_reason(code: str):
        q = month_qs
        if "reason" in fields:
            q = q.filter(reason=code)
        return q.aggregate(v=Sum(signed_expr))["v"] or 0

    month_commission = _sum_reason("COMMISSION")
    month_advance = _sum_reason("ADVANCE")
    month_adjustment = _sum_reason("ADJUSTMENT")
    month_total = month_qs.aggregate(v=Sum(signed_expr))["v"] or 0

    return {
        "balance": balance,
        "month": {
            "commission": month_commission,
            "advance": month_advance,
            "adjustment": month_adjustment,
            "total": month_total,
        },
        "month_label": month_start.strftime("%b %Y"),
    }


def _scope_queryset(qs: QuerySet, business):
    """
    Scope a queryset to the active business.
    Priority:
      1) If the queryset provides .for_business(), use it.
      2) If model has a 'business' field -> filter(business=business).
      3) If model lacks 'business' but has 'item' FK and that model has 'business',
         scope via item__business=business (e.g., Sale -> InventoryItem -> business).
      4) Otherwise return qs unchanged.
    """
    try:
        fn = getattr(qs, "for_business", None)
        if callable(fn):
            return fn(business)

        fields = {getattr(f, "name", None) for f in qs.model._meta.get_fields()}

        if business is not None:
            if "business" in fields:
                return qs.filter(business=business)

            # smart fallback: item__business (Sale → InventoryItem)
            if "item" in fields:
                try:
                    item_model = qs.model._meta.get_field("item").remote_field.model
                    item_fields = {getattr(f, "name", None) for f in item_model._meta.get_fields()}
                    if "business" in item_fields:
                        return qs.filter(item__business=business)
                except Exception:
                    pass
    except Exception:
        pass
    return qs


# --------- InventoryItem price helpers (avoid referencing missing fields) ---------
def _inv_price_field() -> str | None:
    """
    Returns the best available field name on InventoryItem to represent a sold price.
    Order of preference.
    """
    try:
        fields = {getattr(f, "name", None) for f in InventoryItem._meta.get_fields()}
    except Exception:
        fields = set()
    for name in ("sold_price", "selling_price", "price", "sale_price", "last_price"):
        if name in fields:
            return name
    return None


def _inv_revenue_sum(qs: QuerySet) -> float:
    """
    Sum revenue for InventoryItem queryset using the available price field.
    Returns a float (0.0 if no suitable field exists).
    """
    field = _inv_price_field()
    if not field:
        return 0.0
    try:
        val = qs.aggregate(v=Sum(F(field), output_field=DecimalField(max_digits=14, decimal_places=2)))["v"] or 0
        return float(val)
    except Exception:
        return 0.0


def _inv_profit_sum(qs: QuerySet) -> float:
    """
    Sum profit for InventoryItem queryset if both order_price and a price field exist.
    """
    field = _inv_price_field()
    try:
        inv_fields = {getattr(f, "name", None) for f in InventoryItem._meta.get_fields()}
    except Exception:
        inv_fields = set()
    if not field or "order_price" not in inv_fields:
        return 0.0
    try:
        expr = ExpressionWrapper(
            F(field) - F("order_price"),
            output_field=DecimalField(max_digits=14, decimal_places=2),
        )
        val = qs.aggregate(p=Sum(expr))["p"] or 0
        return float(val)
    except Exception:
        return 0.0


def _products_count(biz) -> int:
    """
    Count products for the active business.
    - If Product has a business field: straight count for that business.
    - If Product lacks business: count distinct products referenced by this
      business's InventoryItem, not global Product rows.
    - If Product model is missing: fallback to distinct InventoryItem.product.
    """
    try:
        Product = getattr(inv_models, "Product", None) if inv_models else None
        if Product:
            product_fields = {getattr(f, "name", None) for f in Product._meta.get_fields()}
            if "business" in product_fields:
                return _scope_queryset(Product.objects.all(), biz).count()

            # No business on Product: count only products actually used by THIS tenant's stock
            if hasattr(InventoryItem, "product"):
                return (
                    _scope_queryset(InventoryItem.objects.select_related("product"), biz)
                    .exclude(product__isnull=True)
                    .values("product_id")
                    .distinct()
                    .count()
                )

        # No Product model at all: fallback via InventoryItem
        if hasattr(InventoryItem, "product"):
            return (
                _scope_queryset(InventoryItem.objects.select_related("product"), biz)
                .exclude(product__isnull=True)
                .values("product_id")
                .distinct()
                .count()
            )
    except Exception:
        pass
    return 0


# ---------------------------
# Manager/tenant "home" (fresh dashboard UX)
# ---------------------------
@login_required
@require_business
def home(request):
    """
    Default dashboard for managers/agents within an active business.
    Shows a 'first-run' checklist when there's no data yet; otherwise normal KPIs.
    Staff users are redirected to the staff dashboard (per-tenant view if business is set).

    Routes to vertical-specific dashboards for gym, clothing, liquor, and pharmacy.

    NOTE: @require_business ensures request.business is set; if no active business,
    user is redirected to choose-business page, preventing redirect loops.
    """
    if request.user.is_staff:
        return redirect("dashboard:admin_dashboard")

    biz = request.business

    # ==============================================================================
    # VERTICAL ROUTING: Redirect to vertical-specific dashboards
    # ==============================================================================
    vertical_kind = get_vertical_kind(biz)
    vertical_dashboard_url = get_vertical_dashboard_url(vertical_kind)

    if vertical_dashboard_url:
        # Redirect to vertical-specific dashboard (gym, pharmacy, clothing, liquor)
        try:
            return redirect(vertical_dashboard_url)
        except NoReverseMatch:
            # If the URL doesn't exist, fall through to default dashboard
            pass

    # ===== DATE FILTER PARAMS =====
    # Parse date range from request (default to MTD like clothing)
    date_range_ctx = {}
    active_range = 'mtd'
    filter_start_date = None
    filter_end_date = None
    selected_date = None
    date_param = None

    if DATE_FILTER_AVAILABLE:
        try:
            date_range_ctx = parse_date_range_from_request(request)
            active_range = date_range_ctx.get('active_range', 'mtd')
            filter_start_date = date_range_ctx.get('start_date')
            filter_end_date = date_range_ctx.get('end_date')
            selected_date = date_range_ctx.get('selected_date')
            date_param = date_range_ctx.get('date_param')
        except Exception:
            # Fallback to MTD if parsing fails
            pass

    # Canonical KPI source (tenant-wide for the dashboard tiles)
    inv_kpis = business_metrics(request, include_agent_scope=False)

    products_count = _products_count(biz)
    stock_count = inv_kpis["count_instock"]

    Warehouse = getattr(inv_models, "Warehouse", None) if inv_models else None
    warehouses_count = _scope_queryset(Warehouse.objects.all(), biz).count() if Warehouse else 0

    # IMPORTANT: sales scoped even if Sale lacks 'business' (handled in _scope_queryset)
    sales_qs = _scope_queryset(Sale.objects.select_related("item"), biz)
    sales_count = sales_qs.count()
    first_run = (products_count == 0 and stock_count == 0 and sales_count == 0)

    # Simple per-tenant KPIs (safe)
    tz = timezone.get_current_timezone()
    today = timezone.localdate()

    # Use filter dates if available, otherwise use MTD
    if filter_start_date and filter_end_date:
        # Use the filtered date range
        period_start = _start_of_day(filter_start_date, tz)
        period_end = _start_of_day(filter_end_date, tz)
    else:
        # Default to MTD
        period_start = _start_of_day(today.replace(day=1), tz)
        period_end = _start_of_day(_first_of_next_month(today), tz)

    # Keep original month bounds for backwards compatibility
    month_start = _start_of_day(today.replace(day=1), tz)
    month_end = _start_of_day(_first_of_next_month(today), tz)

    # Try full KPIs when Sale rows exist, else fallback to InventoryItem SOLD rows
    # Use filtered period for KPIs
    try:
        kpis = compute_sales_kpis(sales_qs, dt_field="sold_at", amount_field="price") or {}
    except Exception:
        kpis = {}
    if not kpis or (kpis.get("orders") in (0, None) and kpis.get("revenue") in (0, None)):
        sold_items = (
            _scope_queryset(InventoryItem.objects.all(), biz)
            .filter(SOLD_Q())
        )
        period_qs = sold_items.filter(sold_at__gte=period_start, sold_at__lt=period_end)
        revenue = _inv_revenue_sum(period_qs)
        kpis = {"orders": period_qs.count(), "revenue": revenue, "scope": f"{biz.name}"}
    else:
        kpis["scope"] = f"{biz.name}"

    # Sold count for the selected period — from InventoryItem using SOLD_Q
    sold_period_count = (
        _scope_queryset(InventoryItem.objects.all(), biz)
        .filter(SOLD_Q(), sold_at__gte=period_start, sold_at__lt=period_end)
        .count()
    )

    # Keep MTD count for backwards compatibility (some parts may still use it)
    sold_mtd_count = sold_period_count

    # Onboarding steps tailored to business vertical
    onboarding_steps = get_onboarding_steps(vertical_kind, request)

    # ===== NEW: Personalized dashboard enhancements =====
    # Import helpers
    try:
        from dashboard.helpers_greetings import get_personalized_greeting
        from dashboard.helpers_yesterday import get_yesterday_summary, should_show_yesterday_summary, mark_yesterday_summary_shown
        from dashboard.helpers_payments import get_payment_mix_for_dashboard
        from dashboard.helpers_quotes import get_todays_quotes

        # Personalized greeting
        greeting_ctx = get_personalized_greeting(request.user, biz)

        # Brand header context
        brand_logo_url = None
        if hasattr(biz, 'logo') and biz.logo:
            brand_logo_url = biz.logo.url

        # Yesterday summary (show once per day)
        yesterday_summary = None
        if should_show_yesterday_summary(request):
            yesterday_summary = get_yesterday_summary(request.user, biz)
            if yesterday_summary:
                mark_yesterday_summary_shown(request)

        # Payment mix (last 30 days)
        payment_mix = get_payment_mix_for_dashboard(biz, period_days=30, user=None)

        # Daily quotes
        daily_quotes = get_todays_quotes(request.user, count=10)

        # Add to context
        ctx_enhancements = {
            "DASHBOARD_GREETING": greeting_ctx.get("greeting"),
            "DASHBOARD_USER_NAME": greeting_ctx.get("user_name"),
            "DASHBOARD_SHOW_WELCOME": greeting_ctx.get("show_welcome"),
            "DASHBOARD_MILESTONE_MESSAGE": greeting_ctx.get("milestone"),
            "DASHBOARD_BRAND_LOGO_URL": brand_logo_url,
            "DASHBOARD_BRAND_TITLE": biz.name if biz else "Dashboard",
            "YESTERDAY_SUMMARY": yesterday_summary,
            "PAYMENT_MIX": payment_mix,
            "PAYMENT_MIX_PERIOD": "Last 30 days",
            "DASHBOARD_QUOTES": daily_quotes,
        }
    except Exception:
        # Gracefully degrade if helpers not available
        ctx_enhancements = {}

    # ===== Enhanced Dashboard Data =====
    # Determine if user is manager or agent
    # CRITICAL: Use authoritative flag from middleware (set by tenants.utils_roles)
    if hasattr(request, "cc_is_manager"):
        is_manager = getattr(request, "cc_is_manager", False)
    else:
        # Fallback: if middleware hasn't set flag (shouldn't happen in normal flow)
        is_manager = (
            request.user.is_staff
            or request.user.is_superuser
            or getattr(request.user, 'is_manager', False)
            or getattr(getattr(request.user, 'profile', None), 'is_manager', False)
        )

    # Sales for the filtered period (respects date range selector)
    period_sold = _scope_queryset(InventoryItem.objects.all(), biz).filter(
        SOLD_Q(), sold_at__gte=period_start, sold_at__lt=period_end
    )
    period_sales_count = period_sold.count()
    period_sales_amount = _inv_revenue_sum(period_sold)

    # For display purposes, map to "today" or "month" variables based on active range
    # This maintains backwards compatibility with templates
    if active_range == 'today':
        today_sales_count = period_sales_count
        today_sales_amount = period_sales_amount
        month_sales_count = period_sales_count
        month_sales_amount = period_sales_amount
    else:
        # For other ranges, show in "month" metrics
        today_sales_count = period_sales_count
        today_sales_amount = period_sales_amount
        month_sales_count = period_sales_count
        month_sales_amount = period_sales_amount

    # Locations and agents count
    try:
        from inventory.models import Location
        locations_count = Location.objects.filter(business=biz).count()
    except Exception:
        locations_count = 0

    User = get_user_model()
    try:
        # Count users who have agent_profile for this business
        from inventory.models import AgentProfile
        agents_count = AgentProfile.objects.filter(location__business=biz).count()
    except Exception:
        agents_count = 0

    # Location performance (manager only)
    location_performance = []
    agent_leaderboard = []

    if is_manager:
        try:
            from inventory.models import Location
            locations = Location.objects.filter(business=biz)
            for loc in locations:
                loc_stock = _scope_queryset(InventoryItem.objects.all(), biz).filter(
                    current_location=loc, status='IN_STOCK'
                ).count()
                loc_sales = _scope_queryset(InventoryItem.objects.all(), biz).filter(
                    SOLD_Q(),
                    current_location=loc,
                    sold_at__gte=period_start, sold_at__lt=period_end
                )
                loc_amount = _inv_revenue_sum(loc_sales)

                location_performance.append({
                    'name': loc.name,
                    'stock_count': loc_stock,
                    'sales_amount': loc_amount,
                    'trend': 'up',  # TODO: Compare with last period
                })
        except Exception:
            pass

        # Agent leaderboard (using new service with filtered period)
        try:
            from tenants.services.leaderboard import get_agent_leaderboard
            agent_leaderboard = get_agent_leaderboard(
                business=biz,
                start=period_start.date(),
                end=period_end.date(),
                limit=10
            )
            # Convert to match template expectations
            for agent in agent_leaderboard:
                agent['amount'] = agent['total_sales_amount']
                agent['units'] = agent['devices_sold']
        except Exception as e:
            pass

    # Agent-specific data
    agent_today_amount = 0
    agent_today_count = 0
    agent_month_amount = 0
    agent_month_count = 0
    agent_rank = None
    agent_gap = None
    agent_commission = 0

    if not is_manager:
        try:
            # Agent's own sales for the filtered period
            agent_period_sales = _scope_queryset(InventoryItem.objects.all(), biz).filter(
                SOLD_Q(),
                assigned_agent=request.user,
                sold_at__gte=period_start, sold_at__lt=period_end
            )
            agent_period_count = agent_period_sales.count()
            agent_period_amount = _inv_revenue_sum(agent_period_sales)

            # Map to display variables
            agent_today_count = agent_period_count
            agent_today_amount = agent_period_amount
            agent_month_count = agent_period_count
            agent_month_amount = agent_period_amount

            # Calculate rank using new service with filtered period
            from tenants.services.leaderboard import get_current_agent_rank
            rank_data = get_current_agent_rank(
                business=biz,
                user=request.user,
                start=period_start.date(),
                end=period_end.date()
            )
            agent_rank = rank_data.get('rank')
            agent_gap = rank_data.get('gap_formatted')

            # Commission (simplified - assuming 5% of sales)
            agent_commission = agent_month_amount * Decimal('0.05')
        except Exception:
            pass

    # Check for optional namespaces
    has_reports_namespace = _namespace_exists("reports")

    # Check for payslip reminder banner (show if there's an unread payslip notification in last 10 days)
    show_payslip_banner = False
    try:
        from notifications.models import Notification
        ten_days_ago = timezone.now() - timedelta(days=10)
        show_payslip_banner = Notification.objects.filter(
            user=request.user,
            category='payslip_reminder',
            read_at__isnull=True,
            created_at__gte=ten_days_ago
        ).exists()
    except Exception:
        pass

    # ===== DYNAMIC STATS: Active Businesses & Agents (PREMIUM FEATURE) =====
    active_businesses_today = 0
    active_agents_today = 0
    new_agents_this_week = 0
    
    try:
        from tenants.models import Business, Membership
        from datetime import datetime, date
        
        # Count businesses with sales today (across all verticals)
        today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = timezone.now()
        
        # Try to count businesses with sales in multiple verticals
        businesses_with_activity = set()
        
        # Check ClothingSale
        try:
            from inventory.models_verticals import ClothingSale
            clothing_businesses = ClothingSale.objects.filter(
                sold_at__gte=today_start,
                sold_at__lte=today_end
            ).values_list('business_id', flat=True).distinct()
            businesses_with_activity.update(clothing_businesses)
        except Exception:
            pass
        
        # Check LiquorSale
        try:
            from inventory.models_verticals import LiquorSale
            liquor_businesses = LiquorSale.objects.filter(
                sold_at__gte=today_start,
                sold_at__lte=today_end
            ).values_list('business_id', flat=True).distinct()
            businesses_with_activity.update(liquor_businesses)
        except Exception:
            pass
        
        # Check PharmacySale
        try:
            from inventory.models_pharmacy import PharmacySale
            pharmacy_businesses = PharmacySale.objects.filter(
                sold_at__gte=today_start,
                sold_at__lte=today_end
            ).values_list('business_id', flat=True).distinct()
            businesses_with_activity.update(pharmacy_businesses)
        except Exception:
            pass
        
        # Check general Sale model (uses module-level import - do NOT re-import inside function)
        try:
            general_businesses = Sale.objects.filter(
                sold_at__gte=today_start,
                sold_at__lte=today_end
            ).values_list('business_id', flat=True).distinct()
            businesses_with_activity.update(general_businesses)
        except Exception:
            pass
        
        active_businesses_today = len(businesses_with_activity)
        
        # Count active agents today (agents who made sales today across all businesses)
        agents_with_activity = set()
        
        # Check ClothingSale for agents
        try:
            from inventory.models_verticals import ClothingSale
            clothing_agents = ClothingSale.objects.filter(
                sold_at__gte=today_start,
                sold_at__lte=today_end,
                sold_by__isnull=False
            ).values_list('sold_by_id', flat=True).distinct()
            agents_with_activity.update(clothing_agents)
        except Exception:
            pass
        
        # Check LiquorSale for agents
        try:
            from inventory.models_verticals import LiquorSale
            liquor_agents = LiquorSale.objects.filter(
                sold_at__gte=today_start,
                sold_at__lte=today_end,
                sold_by__isnull=False
            ).values_list('sold_by_id', flat=True).distinct()
            agents_with_activity.update(liquor_agents)
        except Exception:
            pass
        
        # Check PharmacySale for agents
        try:
            from inventory.models_pharmacy import PharmacySale
            pharmacy_agents = PharmacySale.objects.filter(
                sold_at__gte=today_start,
                sold_at__lte=today_end,
                sold_by__isnull=False
            ).values_list('sold_by_id', flat=True).distinct()
            agents_with_activity.update(pharmacy_agents)
        except Exception:
            pass
        
        # Check general Sale model for agents (uses module-level import - do NOT re-import inside function)
        try:
            general_agents = Sale.objects.filter(
                sold_at__gte=today_start,
                sold_at__lte=today_end,
                sold_by__isnull=False
            ).values_list('sold_by_id', flat=True).distinct()
            agents_with_activity.update(general_agents)
        except Exception:
            pass
        
        active_agents_today = len(agents_with_activity)
        
        # Count new agents who joined this week (last 7 days)
        week_ago = today_start - timedelta(days=7)
        try:
            new_agents_this_week = Membership.objects.filter(
                joined_at__gte=week_ago,
                role__iexact='AGENT'
            ).values('user_id').distinct().count()
        except Exception:
            # Fallback: try AgentProfile model
            try:
                from inventory.models import AgentProfile
                new_agents_this_week = AgentProfile.objects.filter(
                    joined_on__gte=week_ago.date()
                ).count()
            except Exception:
                pass
    except Exception:
        # Silently fail - these are bonus stats
        pass

    # ===== COMPUTE COSTS & PROFIT (Manager view) =====
    total_costs_period = Decimal("0.00")
    net_profit = period_sales_amount  # Default: profit = revenue (no costs)
    profit_margin = Decimal("100.00") if period_sales_amount > 0 else Decimal("0.00")
    costs_breakdown = {}

    if is_manager:
        try:
            from wallet.utils import compute_revenue_costs_profit

            # Compute costs and profit for the selected period
            period_start_date = period_start.date() if hasattr(period_start, 'date') else period_start
            period_end_date = period_end.date() if hasattr(period_end, 'date') else period_end

            metrics = compute_revenue_costs_profit(
                biz,
                period_sales_amount,
                period_start_date,
                period_end_date
            )

            total_costs_period = metrics.get('costs', Decimal("0.00"))
            net_profit = metrics.get('profit', period_sales_amount)
            profit_margin = metrics.get('profit_margin', Decimal("100.00"))
            costs_breakdown = metrics.get('costs_breakdown', {})
        except Exception:
            # Gracefully degrade if wallet app not available
            pass

    ctx = {
        "first_run": first_run,
        "products_count": products_count,
        "stock_count": stock_count,
        "warehouses_count": warehouses_count,
        "sales_count": sales_count,
        "kpis": kpis,
        "sold_mtd_count": sold_mtd_count,
        "staff_view": False,
        "vertical_kind": vertical_kind,
        "onboarding_steps": onboarding_steps,
        # Enhanced dashboard data
        "IS_MANAGER": is_manager,
        "greeting_text": _get_greeting(),
        "today_sales_amount": today_sales_amount,
        "today_sales_count": today_sales_count,
        "month_sales_amount": month_sales_amount,
        "month_sales_count": month_sales_count,
        "locations_count": locations_count,
        "agents_count": agents_count,
        "location_performance": location_performance,
        "agent_leaderboard": agent_leaderboard,
        # Agent-specific
        "agent_today_amount": agent_today_amount,
        "agent_today_count": agent_today_count,
        "agent_month_amount": agent_month_amount,
        "agent_month_count": agent_month_count,
        "agent_rank": agent_rank,
        "agent_gap": agent_gap,
        "agent_commission": agent_commission,
        # Optional namespace flags
        "HAS_REPORTS_NAMESPACE": has_reports_namespace,
        "show_payslip_banner": show_payslip_banner,
        # Date filter context (NEW)
        "active_range": active_range,
        "selected_date": selected_date,
        "date_param": date_param,
        # Costs & Profit (NEW)
        "total_costs_period": total_costs_period,
        "net_profit": net_profit,
        "profit_margin": profit_margin,
        "costs_breakdown": costs_breakdown,
        # Dynamic Stats (PREMIUM FEATURE)
        "active_businesses_today": active_businesses_today,
        "active_agents_today": active_agents_today,
        "new_agents_this_week": new_agents_this_week,
        **ctx_enhancements,  # Merge enhancements
    }

    # ===== MANAGER ONLY: Costs & Commissions Panel =====
    if is_manager:
        try:
            from dashboard.helpers_costs_commissions import get_month_to_date_costs_commissions
            costs_commissions_panel = get_month_to_date_costs_commissions(biz)
            ctx['costs_commissions_panel'] = costs_commissions_panel
        except Exception:
            pass

    # ===== BUSINESS HEALTH SCORE (manager view, lightweight card) =====
    if is_manager:
        try:
            from dashboard.services_health import calculate_business_health_score
            health_score = calculate_business_health_score(biz)
            ctx['health_score'] = health_score
        except Exception:
            ctx['health_score'] = None

        try:
            from dashboard.services_books_balance import run_daily_books_balance
            ctx["books_balance"] = run_daily_books_balance(biz)
        except Exception:
            ctx["books_balance"] = None

    ctx.setdefault("latest_notifications", [])
    
    # Inject dashboard enhancements and normalize context
    from core.dashboard_context import normalize_dashboard_context
    ctx = normalize_dashboard_context(request, ctx)

    return render(request, "dashboard/home.html", ctx)


# ---------------------------
# Staff/admin dashboard (global or per-tenant)
# ---------------------------
@login_required
@user_passes_test(_is_staff)
@otp_required  # Protect staff dashboard with OTP
def admin_dashboard(request):
    """
    Staff/admin dashboard.
    """
    tz = timezone.get_current_timezone()
    now = timezone.localtime()
    today = now.date()
    biz = getattr(request, "business", None)

    scope = request.GET.get("scope") or ("tenant" if biz is not None else "global")

    # Base querysets (scoped if tenant scope)
    if scope == "tenant" and biz is not None:
        sales_qs = _scope_queryset(Sale.objects.select_related("item", "agent"), biz)
        stock_qs = _scope_queryset(InventoryItem.objects.all(), biz)
        inv_kpis = business_metrics(request, include_agent_scope=False)
    else:
        sales_qs = Sale.objects.select_related("item", "agent").all()
        stock_qs = InventoryItem.objects.all()
        # Global: compute directly from qs (no request scope)
        qs_in = stock_qs.filter(IN_STOCK_Q())
        qs_sold = stock_qs.filter(SOLD_Q())
        inv_kpis = {
            "count_instock": qs_in.count(),
            "count_sold": qs_sold.count(),
            "sum_order": qs_in.aggregate(total=Sum("order_price"))["total"] or 0,
            "sum_selling": qs_sold.aggregate(total=Sum("sold_price"))["total"] or 0,
        }

    # Month window (tz-aware bounds)
    month_start = _start_of_day(today.replace(day=1), tz)
    month_end = _start_of_day(_first_of_next_month(today), tz)

    # KPIs with fallback if there are no Sale rows
    try:
        kpis = compute_sales_kpis(sales_qs, dt_field="sold_at", amount_field="price") or {}
    except Exception:
        kpis = {}
    if not kpis or (kpis.get("orders") in (0, None) and kpis.get("revenue") in (0, None)):
        sold_items = stock_qs.filter(SOLD_Q())
        mtd_qs = sold_items.filter(sold_at__gte=month_start, sold_at__lt=month_end)
        revenue = _inv_revenue_sum(mtd_qs)
        kpis = {"orders": mtd_qs.count(), "revenue": revenue,
                "scope": (biz.name if (scope == "tenant" and biz) else "All businesses")}
    else:
        kpis["scope"] = (biz.name if (scope == "tenant" and biz) else "All businesses")

    # In stock (canonical)
    in_stock_total = inv_kpis["count_instock"]

    # Sold (MTD) (canonical via InventoryItem)
    sold_mtd_count = (
        stock_qs.filter(SOLD_Q(), sold_at__gte=month_start, sold_at__lt=month_end)
        .count()
    )

    # Monthly profit (fallback to InventoryItem if Sale is empty)
    profit_expr = ExpressionWrapper(
        F("price") - F("item__order_price"),
        output_field=DecimalField(max_digits=14, decimal_places=2),
    )
    month_sales_qs = sales_qs.filter(sold_at__gte=month_start, sold_at__lt=month_end)
    monthly_profit = month_sales_qs.aggregate(p=Sum(profit_expr))["p"] or 0
    if monthly_profit == 0:
        monthly_profit = _inv_profit_sum(
            stock_qs.filter(SOLD_Q(), sold_at__gte=month_start, sold_at__lt=month_end)
        )

    # Global/tenant stock battery (simple heuristic)
    battery_max = 100
    battery_count = in_stock_total
    battery_pct = int(round(min(100, (battery_count / battery_max) * 100))) if battery_max else 0
    if battery_pct < 20:
        battery_label, battery_color = "Critical", "red"
    elif battery_pct < 60:
        battery_label, battery_color = "Low", "yellow"
    else:
        battery_label, battery_color = "Stable", "green"

    # Agents (clickable cards)
    User = get_user_model()
    if scope == "tenant" and biz is not None:
        agent_ids = set(month_sales_qs.values_list("agent_id", flat=True))
        try:
            assigned_ids = set(_scope_queryset(InventoryItem.objects.all(), biz)
                               .exclude(assigned_agent__isnull=True)
                               .values_list("assigned_agent_id", flat=True))
            agent_ids |= assigned_ids
        except Exception:
            pass
        agents_qs = User.objects.filter(id__in=[aid for aid in agent_ids if aid]).distinct()
        if not agents_qs.exists():
            agents_qs = User.objects.filter(groups__name="Agent").distinct()
    else:
        agents_qs = User.objects.filter(groups__name="Agent").distinct()
        if not agents_qs.exists():
            agents_qs = User.objects.filter(is_staff=False)

    agent_cards = []
    for a in agents_qs:
        a_mtd_qs = month_sales_qs.filter(agent=a)
        a_mtd_amount = a_mtd_qs.aggregate(t=Sum("price"))["t"] or 0
        a_mtd_count = a_mtd_qs.count()
        photo_url = getattr(getattr(a, "agent_profile", None), "photo_url", None)
        detail_url = _reverse_agent_detail(a.id)
        agent_cards.append({
            "id": a.id,
            "name": a.get_username(),
            "initials": _initials(a),
            "photo_url": photo_url,
            "mtd_amount": a_mtd_amount,
            "mtd_count": a_mtd_count,
            "url": detail_url,
        })

    # ===== NEW: Personalized dashboard enhancements for staff =====
    try:
        from dashboard.helpers_greetings import get_personalized_greeting
        from dashboard.helpers_payments import get_payment_mix_for_dashboard
        from dashboard.helpers_quotes import get_todays_quotes

        # Personalized greeting
        greeting_ctx = get_personalized_greeting(request.user, biz)

        # Brand header context
        brand_logo_url = None
        if biz and hasattr(biz, 'logo') and biz.logo:
            brand_logo_url = biz.logo.url

        # Payment mix (business-wide, last 30 days)
        payment_mix = get_payment_mix_for_dashboard(biz, period_days=30, user=None)

        # Daily quotes
        daily_quotes = get_todays_quotes(request.user, count=10)

        ctx_enhancements = {
            "DASHBOARD_GREETING": greeting_ctx.get("greeting"),
            "DASHBOARD_USER_NAME": greeting_ctx.get("user_name"),
            "DASHBOARD_SHOW_WELCOME": greeting_ctx.get("show_welcome"),
            "DASHBOARD_MILESTONE_MESSAGE": greeting_ctx.get("milestone"),
            "DASHBOARD_BRAND_LOGO_URL": brand_logo_url,
            "DASHBOARD_BRAND_TITLE": biz.name if biz else "Admin Dashboard",
            "PAYMENT_MIX": payment_mix,
            "PAYMENT_MIX_PERIOD": "Last 30 days",
            "DASHBOARD_QUOTES": daily_quotes,
        }
    except Exception:
        ctx_enhancements = {}

    ctx = {
        "kpis": kpis,
        "in_stock_total": in_stock_total,
        "sold_mtd_count": sold_mtd_count,
        "monthly_profit": monthly_profit,
        "battery": {"count": battery_count, "max": battery_max, "pct": battery_pct,
                    "label": battery_label, "color": battery_color},
        "agents": agent_cards,
        "staff_view": True,
        "scope": scope,
        **ctx_enhancements,
    }
    return render(request, "dashboard.html", ctx)


# ---------------------------
# Agent dashboard (tenant + per-agent)
# ---------------------------
@login_required
@require_business
def agent_dashboard(request):
    """
    Agent dashboard: per-agent KPIs + personal stock battery (within tenant if active).
    """
    biz = getattr(request, "business", None)

    my_sales_qs = Sale.objects.select_related("item")
    my_sales_qs = _scope_queryset(my_sales_qs, biz).filter(agent=request.user)
    try:
        kpis = compute_sales_kpis(my_sales_qs, dt_field="sold_at", amount_field="price") or {}
    except Exception:
        kpis = {}
    if not kpis:
        sold_items = (
            _scope_queryset(InventoryItem.objects.all(), biz)
            .filter(SOLD_Q(), assigned_agent=request.user)
        )
        revenue = _inv_revenue_sum(sold_items)
        kpis = {"orders": sold_items.count(), "revenue": revenue, "scope": "My sales"}
    else:
        kpis["scope"] = "My sales"

    my_stock_qs = _scope_queryset(InventoryItem.objects.all(), biz).filter(assigned_agent=request.user)
    my_in_stock = my_stock_qs.filter(IN_STOCK_Q()).count()

    battery_max = 20
    pct = int(round(min(100, (my_in_stock / battery_max) * 100))) if battery_max else 0
    if my_in_stock < 10:
        label, color = "Critical", "red"
    elif my_in_stock < 12:
        label, color = "Low", "yellow"
    else:
        label, color = "Stable", "green"

    wallet = _wallet_summary_for(request.user)

    # Agent Ranking & Milestones
    agent_ranking = None
    gamification_message = None
    current_milestone = None
    next_milestone = None
    try:
        from hq.utils_gamification import (
            get_agent_rank_for_user,
            get_gamification_message,
            get_current_milestone,
            get_next_milestone
        )
        from hq.utils_dates import get_month_range
        from django.utils import timezone

        if biz:
            # Get MTD date range
            today = timezone.now().date()
            month_start, month_end = get_month_range(today.year, today.month)

            # Get agent's ranking
            rank = get_agent_rank_for_user(
                user_id=request.user.id,
                business=biz,
                location=None,
                start_date=month_start,
                end_date=month_end
            )

            if rank:
                agent_ranking = rank
                gamification_message = get_gamification_message(rank)

                # Get milestones
                current_milestone = get_current_milestone(rank.sales_count)
                next_milestone = get_next_milestone(rank.sales_count)

                # Build agent ranking dict
                agent_ranking = {
                    "rank": rank.rank,
                    "sales_count": rank.sales_count,
                    "revenue": rank.revenue,
                    "behind_count": rank.behind_count,
                    "gamification_message": gamification_message,
                }

                # Format milestones
                if current_milestone:
                    threshold, name, emoji = current_milestone
                    agent_ranking["current_milestone"] = {
                        "name": name,
                        "emoji": emoji,
                        "threshold": threshold,
                    }

                if next_milestone:
                    threshold, name, emoji, sales_needed = next_milestone
                    agent_ranking["next_milestone"] = {
                        "name": name,
                        "emoji": emoji,
                        "threshold": threshold,
                        "sales_needed": sales_needed,
                    }
    except Exception as e:
        import logging
        log = logging.getLogger(__name__)
        log.exception("Failed to calculate agent ranking/milestones: %s", e)

    # ===== NEW: Personalized dashboard enhancements for agents =====
    try:
        from dashboard.helpers_greetings import get_personalized_greeting
        from dashboard.helpers_yesterday import get_yesterday_summary, should_show_yesterday_summary, mark_yesterday_summary_shown
        from dashboard.helpers_payments import get_payment_mix_for_dashboard
        from dashboard.helpers_quotes import get_todays_quotes

        # Personalized greeting
        greeting_ctx = get_personalized_greeting(request.user, biz)

        # Brand header context
        brand_logo_url = None
        if biz and hasattr(biz, 'logo') and biz.logo:
            brand_logo_url = biz.logo.url

        # Yesterday summary (agent-scoped would be future enhancement)
        yesterday_summary = None
        if should_show_yesterday_summary(request):
            yesterday_summary = get_yesterday_summary(request.user, biz)
            if yesterday_summary:
                mark_yesterday_summary_shown(request)

        # Payment mix (agent-scoped, last 30 days)
        payment_mix = get_payment_mix_for_dashboard(biz, period_days=30, user=request.user)

        # Daily quotes
        daily_quotes = get_todays_quotes(request.user, count=10)

        ctx_enhancements = {
            "DASHBOARD_GREETING": greeting_ctx.get("greeting"),
            "DASHBOARD_USER_NAME": greeting_ctx.get("user_name"),
            "DASHBOARD_SHOW_WELCOME": greeting_ctx.get("show_welcome"),
            "DASHBOARD_MILESTONE_MESSAGE": greeting_ctx.get("milestone"),
            "DASHBOARD_BRAND_LOGO_URL": brand_logo_url,
            "DASHBOARD_BRAND_TITLE": biz.name if biz else "Dashboard",
            "YESTERDAY_SUMMARY": yesterday_summary,
            "PAYMENT_MIX": payment_mix,
            "PAYMENT_MIX_PERIOD": "Last 30 days (your sales)",
            "DASHBOARD_QUOTES": daily_quotes,
        }
    except Exception:
        ctx_enhancements = {}

    ctx = {
        "kpis": kpis,
        "agent_battery": {"count": my_in_stock, "max": battery_max, "pct": pct, "label": label, "color": color},
        "wallet": wallet,
        "staff_view": False,
        "agent_ranking": agent_ranking,
        **ctx_enhancements,
    }
    return render(request, "dashboard.html", ctx)


@login_required
@user_passes_test(_is_staff)
@otp_required
def agent_detail(request, pk: int):
    """
    Staff-only page showing KPIs and stock battery for a specific agent.
    """
    biz = getattr(request, "business", None)
    User = get_user_model()
    agent = get_object_or_404(User, pk=pk)

    sales_qs = _scope_queryset(Sale.objects.select_related("item"), biz).filter(agent=agent)
    try:
        kpis = compute_sales_kpis(sales_qs, dt_field="sold_at", amount_field="price") or {}
    except Exception:
        kpis = {}
    if not kpis:
        sold_items = (
            _scope_queryset(InventoryItem.objects.all(), biz)
            .filter(SOLD_Q(), assigned_agent=agent)
        )
        revenue = _inv_revenue_sum(sold_items)
        kpis = {"orders": sold_items.count(), "revenue": revenue, "scope": f"{agent.get_username()}'s sales"}
    else:
        kpis["scope"] = f"{agent.get_username()}'s sales"

    in_stock_qs = _scope_queryset(InventoryItem.objects.all(), biz).filter(assigned_agent=agent)
    in_stock = in_stock_qs.filter(IN_STOCK_Q()).count()

    battery_max = 20
    pct = int(round(min(100, (in_stock / battery_max) * 100))) if battery_max else 0
    if in_stock < 10:
        label, color = "Critical", "red"
    elif in_stock < 12:
        label, color = "Low", "yellow"
    else:
        label, color = "Stable", "green"

    photo_url = getattr(getattr(agent, "agent_profile", None), "photo_url", None)
    wallet = _wallet_summary_for(agent)

    ctx = {
        "kpis": kpis,
        "agent_battery": {"count": in_stock, "max": battery_max, "pct": pct, "label": label, "color": color},
        "wallet": wallet,
        "staff_view": False,
        "view_agent": {
            "id": agent.id,
            "name": agent.get_username(),
            "initials": _initials(agent),
            "photo_url": photo_url,
        },
    }
    return render(request, "dashboard.html", ctx)


# ---------------------------
# ✅ Staff-only AI-CFO Panel (unchanged)
# ---------------------------
@login_required
@user_passes_test(_is_staff)
@otp_required
def cfo_panel(request):
    return render(
        request,
        "dashboard/cfo_panel.html",
        {
            "poll_ms": getattr(settings, "NOTIFICATIONS_POLL_MS", 15000),
            "api_prefix": "/api/v1",
        },
    )


# ---------------------------
# Chart data endpoints (tenant-aware)
# ---------------------------
@never_cache
@login_required
@require_GET
def profit_data(request):
    biz = getattr(request, "business", None)
    month_str = request.GET.get("month")
    group_by = request.GET.get("group_by")  # 'model' or None

    today = timezone.localdate()
    if month_str:
        anchor = datetime.strptime(month_str, "%Y-%m").date().replace(day=1)
    else:
        anchor = today.replace(day=1)

    base = _scope_queryset(Sale.objects.select_related("item__product"), biz)
    if not request.user.is_staff:
        base = base.filter(agent=request.user)

    profit_expr = ExpressionWrapper(
        F("price") - F("item__order_price"),
        output_field=DecimalField(max_digits=14, decimal_places=2),
    )

    if group_by == "model":
        start = anchor
        end = _first_of_next_month(anchor)
        qs = (base.filter(sold_at__date__gte=start, sold_at__date__lt=end)
                  .values("item__product__brand", "item__product__model")
                  .annotate(v=Sum(profit_expr))
                  .order_by("-v"))[:20]
        def _label(r):
            brand = (r.get("item__product__brand") or "").strip()
            model = (r.get("item__product__model") or "").strip()
            s = f"{brand} {model}".strip()
            return s or "Unknown model"
        labels = [_label(r) for r in qs]
        data = [float(r["v"] or 0) for r in qs]
    else:
        end = _first_of_next_month(anchor)
        start = (anchor.replace(day=1) - timedelta(days=365))
        qs = (base.filter(sold_at__date__gte=start, sold_at__date__lt=end)
                  .annotate(m=TruncMonth("sold_at"))
                  .values("m")
                  .annotate(v=Sum(profit_expr))
                  .order_by("m"))

        def add_month(y, m, delta):
            total = y * 12 + (m - 1) + delta
            return total // 12, total % 12 + 1

        sequence = []
        y, m = anchor.year, anchor.month
        for i in range(11, -1, -1):
            yy, mm = add_month(y, m, -i)
            sequence.append(f"{yy}-{mm:02d}")

        found = {r["m"].strftime("%Y-%m"): float(r["v"] or 0) for r in qs if r["m"]}
        labels = sequence
        data = [found.get(lbl, 0.0) for lbl in sequence]

    return JsonResponse({"labels": labels, "data": data})


@never_cache
@login_required
@require_GET
def agent_trend_data(request):
    biz = getattr(request, "business", None)
    months = int(request.GET.get("months", 6))
    metric = request.GET.get("metric", "sales")
    agent_id = request.GET.get("agent")

    base = _scope_queryset(Sale.objects.select_related("agent", "item"), biz)

    if request.user.is_staff:
        if agent_id:
            base = base.filter(agent_id=agent_id)
    else:
        base = base.filter(agent=request.user)

    start = (timezone.localdate().replace(day=1) - timedelta(days=31 * (months - 1)))
    base = base.filter(sold_at__date__gte=start)

    if metric == "profit":
        value = ExpressionWrapper(
            F("price") - F("item__order_price"),
            output_field=DecimalField(max_digits=14, decimal_places=2),
        )
        qs = (base.annotate(m=TruncMonth("sold_at"))
                  .values("m")
                  .annotate(v=Sum(value))
                  .order_by("m"))
    else:
        qs = (base.annotate(m=TruncMonth("sold_at"))
                  .values("m")
                  .annotate(v=Count("id"))
                  .order_by("m"))

    rows = list(qs)
    labels = [r["m"].strftime("%b %Y") for r in rows]
    data = [float(r["v"] or 0) for r in rows]
    return JsonResponse({"labels": labels, "data": data})


# =========================
# Append-only proxies (unchanged)
# =========================

def _inventory_dashboard_url() -> str:
    candidates = ("inventory:inventory_dashboard","inventory_dashboard","inventory:dashboard","inventory:home")
    for name in candidates:
        try:
            return reverse(name)
        except NoReverseMatch:
            continue
    prefix = getattr(settings, "FORCE_SCRIPT_NAME", "") or ""
    return f"{prefix}/inventory/dashboard/"


def _call_inventory_view(func_name, request):
    inv_views = import_module("inventory.views")
    func = getattr(inv_views, func_name)
    return func(request)


@never_cache
@login_required
def admin_dashboard_proxy(request):
    return HttpResponseRedirect(_inventory_dashboard_url())


@never_cache
@login_required
def agent_dashboard_proxy(request):
    return HttpResponseRedirect(_inventory_dashboard_url())


@never_cache
@login_required
@require_business
@require_GET
def v2_sales_trend_data_proxy(request):
    """
    Sales trend API for main dashboard - uses InventoryItem (same as KPIs).
    Returns {labels: [...], values: [...]} for Chart.js.
    """
    try:
        # Get business from request (set by @require_business decorator)
        business = getattr(request, "business", None)
        if not business:
            return JsonResponse({"labels": [], "values": []})

        # Parse period parameter (default 30d for "month")
        period_param = request.GET.get("period", "30d").lower()
        if period_param in ("month", "30d"):
            days = 30
        elif period_param in ("week", "7d"):
            days = 7
        elif period_param == "today":
            days = 1
        else:
            days = 30

        # Calculate date range
        tz = timezone.get_current_timezone()
        today = timezone.localdate()
        end_date = _start_of_day(today + timedelta(days=1), tz)
        start_date = _start_of_day(today - timedelta(days=days - 1), tz)

        # Query sold items using InventoryItem (same as KPIs)
        sold_items = (
            _scope_queryset(InventoryItem.objects.all(), business)
            .filter(SOLD_Q(), sold_at__gte=start_date, sold_at__lt=end_date)
        )

        # Group by date
        from django.db.models.functions import TruncDate
        daily_sales = (
            sold_items
            .annotate(sale_date=TruncDate('sold_at'))
            .values('sale_date')
            .annotate(
                qty=Count('id'),
                amount=Sum(F(_inv_price_field() or 'selling_price'), output_field=DecimalField(max_digits=14, decimal_places=2))
            )
            .order_by('sale_date')
        )

        # Build dict for quick lookup
        sales_by_date = {
            item['sale_date'].isoformat(): item
            for item in daily_sales
        }

        # Fill all dates in range (including zeros)
        labels = []
        values = []
        current = today - timedelta(days=days - 1)

        metric = request.GET.get("metric", "amount")

        for i in range(days):
            date_str = current.isoformat()
            labels.append(date_str)

            if date_str in sales_by_date:
                row = sales_by_date[date_str]
                if metric in ("count", "qty"):
                    values.append(int(row['qty'] or 0))
                else:  # amount
                    values.append(float(row['amount'] or 0))
            else:
                values.append(0)

            current += timedelta(days=1)

        return JsonResponse({"labels": labels, "values": values})

    except Exception as e:
        import logging
        logging.exception("Error in v2_sales_trend_data_proxy")
        return JsonResponse({"labels": [], "values": []})


@never_cache
@login_required
@require_business
@require_GET
def v2_top_models_data_proxy(request):
    """
    Top models API for main dashboard - uses InventoryItem (same as KPIs).
    Returns {labels: [...], values: [...]} for Chart.js.
    """
    try:
        # Get business from request (set by @require_business decorator)
        business = getattr(request, "business", None)
        if not business:
            return JsonResponse({"labels": [], "values": []})

        # Parse period parameter
        period_param = request.GET.get("period", "month").lower()
        if period_param == "today":
            days = 1
        elif period_param in ("week", "7d"):
            days = 7
        else:  # month/30d
            days = 30

        # Calculate date range
        tz = timezone.get_current_timezone()
        today = timezone.localdate()
        end_date = _start_of_day(today + timedelta(days=1), tz)
        start_date = _start_of_day(today - timedelta(days=days - 1), tz)

        # Query sold items by product/model
        sold_items = (
            _scope_queryset(InventoryItem.objects.select_related('product'), business)
            .filter(SOLD_Q(), sold_at__gte=start_date, sold_at__lt=end_date)
        )

        # Group by product name
        from django.db.models.functions import Coalesce
        top_models = (
            sold_items
            .annotate(
                model_name=Coalesce(
                    F('product__name'),
                    F('product__model'),
                    Value('Unknown'),
                    output_field=CharField()
                )
            )
            .values('model_name')
            .annotate(
                qty=Count('id'),
                amount=Sum(F(_inv_price_field() or 'selling_price'), output_field=DecimalField(max_digits=14, decimal_places=2))
            )
            .order_by('-qty')[:5]  # Top 5
        )

        labels = []
        values = []

        for item in top_models:
            labels.append(str(item['model_name'] or 'Unknown'))
            values.append(int(item['qty'] or 0))

        return JsonResponse({"labels": labels, "values": values})

    except Exception as e:
        import logging
        logging.exception("Error in v2_top_models_data_proxy")
        return JsonResponse({"labels": [], "values": []})


@never_cache
@login_required
@require_GET
def v2_profit_data_proxy(request):
    try:
        return _call_inventory_view("api_profit_bar", request)
    except Exception:
        return JsonResponse({"labels": [], "data": []})


@never_cache
@login_required
@require_GET
def v2_agent_trend_data_proxy(request):
    try:
        return _call_inventory_view("api_agent_trend", request)
    except Exception:
        return JsonResponse({"labels": [], "data": []})


@never_cache
@login_required
@require_GET
def v2_cash_overview_proxy(request):
    try:
        return _call_inventory_view("api_cash_overview", request)
    except Exception:
        today = timezone.localdate()
        return JsonResponse({
            "ok": True,
            "orders": 0,
            "revenue": 0.0,
            "paid_out": 0.0,
            "expenses": 0.0,
            "period_label": today.replace(day=1).strftime("%b %Y"),
        })


@never_cache
@login_required
@require_GET
def v2_recommendations_proxy(request):
    try:
        inv_api = import_module("inventory.api")
        fn = getattr(inv_api, "predictions_summary", None)
        if callable(fn):
            return fn(request)
    except Exception:
        pass

    try:
        return _call_inventory_view("api_predictions", request)
    except Exception:
        pass

    today = timezone.localdate()
    return JsonResponse({
        "ok": True,
        "overall": [{"date": (today + timedelta(days=i)).isoformat(),"predicted_units": 0,"predicted_revenue": 0.0} for i in range(1, 8)],
        "risky": [],
        "message": "recommendations stub",
    })


@never_cache
@login_required
@require_GET
def api_recommendations(request):
    u = request.user
    biz = getattr(request, "business", None)
    now = timezone.now()
    last_30 = now - timedelta(days=30)
    items = []

    try:
        my_in_stock = (
            _scope_queryset(InventoryItem.objects.all(), biz)
            .filter(assigned_agent=u)
            .filter(IN_STOCK_Q())
            .count()
        )
        if my_in_stock < 10:
            items.append({"message": f"Your stock is low ({my_in_stock}/20). Request replenishment.","confidence": 0.90})
        elif my_in_stock < 12:
            items.append({"message": f"Consider topping up: you have {my_in_stock}/20 units.","confidence": 0.65})
    except Exception:
        pass

    try:
        fields = {getattr(f, "name", None) for f in InventoryItem._meta.get_fields()}
        stale_cutoff = now - timedelta(days=14)
        stale_qs = _scope_queryset(InventoryItem.objects.all(), biz).filter(assigned_agent=u)
        # Use IN_STOCK_Q to ensure we probe true in-stock items
        stale_qs = stale_qs.filter(IN_STOCK_Q())
        if "updated_at" in fields:
            stale_qs = stale_qs.filter(updated_at__lt=stale_cutoff)
        elif "created_at" in fields:
            stale_qs = stale_qs.filter(created_at__lt=stale_cutoff)
        else:
            stale_qs = None
        if stale_qs is not None:
            stale_count = stale_qs.count()
            if stale_count:
                items.append({"message": f"{stale_count} items haven’t moved in 14+ days — consider promos/rotation.","confidence": 0.75})
    except Exception:
        pass

    try:
        label_key = None
        top = []
        try:
            top = (_scope_queryset(Sale.objects.all(), biz)
                   .filter(sold_at__gte=last_30)
                   .values("item__product__model")
                   .annotate(n=Count("id"))
                   .order_by("-n")[:3])
            label_key = "item__product__model"
        except Exception:
            pass
        if not top:
            try:
                top = (_scope_queryset(Sale.objects.all(), biz)
                       .filter(sold_at__gte=last_30)
                       .values("item__model")
                       .annotate(n=Count("id"))
                       .order_by("-n")[:3])
                label_key = "item__model"
            except Exception:
                pass
        if not top:
            try:
                top = (_scope_queryset(Sale.objects.all(), biz)
                       .filter(sold_at__gte=last_30)
                       .values("model")
                       .annotate(n=Count("id"))
                       .order_by("-n")[:3])
                label_key = "model"
            except Exception:
                pass

        for t in top:
            label = (t.get(label_key) or "Popular model")
            items.append({"message": f"Push {label}: {t['n']} sold in the last 30 days.","confidence": 0.60})
    except Exception:
        pass

    return JsonResponse({"success": True, "items": items}, status=200)


@never_cache
@require_GET
def dashboard_healthz_proxy(request):
    return JsonResponse({"ok": True, "time": timezone.now().isoformat()})


# ---------------------------------------------------------------------------
# Business Health Score — dashboard card view + full breakdown + API
# ---------------------------------------------------------------------------

@login_required
@require_business
@never_cache
def business_health_view(request):
    """
    Full Business Health Score breakdown page.
    URL: /dashboard/business-health/
    Scoped to request.business — no cross-tenant leakage.
    """
    from dashboard.services_health import calculate_business_health_score

    business = request.business
    health = calculate_business_health_score(business)

    return render(request, "dashboard/business_health.html", {
        "business": business,
        "health": health,
        "active_tab": "business_health",
        "show_search": False,
    })


@login_required
@require_business
@require_GET
def business_health_api(request):
    """
    JSON endpoint for Business Health Score.
    GET /dashboard/api/business-health/
    Returns the same structure as calculate_business_health_score, serialised.
    Scoped to request.business.
    """
    from dashboard.services_health import calculate_business_health_score
    from datetime import date as _date

    business = request.business
    health = calculate_business_health_score(business)

    # Serialise dates for JSON
    period = health.get("period", {})
    health_json = {
        **health,
        "period": {
            "start": period["start"].isoformat() if isinstance(period.get("start"), _date) else None,
            "end": period["end"].isoformat() if isinstance(period.get("end"), _date) else None,
        },
    }

    return JsonResponse(health_json)


# ---------------------------------------------------------------------------
# Daily Books Balance / Business Health Check
# ---------------------------------------------------------------------------

@login_required
@require_business
@never_cache
@require_http_methods(["GET", "POST"])
def books_balance_view(request):
    from dashboard.services_books_balance import books_balance_history, run_daily_books_balance

    business = request.business
    if request.method == "POST":
        check = run_daily_books_balance(business, force=True)
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse(
                {
                    "ok": True,
                    "status": check.status,
                    "score": check.score,
                    "variance": str(check.variance),
                    "recommendation": check.recommendation,
                }
            )
        return redirect("dashboard:books_balance")

    check = run_daily_books_balance(business)
    history = books_balance_history(business)
    return render(
        request,
        "dashboard/books_balance.html",
        {
            "business": business,
            "books_balance": check,
            "history": history,
            "active_tab": "books_balance",
            "show_search": False,
        },
    )


@login_required
@require_business
@never_cache
@require_http_methods(["POST"])
def books_balance_recalculate(request):
    from dashboard.services_books_balance import run_daily_books_balance

    check = run_daily_books_balance(request.business, force=True)
    return JsonResponse(
        {
            "ok": True,
            "status": check.status,
            "status_label": check.status_label,
            "score": check.score,
            "expected_value": str(check.expected_value),
            "actual_value": str(check.actual_value),
            "variance": str(check.variance),
            "recommendation": check.recommendation,
        }
    )


# ---------------------------------------------------------------------------
# Credit Score Views
# ---------------------------------------------------------------------------

@login_required
@require_business
def credit_scores_list(request):
    """
    Shows the active business's creditworthiness score.
    GET /dashboard/credit-scores/
    """
    from dashboard.services_credit import calculate_business_credit_score

    business = request.business
    credit = calculate_business_credit_score(business)
    return render(request, "dashboard/credit_scores.html", {
        "business": business,
        "credit": credit,
        "active_tab": "credit_scores",
        "show_search": False,
    })


@login_required
@require_business
def credit_score_detail(request, customer_phone: str):
    """
    Backward-compatible legacy route. Credit scoring is now business-level,
    so render the same business credit profile for the active business.
    GET /dashboard/credit-score/<customer_phone>/
    """
    from dashboard.services_credit import calculate_business_credit_score

    business = request.business
    credit = calculate_business_credit_score(business)
    return render(request, "dashboard/credit_scores.html", {
        "business": business,
        "credit": credit,
        "active_tab": "credit_scores",
        "show_search": False,
        "legacy_customer_phone": customer_phone,
    })


@login_required
@require_business
@require_GET
def credit_score_api(request, customer_phone: str):
    """
    Backward-compatible JSON endpoint. Returns business creditworthiness.
    GET /dashboard/api/credit-score/<customer_phone>/
    """
    from dashboard.services_credit import calculate_business_credit_score

    business = request.business
    credit = calculate_business_credit_score(business)
    credit["legacy_customer_phone"] = customer_phone
    return JsonResponse(credit)


@login_required
@require_business
@require_GET
def business_credit_score_api(request):
    from dashboard.services_credit import calculate_business_credit_score

    return JsonResponse(calculate_business_credit_score(request.business))


# ---------------------------------------------------------------------------
# Business OS Dashboard — Cross-Vertical Intelligence Layer (Phase 2)
# ---------------------------------------------------------------------------

@login_required
@require_business
def business_os_dashboard(request):
    """
    Unified Business OS dashboard showing cross-vertical analytics.
    Aggregates metrics from all active verticals for executive overview.
    """
    business = request.business

    try:
        from inventory.services.business_os import get_business_os_metrics
        metrics = get_business_os_metrics(business)
    except Exception:
        metrics = {"business": business, "verticals_active": [], "insights": [], "vertical_metrics": {}}

    ctx = {
        "business": business,
        **metrics,
    }
    return render(request, "dashboard/business_os.html", ctx)


# ---------------------------------------------------------------------------
# Recurring Costs — cross-vertical cost management
# ---------------------------------------------------------------------------

@login_required
@require_business
def recurring_costs_list(request):
    """Show and manage recurring costs for the active business."""
    from inventory.models import RecurringCost, RecurringCostCategory, RecurringCostFrequency
    from django.db.models import Sum

    business = request.business
    costs = RecurringCost.objects.filter(business=business)
    active = costs.filter(is_active=True)
    monthly_total = 0.0

    for c in active:
        amt = float(c.amount)
        if c.frequency == "monthly":
            monthly_total += amt
        elif c.frequency == "weekly":
            monthly_total += amt * 4.33
        elif c.frequency == "quarterly":
            monthly_total += amt / 3
        elif c.frequency == "annually":
            monthly_total += amt / 12

    by_category = {}
    for c in active:
        by_category[c.category] = by_category.get(c.category, 0) + float(c.amount)

    return render(request, "dashboard/recurring_costs.html", {
        "business": business,
        "costs": costs,
        "active_count": active.count(),
        "monthly_total": monthly_total,
        "by_category": by_category,
        "categories": RecurringCostCategory.choices,
        "frequencies": RecurringCostFrequency.choices,
    })


@login_required
@require_business
def recurring_cost_add(request):
    """Add a new recurring cost."""
    from inventory.models import RecurringCost, RecurringCostCategory, RecurringCostFrequency
    from django.utils import timezone as _tz
    import calendar

    business = request.business
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        category = request.POST.get("category", "other")
        amount = request.POST.get("amount", "0")
        frequency = request.POST.get("frequency", "monthly")
        notes = request.POST.get("notes", "").strip()

        try:
            from decimal import Decimal
            amt = Decimal(amount)
            if not name or amt <= 0:
                raise ValueError("Name and amount required")

            today = _tz.localdate()
            year, month = today.year, today.month
            if month == 12:
                year, month = year + 1, 1
            else:
                month += 1
            next_run = today.replace(day=1) if today.day > 1 else today
            next_run = next_run.replace(year=year, month=month, day=1)

            RecurringCost.objects.create(
                business=business,
                name=name,
                category=category,
                amount=amt,
                frequency=frequency,
                notes=notes,
                is_active=True,
                next_run_date=next_run,
                created_by=request.user,
            )
            from django.contrib import messages
            messages.success(request, f"'{name}' added as a recurring cost.")
            return redirect("dashboard:recurring_costs")
        except Exception as exc:
            from django.contrib import messages
            messages.error(request, f"Could not add cost: {exc}")

    return render(request, "dashboard/recurring_cost_form.html", {
        "business": business,
        "categories": RecurringCostCategory.choices,
        "frequencies": RecurringCostFrequency.choices,
        "editing": False,
    })


@login_required
@require_business
def recurring_cost_edit(request, pk: int):
    """Edit an existing recurring cost."""
    from inventory.models import RecurringCost, RecurringCostCategory, RecurringCostFrequency
    from django.shortcuts import get_object_or_404

    business = request.business
    cost = get_object_or_404(RecurringCost, pk=pk, business=business)

    if request.method == "POST":
        try:
            from decimal import Decimal
            cost.name = request.POST.get("name", cost.name).strip()
            cost.category = request.POST.get("category", cost.category)
            cost.amount = Decimal(request.POST.get("amount", str(cost.amount)))
            cost.frequency = request.POST.get("frequency", cost.frequency)
            cost.notes = request.POST.get("notes", cost.notes).strip()
            cost.save()
            from django.contrib import messages
            messages.success(request, f"'{cost.name}' updated.")
            return redirect("dashboard:recurring_costs")
        except Exception as exc:
            from django.contrib import messages
            messages.error(request, f"Could not update cost: {exc}")

    return render(request, "dashboard/recurring_cost_form.html", {
        "business": business,
        "cost": cost,
        "categories": RecurringCostCategory.choices,
        "frequencies": RecurringCostFrequency.choices,
        "editing": True,
    })


@login_required
@require_business
def recurring_cost_toggle(request, pk: int):
    """Toggle active/paused state of a recurring cost."""
    from inventory.models import RecurringCost
    from django.shortcuts import get_object_or_404
    from django.views.decorators.http import require_POST as _require_POST
    from django.contrib import messages

    business = request.business
    cost = get_object_or_404(RecurringCost, pk=pk, business=business)
    cost.is_active = not cost.is_active
    cost.save(update_fields=["is_active"])
    state = "resumed" if cost.is_active else "paused"
    messages.success(request, f"'{cost.name}' {state}.")
    return redirect("dashboard:recurring_costs")


@login_required
@require_business
def recurring_cost_delete(request, pk: int):
    """Delete a recurring cost."""
    from inventory.models import RecurringCost
    from django.shortcuts import get_object_or_404
    from django.contrib import messages

    business = request.business
    cost = get_object_or_404(RecurringCost, pk=pk, business=business)
    name = cost.name
    cost.delete()
    messages.success(request, f"'{name}' deleted.")
    return redirect("dashboard:recurring_costs")
