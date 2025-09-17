# billing/views_invoices.py
from __future__ import annotations
from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.template.loader import render_to_string

from .models import Invoice
from .utils_send import send_invoice_email, send_invoice_whatsapp


@login_required
def invoice_detail(request: HttpRequest, pk):
    inv = get_object_or_404(Invoice, pk=pk)
    # Very light perms: tenant isolation is already handled by your Tenant middleware
    return render(request, "billing/invoice.html", {"invoice": inv})


@login_required
def invoice_send(request: HttpRequest, pk):
    """
    POST with JSON: { "channels": ["email","whatsapp"], "email": "...", "phone": "..." }
    Falls back to invoice.manager_* if not provided.
    """
    if request.method != "POST":
        raise Http404()

    inv = get_object_or_404(Invoice, pk=pk)

    data = request.POST or request.GET  # allow form POST or quick tests
    channels = data.getlist("channels") if hasattr(data, "getlist") else (data.get("channels") or [])
    if isinstance(channels, str):
        channels = [c.strip() for c in channels.split(",") if c.strip()]

    # Fallbacks
    to_email = data.get("email") or inv.manager_email
    to_phone = data.get("phone") or inv.manager_whatsapp

    # Compose message bodies
    subject = f"Invoice {inv.number} — Total {inv.currency} {inv.total}"
    html = render_to_string("billing/email/invoice_email.html", {"invoice": inv})
    text = f"Invoice {inv.number}\nTotal: {inv.currency} {inv.total}\nDue: {inv.due_date or '-'}\n\nLog in to view details."

    results = []
    for ch in channels:
        ch = ch.lower().strip()
        if ch == "email":
            results.append(send_invoice_email(to_email=to_email, subject=subject, html_body=html, text_body=text))
        elif ch in ("whatsapp", "wa"):
            results.append(send_invoice_whatsapp(to_number=to_phone, text=text))
        else:
            results.append(dict(ok=False, channel=ch, detail="Unknown channel"))

    # Update status if we actually sent something
    if any(r.ok for r in results):
        if inv.status == Invoice.Status.DRAFT:
            inv.status = Invoice.Status.SENT
            inv.save(update_fields=["status", "updated_at"])

    payload = [{"ok": getattr(r, "ok", False), "channel": getattr(r, "channel", "?"), "detail": getattr(r, "detail", "")} for r in results]
    return JsonResponse({"invoice": str(inv.id), "results": payload})
