# layby/views.py
from __future__ import annotations

from decimal import Decimal
from typing import Any, Callable

import io
import random
from datetime import timedelta
from hashlib import md5
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.http import (
    FileResponse,
    HttpRequest,
    HttpResponse,
    HttpResponseBadRequest,
    Http404,
)
from django.middleware.csrf import get_token
from django.shortcuts import get_object_or_404, redirect
from django.template import TemplateDoesNotExist
from django.template.loader import get_template
from django.urls import NoReverseMatch, reverse
from django.utils import timezone
from django.utils.html import escape
from django.views.decorators.http import require_POST

from .forms import LaybyOrderForm
from .models import LaybyOrder

# Optional import for QR generation (pip install qrcode[pil])
try:
    import qrcode  # type: ignore
except Exception:  # pragma: no cover
    qrcode = None


# ---------------- helpers ----------------

def _agent_field_name() -> str | None:
    names = {f.name for f in LaybyOrder._meta.get_fields()}
    if "agent" in names:
        return "agent"
    if "created_by" in names:
        return "created_by"
    return None


def _money(x: Any, default: Decimal = Decimal("0.00")) -> Decimal:
    try:
        if x is None:
            return default
        if isinstance(x, Decimal):
            return x
        return Decimal(str(x))
    except Exception:
        return default


def _serialize_order(o: LaybyOrder) -> dict[str, Any]:
    """
    Robust serializer that tolerates different field names.
    Computes amount_paid (deposit + extra payments) and balance.
    """
    # Quantities / prices
    qty = getattr(o, "qty", 1) or 1
    unit = getattr(o, "unit_price", None)
    total = getattr(o, "total_price", None)
    if total is None and unit is not None:
        try:
            total = _money(unit) * int(qty)
        except Exception:
            total = Decimal("0.00")
    total = _money(total)

    # Deposit (either field)
    deposit = getattr(o, "deposit", None)
    if deposit is None:
        deposit = getattr(o, "deposit_amount", None)
    deposit = _money(deposit)

    # Extra payments via related manager
    paid_extra = Decimal("0.00")
    try:
        paid_extra = _money((o.payments.aggregate(s=Sum("amount")) or {}).get("s"))
    except Exception:
        pass

    amount_paid = deposit + paid_extra
    balance = max(total - amount_paid, Decimal("0.00"))

    # Product
    product = (
        getattr(o, "product_name", None)
        or getattr(o, "item_name", None)
        or getattr(o, "product", None)
        or ""
    )
    sku = getattr(o, "product_sku", None) or getattr(o, "sku", None) or ""
    ref = getattr(o, "ref", None) or getattr(o, "reference", "") or ""

    return {
        "id": o.pk,
        "ref": ref,
        "customer_name": getattr(o, "customer_name", "") or "",
        "customer_phone": getattr(o, "customer_phone", "") or "",
        "product": str(product),
        "sku": str(sku),
        "qty": qty,
        "total": total,
        "amount_paid": amount_paid,
        "balance": balance,
        "status": getattr(o, "status", "") or "",
        "term_months": getattr(o, "term_months", None),
    }


def _safe_reverse(name: str, default: str) -> str:
    try:
        return reverse(name)
    except NoReverseMatch:
        return default


def _render_or_inline(
    request: HttpRequest,
    template_name: str,
    context: dict[str, Any],
    inline_html_factory: Callable[[], str],
) -> HttpResponse:
    """
    Prefer project templates (extend base.html).
    If missing/broken, return an inline fallback.
    """
    try:
        t = get_template(template_name)
        return HttpResponse(t.render(context, request))
    except TemplateDoesNotExist:
        pass
    except Exception:
        # If template exists but errors, fail soft with inline.
        pass
    return HttpResponse(inline_html_factory())


# ---------- extra helpers for customer portal (history + messages) -----------

def _dt_as_str(obj) -> str:
    """
    Try several common timestamp fields and return 'YYYY-MM-DD HH:MM' local time.
    Works with objects that have attributes or dict-like access.
    """
    import datetime

    if not obj:
        return ""
    candidates = ["created_at", "timestamp", "time", "date", "sent_at", "received_at"]
    dt = None
    for k in candidates:
        try:
            v = getattr(obj, k) if hasattr(obj, k) else (obj.get(k) if isinstance(obj, dict) else None)
        except Exception:
            v = None
        if v:
            dt = v
            break
    if dt is None and isinstance(obj, (datetime.datetime, datetime.date)):
        dt = obj
    if dt is None:
        return ""
    if isinstance(dt, datetime.date) and not isinstance(dt, datetime.datetime):
        dt = datetime.datetime(dt.year, dt.month, dt.day, tzinfo=timezone.get_current_timezone())
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return timezone.localtime(dt).strftime("%Y-%m-%d %H:%M")


def _collect_payments(order_obj):
    """
    Return a list of dicts: [{amount, method, tx_ref, when}], tolerant to schema names.
    """
    items = []
    try:
        pmgr = getattr(order_obj, "payments", None)
        if pmgr is None:
            return items
        qs = pmgr.all()
        for p in qs:
            amt = _money(getattr(p, "amount", None))
            method = getattr(p, "method", "") or getattr(p, "channel", "") or ""
            txref = getattr(p, "tx_ref", "") or getattr(p, "reference", "") or ""
            when = _dt_as_str(p)
            items.append({"amount": amt, "method": method, "tx_ref": txref, "when": when})
    except Exception:
        pass
    items.sort(key=lambda x: x.get("when", ""), reverse=True)
    return items


def _collect_sms(order_obj):
    """
    Try to collect SMS/notification logs attached to this layby.
    Supported related names (optional): sms, messages, notifications, sms_logs
    Each item -> { body, when }
    """
    items = []
    rel_names = ["sms", "messages", "notifications", "sms_logs"]
    for rel in rel_names:
        try:
            mgr = getattr(order_obj, rel, None)
            if not mgr:
                continue
            for m in mgr.all():
                body = getattr(m, "body", "") or getattr(m, "message", "") or getattr(m, "text", "")
                when = _dt_as_str(m)
                if body:
                    items.append({"body": str(body), "when": when})
        except Exception:
            continue
    items.sort(key=lambda x: x.get("when", ""), reverse=True)
    return items


# ---------------- Agent views ----------------

@login_required
def agent_dashboard(request: HttpRequest) -> HttpResponse:
    field = _agent_field_name()
    qs = LaybyOrder.objects.all()
    if field:
        qs = qs.filter(**{field: request.user})
    qs = qs.order_by("-id")[:500]

    orders = [_serialize_order(o) for o in qs]
    total_balance = sum((o["balance"] for o in orders), Decimal("0"))

    def inline_html() -> str:
        # Fallback uses dark sidebar + light content
        new_url = _safe_reverse("layby:agent_new", "/layby/agent/new/")
        rows = (
            "\n".join(
                f"<tr>"
                f"<td>{o['id']}</td>"
                f"<td>{escape(o.get('ref') or '')}</td>"
                f"<td>{escape(o['customer_name'])}</td>"
                f"<td>{escape(o['product'])}</td>"
                f"<td>{escape(o['status'])}</td>"
                f"<td>{o['amount_paid']}</td>"
                f"<td>{o['balance']}</td>"
                f"</tr>"
                for o in orders
            )
            or "<tr><td colspan='7'>No laybys yet.</td></tr>"
        )

        return f"""
        <!-- INLINE FALLBACK: agent_dashboard -->
        <div style="display:flex;min-height:100vh;font-family:system-ui,Segoe UI,Inter,Roboto,Arial">
          <aside style="width:240px;background:#13315c;color:#e6eefc;padding:20px;position:sticky;top:0;height:100vh">
            <h2 style="margin:0 0 1rem">Circuit City</h2>
            <nav style="display:flex;flex-direction:column;gap:.6rem">
              <a href="/inventory/" style="color:#d7e3ff;text-decoration:none">Stock</a>
              <a href="/inventory/scan-in/" style="color:#d7e3ff;text-decoration:none">Scan IN</a>
              <a href="/wallet/" style="color:#d7e3ff;text-decoration:none">Wallet</a>
              <a href="/reports/" style="color:#d7e3ff;text-decoration:none">Reports</a>
              <div style="margin-top:1rem;color:#9fb7dd;font-size:.9rem">Layby</div>
              <a href="/layby/agent/" style="background:#1b3b6f;color:#fff;padding:.5rem .7rem;border-radius:.6rem;text-decoration:none">My Laybys</a>
              <a href="{new_url}" style="color:#d7e3ff;text-decoration:none">+ New layby</a>
            </nav>
          </aside>

          <main style="flex:1;padding:28px;background:#f6f8fc;color:#0b2545">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;gap:12px;flex-wrap:wrap">
              <h1 style="margin:0">My Laybys</h1>
              <a href="{new_url}" style="background:#16c784;color:#052e2b;padding:.6rem 1rem;border-radius:.7rem;text-decoration:none;font-weight:600">+ New layby</a>
            </div>

            <div style="background:#ffffff;border:1px solid #e5e9f2;border-radius:12px;padding:16px;margin-bottom:14px">
              <strong>Total outstanding balance:</strong> {total_balance}
            </div>

            <div style="background:#ffffff;border:1px solid #e5e9f2;border-radius:12px;overflow:auto">
              <table style="width:100%;border-collapse:collapse;min-width:780px">
                <thead style="background:#f2f5fb">
                  <tr>
                    <th style="text-align:left;padding:10px;border-bottom:1px solid #e5e9f2">ID</th>
                    <th style="text-align:left;padding:10px;border-bottom:1px solid #e5e9f2">Ref</th>
                    <th style="text-align:left;padding:10px;border-bottom:1px solid #e5e9f2">Customer</th>
                    <th style="text-align:left;padding:10px;border-bottom:1px solid #e5e9f2">Product</th>
                    <th style="text-align:left;padding:10px;border-bottom:1px solid #e5e9f2">Status</th>
                    <th style="text-align:left;padding:10px;border-bottom:1px solid #e5e9f2">Paid</th>
                    <th style="text-align:left;padding:10px;border-bottom:1px solid #e5e9f2">Balance</th>
                  </tr>
                </thead>
                <tbody>{rows}</tbody>
              </table>
            </div>
          </main>
        </div>
        """.strip()

    return _render_or_inline(
        request,
        "layby/agent_dashboard.html",
        {
            "orders": orders,
            "total_balance": total_balance,
            "header_title": "Layby",
            "active_nav": "layby",
            "show_layby_quick": False,
        },
        inline_html,
    )


@login_required
def agent_new(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        form = LaybyOrderForm(request.POST, request.FILES)
        if form.is_valid():
            order = form.save(user=request.user, commit=True)
            messages.success(request, f"Layby {escape(getattr(order, 'ref', '') or order.pk)} created.")
            return HttpResponse(
                '<meta http-equiv="refresh" content="0;url=/layby/agent/"/>',
                headers={"HX-Redirect": "/layby/agent/"},
            )
    else:
        form = LaybyOrderForm()

    def inline_html() -> str:
        list_url = _safe_reverse("layby:agent_dashboard", "/layby/agent/")
        csrf_token = escape(get_token(request))
        form_html = form.as_p()

        return f"""
        <!-- INLINE FALLBACK: agent_new -->
        <div style="display:flex;min-height:100vh;font-family:system-ui,Segoe UI,Inter,Roboto,Arial">
          <aside style="width:240px;background:#13315c;color:#e6eefc;padding:20px;position:sticky;top:0;height:100vh">
            <h2 style="margin:0 0 1rem">Circuit City</h2>
            <nav style="display:flex;flex-direction:column;gap:.6rem">
              <a href="/inventory/" style="color:#d7e3ff;text-decoration:none">Stock</a>
              <a href="/inventory/scan-in/" style="color:#d7e3ff;text-decoration:none">Scan IN</a>
              <a href="/wallet/" style="color:#d7e3ff;text-decoration:none">Wallet</a>
              <a href="/reports/" style="color:#d7e3ff;text-decoration:none">Reports</a>
              <div style="margin-top:1rem;color:#9fb7dd;font-size:.9rem">Layby</div>
              <a href="{list_url}" style="color:#d7e3ff;text-decoration:none">My Laybys</a>
              <a href="#" style="background:#1b3b6f;color:#fff;padding:.5rem .7rem;border-radius:.6rem;text-decoration:none">New layby</a>
            </nav>
          </aside>

          <main style="flex:1;padding:28px;background:#f6f8fc;color:#0b2545">
            <h1 style="margin:0 0 1rem">New Layby</h1>
            <form method="post" enctype="multipart/form-data" style="background:#ffffff;border:1px solid #e5e9f2;border-radius:12px;padding:16px;max-width:860px">
              <input type="hidden" name="csrfmiddlewaretoken" value="{csrf_token}">
              {form_html}
              <div style="margin-top:14px;display:flex;gap:8px;flex-wrap:wrap">
                <button type="submit" style="background:#16c784;color:#052e2b;padding:.6rem 1rem;border-radius:.7rem;border:none;font-weight:600">Save layby</button>
                <a href="{list_url}" style="color:#1f3b63;text-decoration:none;padding:.6rem 1rem;border-radius:.7rem;border:1px solid #e5e9f2;background:#fff">Cancel</a>
              </div>
            </form>
          </main>
        </div>
        """.strip()

    return _render_or_inline(
        request,
        "layby/agent_new.html",
        {
            "form": form,
            "header_title": "Layby",
            "active_nav": "layby",
            "show_layby_quick": False,
        },
        inline_html,
    )


# ---------------- Admin dashboard (customers + alerts + colors) ----------------

def _color_for(name: str) -> str:
    palette = ["#ffeb3b", "#03a9f4", "#8bc34a", "#e91e63", "#ff9800", "#9c27b0", "#00bcd4", "#cddc39"]
    if not name:
        return "#cccccc"
    h = md5(name.encode("utf-8")).hexdigest()
    idx = int(h[:2], 16) % len(palette)
    return palette[idx]


@staff_member_required
def admin_dashboard(request: HttpRequest) -> HttpResponse:
    qs = LaybyOrder.objects.all().order_by("-id")[:1000]
    orders = [_serialize_order(o) for o in qs]

    total_outstanding = sum((o["balance"] for o in orders), Decimal("0"))
    count_active = sum(1 for o in orders if (o.get("status") or "").lower() == "active")

    paid_this_week = Decimal("0.00")
    try:
        from .models import LaybyPayment  # type: ignore
        week_ago = timezone.now() - timedelta(days=7)
        if hasattr(LaybyPayment, "created_at"):
            paid_this_week = _money(LaybyPayment.objects.filter(created_at__gte=week_ago).aggregate(s=Sum("amount"))["s"])
        elif hasattr(LaybyPayment, "timestamp"):
            paid_this_week = _money(LaybyPayment.objects.filter(timestamp__gte=week_ago).aggregate(s=Sum("amount"))["s"])
        elif hasattr(LaybyPayment, "date"):
            paid_this_week = _money(LaybyPayment.objects.filter(date__gte=week_ago.date()).aggregate(s=Sum("amount"))["s"])
        else:
            paid_this_week = _money(LaybyPayment.objects.aggregate(s=Sum("amount"))["s"])
    except Exception:
        paid_this_week = Decimal("0.00")

    def inline_html() -> str:
        rows = (
            "\n".join(
                f"<tr>"
                f"<td>{o['id']}</td>"
                f"<td>{escape(o.get('ref') or '')}</td>"
                f"<td>"
                f"<a href='/layby/admin/customer/?{urlencode({'phone': o['customer_phone']})}' style='text-decoration:none'>"
                f"<span style='display:inline-block;padding:.2rem .55rem;border-radius:999px;border:1px solid #e5e9f2;background:{_color_for(o['customer_name'])};color:#052e2b;font-weight:900'>{escape(o['customer_name'])}</span>"
                f"</a>"
                f"</td>"
                f"<td>{escape(o['product'])}</td>"
                f"<td>{escape(o['status'])}</td>"
                f"<td>{o['amount_paid']}</td>"
                f"<td>{o['balance']}</td>"
                f"<td>{'Unpaid' if o['balance'] > 0 else ''}</td>"
                f"</tr>"
                for o in orders
            )
            or "<tr><td colspan='8'>No data.</td></tr>"
        )
        return f"""
        <!-- INLINE FALLBACK: admin_dashboard -->
        <div style="display:flex;min-height:100vh;font-family:system-ui,Segoe UI,Inter,Roboto,Arial">
          <aside style="width:240px;background:#13315c;color:#e6eefc;padding:20px;position:sticky;top:0;height:100vh">
            <h2 style="margin:0 0 1rem">Circuit City</h2>
            <nav style="display:flex;flex-direction:column;gap:.6rem">
              <a href="/layby/admin/dashboard/" style="background:#1b3b6f;color:#fff;padding:.5rem .7rem;border-radius:.6rem">Layby Dashboard</a>
            </nav>
          </aside>
          <main style="flex:1;padding:28px;background:#f6f8fc;color:#0b2545">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;gap:12px;flex-wrap:wrap">
              <h1 style="margin:0">Admin · Laybys</h1>
            </div>
            <div style="background:#ffffff;border:1px solid #e5e9f2;border-radius:12px;padding:16px;margin-bottom:14px">
              <strong>Total outstanding balance:</strong> {total_outstanding}
            </div>
            <div style="background:#ffffff;border:1px solid #e5e9f2;border-radius:12px;overflow:auto">
              <table style="width:100%;border-collapse:collapse;min-width:900px">
                <thead style="background:#f2f5fb">
                  <tr>
                    <th style="text-align:left;padding:10px;border-bottom:1px solid #e5e9f2">ID</th>
                    <th style="text-align:left;padding:10px;border-bottom:1px solid #e5e9f2">Ref</th>
                    <th style="text-align:left;padding:10px;border-bottom:1px solid #e5e9f2">Customer</th>
                    <th style="text-align:left;padding:10px;border-bottom:1px solid #e5e9f2">Product</th>
                    <th style="text-align:left;padding:10px;border-bottom:1px solid #e5e9f2">Status</th>
                    <th style="text-align:left;padding:10px;border-bottom:1px solid #e5e9f2">Paid</th>
                    <th style="text-align:left;padding:10px;border-bottom:1px solid #e5e9f2">Balance</th>
                    <th style="text-align:left;padding:10px;border-bottom:1px solid #e5e9f2">Alert</th>
                  </tr>
                </thead>
                <tbody>{rows}</tbody>
              </table>
            </div>
          </main>
        </div>
        """.strip()

    return _render_or_inline(
        request,
        "layby/admin/dashboard.html",
        {
            "orders": orders,
            "rows": orders,
            "total_outstanding": total_outstanding,
            "count_active": count_active,
            "paid_this_week": paid_this_week,
            "total_balance": total_outstanding,
            "color_for": _color_for,
            "header_title": "Admin · Laybys",
            "active_nav": "layby-admin",
            "show_layby_quick": False,
        },
        inline_html,
    )


# ---------------- Admin: customer detail ----------------

@staff_member_required
def admin_customer(request: HttpRequest) -> HttpResponse:
    phone = (request.GET.get("phone") or "").strip()
    name = (request.GET.get("name") or "").strip()

    if phone:
        qs = LaybyOrder.objects.filter(customer_phone=phone).order_by("-id")
    elif name:
        qs = LaybyOrder.objects.filter(customer_name=name).order_by("-id")
    else:
        messages.error(request, "Customer identifier required.")
        return redirect(_safe_reverse("layby:admin_dashboard", "/layby/admin/dashboard/"))

    orders_raw = list(qs)
    if not orders_raw:
        raise Http404("No laybys for this customer.")

    orders = [_serialize_order(o) for o in orders_raw]
    cust_name = orders[0]["customer_name"]
    cust_phone = orders[0]["customer_phone"]
    total = sum((o["total"] for o in orders), Decimal("0"))
    paid = sum((o["amount_paid"] for o in orders), Decimal("0"))
    balance = sum((o["balance"] for o in orders), Decimal("0"))

    def inline_html() -> str:
        rows = "\n".join(
            f"<tr>"
            f"<td>{o['id']}</td>"
            f"<td>{escape(o.get('ref') or '')}</td>"
            f"<td>{escape(o['product'])}</td>"
            f"<td>{escape(o['status'])}</td>"
            f"<td>{o['amount_paid']}</td>"
            f"<td>{o['balance']}</td>"
            f"</tr>"
            for o in orders
        )
        from_html = f"?{urlencode({'phone': cust_phone})}" if cust_phone else f"?{urlencode({'name': cust_name})}"
        return f"""
        <!-- INLINE FALLBACK: admin_customer -->
        <div style="display:flex;min-height:100vh;font-family:system-ui,Segoe UI,Inter,Roboto,Arial">
          <aside style="width:240px;background:#13315c;color:#e6eefc;padding:20px;position:sticky;top:0;height:100vh">
            <h2 style="margin:0 0 1rem">Circuit City</h2>
            <nav style="display:flex;flex-direction:column;gap:.6rem">
              <a href="/layby/admin/dashboard/" style="color:#d7e3ff;text-decoration:none">← Back to Layby Dashboard</a>
              <a href="/layby/admin/customer/{from_html}" style="color:#9fb7dd;text-decoration:none">Refresh</a>
            </nav>
          </aside>
          <main style="flex:1;padding:28px;background:#f6f8fc;color:#0b2545">
            <h1 style="margin:0 0 .75rem">
              Customer · <span style="background:{_color_for(cust_name)};color:#052e2b;padding:.2rem .55rem;border-radius:999px">{escape(cust_name)}</span>
            </h1>
            <div style="opacity:.8;margin-bottom:10px">Phone: {escape(cust_phone)}</div>

            <div style="background:#ffffff;border:1px solid #e5e9f2;border-radius:12px;padding:14px;margin-bottom:14px">
              <strong>Totals</strong> — Total: {total} · Paid: {paid} · Balance: <strong>{balance}</strong>
            </div>

            <div style="background:#ffffff;border:1px solid #e5e9f2;border-radius:12px;overflow:auto">
              <table style="width:100%;border-collapse:collapse;min-width:760px">
                <thead style="background:#f2f5fb">
                  <tr>
                    <th style="text-align:left;padding:10px;border-bottom:1px solid #e5e9f2">ID</th>
                    <th style="text-align:left;padding:10px;border-bottom:1px solid #e5e9f2">Ref</th>
                    <th style="text-align:left;padding:10px;border-bottom:1px solid #e5e9f2">Product</th>
                    <th style="text-align:left;padding:10px;border-bottom:1px solid #e5e9f2">Status</th>
                    <th style="text-align:left;padding:10px;border-bottom:1px solid #e5e9f2">Paid</th>
                    <th style="text-align:left;padding:10px;border-bottom:1px solid #e5e9f2">Balance</th>
                  </tr>
                </thead>
                <tbody>{rows}</tbody>
              </table>
            </div>
          </main>
        </div>
        """.strip()

    return _render_or_inline(
        request,
        "layby/admin/customer.html",
        {
            "orders": orders,
            "items": orders,
            "cust_name": cust_name,
            "cust_phone": cust_phone,
            "customer_name": cust_name,
            "customer_phone": cust_phone,
            "total": total,
            "paid": paid,
            "balance": balance,
            "header_title": "Layby · Customer",
            "active_nav": "layby-admin",
            "show_layby_quick": False,
        },
        inline_html,
    )


# ---------------- Customer OTP flow ----------------

def customer_login(request: HttpRequest) -> HttpResponse:
    return _render_or_inline(
        request,
        "layby/customer_login.html",
        {"show_layby_quick": False},
        lambda: "<p>Customer login page missing template.</p>",
    )


@require_POST
def customer_send_otp(request: HttpRequest) -> HttpResponse:
    phone = (request.POST.get("phone") or "").strip()
    if not phone:
        messages.error(request, "Enter your phone number.")
        return redirect(_safe_reverse("layby:customer_login", "/layby/customer/login/"))

    otp = f"{random.randint(0, 9999):04d}"
    request.session["layby_otp_phone"] = phone
    request.session["layby_otp_code"] = otp

    messages.info(request, "We SMSed you a 4-digit code.")

    return _render_or_inline(
        request,
        "layby/customer_verify.html",
        {"phone": phone, "otp_dev": otp if settings.DEBUG else None, "show_layby_quick": False},
        lambda: f"<p>Enter the code we sent to {escape(phone)}. (DEV OTP: {otp})</p>",
    )


@require_POST
def customer_verify_otp(request: HttpRequest) -> HttpResponse:
    phone = (request.POST.get("phone") or "").strip()
    code = (request.POST.get("otp") or request.POST.get("otp_fallback") or "").strip()

    sess_phone = request.session.get("layby_otp_phone")
    sess_code = request.session.get("layby_otp_code")

    if not (phone and code and sess_phone == phone and sess_code == code):
        messages.error(request, "Incorrect or expired code. Please try again.")
        return _render_or_inline(
            request,
            "layby/customer_verify.html",
            {"phone": phone, "show_layby_quick": False},
            lambda: "<p>Verification failed.</p>",
        )

    request.session.pop("layby_otp_code", None)
    return redirect(_safe_reverse("layby:customer_portal", f"/layby/portal/?{urlencode({'phone': phone})}"))


def customer_portal(request: HttpRequest) -> HttpResponse:
    phone = (request.GET.get("phone") or request.session.get("layby_otp_phone") or "").strip()
    qs = LaybyOrder.objects.filter(customer_phone=phone).order_by("-id") if phone else LaybyOrder.objects.none()

    # Build rich objects for the template: each entry has 'o' (serialized),
    # plus 'payments' and 'sms' lists.
    orders_data = []
    for obj in qs:
        ser = _serialize_order(obj)
        orders_data.append(
            {
                "o": ser,
                "payments": _collect_payments(obj),
                "sms": _collect_sms(obj),
            }
        )

    # Compute display name for the friendly greeting
    display_name = ""
    if orders_data:
        display_name = orders_data[0]["o"].get("customer_name") or ""

    return _render_or_inline(
        request,
        "layby/customer_portal.html",
        {
            "orders_data": orders_data,
            "orders": [x["o"] for x in orders_data],  # backwards compat in template
            "customer_phone": phone,
            "display_name": display_name,  # <-- use this in the template for “Welcome, Tessa”
            "show_layby_quick": False,
        },
        lambda: "<p>Customer portal missing template.</p>",
    )


# ---------------- Pay Now (QR + deep link) ----------------

@login_required
def pay_now(request: HttpRequest, order_id: int) -> HttpResponse:
    order = get_object_or_404(LaybyOrder, pk=order_id)
    ser = _serialize_order(order)
    deeplink = f"circuitpay://pay?ref=LAYBY-{order.pk}&amount={ser['balance']}&label={escape(ser['product'])}"
    return _render_or_inline(
        request,
        "layby/pay_now.html",
        {"order": order, "ser": ser, "deeplink": deeplink, "show_layby_quick": False},
        lambda: f"<p>Pay {ser['balance']} for {escape(ser['product'])}. Ref LAYBY-{order.pk}</p>",
    )


@login_required
def qr_png(request: HttpRequest, order_id: int) -> HttpResponse:
    order = get_object_or_404(LaybyOrder, pk=order_id)
    ser = _serialize_order(order)
    payload = f"REF=LAYBY-{order.pk};AMOUNT={ser['balance']};DESC={ser['product']}"
    if not qrcode:  # pragma: no cover
        return HttpResponseBadRequest("QR generation library not installed.")
    img = qrcode.make(payload)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return FileResponse(buf, content_type="image/png")


# ---------------- Agent: Add Payment ----------------
from django import forms
from .models import LaybyPayment  # type: ignore


class LaybyPaymentForm(forms.ModelForm):
    class Meta:
        model = LaybyPayment
        fields = ["amount", "method", "tx_ref"]
        widgets = {
            "amount": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0.01"}),
            "method": forms.TextInput(attrs={"class": "form-control", "placeholder": "cash / card / mobile"}),
            "tx_ref": forms.TextInput(attrs={"class": "form-control", "placeholder": "Provider reference (optional)"}),
        }


@login_required
def agent_add_payment(request: HttpRequest, order_id: int) -> HttpResponse:
    order = get_object_or_404(LaybyOrder, pk=order_id)

    if request.method == "POST":
        form = LaybyPaymentForm(request.POST)
        if form.is_valid():
            pay: LaybyPayment = form.save(commit=False)  # type: ignore[name-defined]
            pay.order = order
            if hasattr(pay, "received_by") and request.user.is_authenticated:
                pay.received_by = request.user  # type: ignore[assignment]
            pay.save()
            messages.success(request, "Payment recorded.")
            return redirect(_safe_reverse("layby:agent_dashboard", "/layby/agent/"))
    else:
        form = LaybyPaymentForm()

    return _render_or_inline(
        request,
        "layby/agent_add_payment.html",
        {"order": order, "form": form, "show_layby_quick": False},
        lambda: "<p>Add payment form missing template.</p>",
    )
