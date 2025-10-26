# inventory/views_docs.py
from __future__ import annotations
import csv, io
from datetime import datetime
from decimal import Decimal
from typing import List
from django.contrib.auth.decorators import login_required
from django.core.mail import EmailMessage
from django.http import HttpRequest, HttpResponse, JsonResponse, FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods, require_GET, require_POST
from django.template.loader import render_to_string
from django.utils import timezone

from .models_docs import Customer, Doc, DocLine

# -------- Helpers ----------
def _next_number(prefix: str) -> str:
    y = timezone.now().year
    base = f"{prefix}-{y}-"
    last = Doc.objects.filter(number__startswith=f"{prefix}-{y}-").order_by("number").last()
    next_seq = 1
    if last:
        try:
            next_seq = int(last.number.rsplit("-", 1)[-1]) + 1
        except Exception:
            pass
    return f"{base}{next_seq:05d}"

def _parse_lines(data) -> List[dict]:
    # Expect [{description, quantity, unit_price}]
    lines = []
    for row in (data or []):
        if not row: 
            continue
        desc = (row.get("description") or row.get("name") or "").strip()
        if not desc:
            continue
        qty = Decimal(str(row.get("quantity") or 1))
        price = Decimal(str(row.get("unit_price") or row.get("price") or 0))
        lines.append({"description": desc, "quantity": qty, "unit_price": price})
    return lines

# -------- Pages ----------
@login_required
@require_GET
def docs_list(request: HttpRequest):
    qs = Doc.objects.select_related("customer")
    q = (request.GET.get("q") or "").strip()
    dt_from = request.GET.get("from")
    dt_to = request.GET.get("to")
    if q:
        qs = qs.filter(number__icontains=q) | qs.filter(customer__name__icontains=q)
    if dt_from:
        qs = qs.filter(created_at__date__gte=dt_from)
    if dt_to:
        qs = qs.filter(created_at__date__lte=dt_to)
    return render(request, "inventory/docs_list.html", {"docs": qs[:200], "q": q, "from": dt_from, "to": dt_to})

@login_required
@require_http_methods(["GET", "POST"])
def doc_new(request: HttpRequest, kind: str):
    if kind not in (Doc.DOC_INVOICE, Doc.DOC_QUOTE):
        raise Http404()
    if request.method == "GET":
        return render(request, "inventory/doc_edit.html", {"kind": kind})
    # POST (JSON or form)
    data = request.POST or request.body
    if request.content_type and "json" in request.content_type:
        import json
        payload = json.loads(request.body.decode("utf-8") or "{}")
    else:
        # form-encoded quick add
        payload = {
            "customer": {
                "name": request.POST.get("customer_name"),
                "email": request.POST.get("customer_email"),
                "phone": request.POST.get("customer_phone"),
                "address": request.POST.get("customer_address"),
            },
            "tax_rate_pct": request.POST.get("tax_rate_pct") or 0,
            "lines": [{
                "description": request.POST.get("description"),
                "quantity": request.POST.get("quantity") or 1,
                "unit_price": request.POST.get("unit_price") or 0,
            }],
        }

    cust_data = payload.get("customer") or {}
    customer, _ = Customer.objects.get_or_create(
        name=(cust_data.get("name") or "Walk-in").strip()[:160],
        defaults={"email": cust_data.get("email", ""), "phone": cust_data.get("phone", ""), "address": cust_data.get("address", "")}
    )
    number = _next_number("INV" if kind == Doc.DOC_INVOICE else "QUO")
    doc = Doc.objects.create(
        doc_type=kind, number=number, customer=customer, created_by=request.user,
        tax_rate_pct=Decimal(str(payload.get("tax_rate_pct") or 0))
    )
    for row in _parse_lines(payload.get("lines")):
        DocLine.objects.create(doc=doc, **row)
    doc.recalc(commit=True)
    return JsonResponse({"ok": True, "id": doc.id, "number": doc.number, "detail_url": reverse("inventory:doc_detail", args=[doc.id])})

@login_required
@require_GET
def doc_detail(request: HttpRequest, pk: int):
    doc = get_object_or_404(Doc.objects.select_related("customer").prefetch_related("lines"), pk=pk)
    return render(request, "inventory/doc_detail.html", {"doc": doc})

# -------- Downloads ----------
@login_required
@require_GET
def doc_pdf(request: HttpRequest, pk: int):
    doc = get_object_or_404(Doc.objects.select_related("customer").prefetch_related("lines"), pk=pk)
    html = render_to_string("inventory/doc_print.html", {"doc": doc, "as_pdf": True})
    # Try WeasyPrint -> PDF. If missing, return HTML nicely.
    try:
        from weasyprint import HTML
        pdf = HTML(string=html, base_url=request.build_absolute_uri("/")).write_pdf()
        filename = f"{doc.number}.pdf"
        return HttpResponse(pdf, content_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{filename}"'})
    except Exception:
        return HttpResponse(html)  # graceful fallback

@login_required
@require_GET
def doc_excel(request: HttpRequest, pk: int):
    doc = get_object_or_404(Doc.objects.select_related("customer").prefetch_related("lines"), pk=pk)
    # Generate a simple CSV (universally openable in Excel). No external deps.
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow([doc.get_doc_type_display(), doc.number, doc.created_at.date(), doc.customer.name])
    w.writerow(["Description", "Qty", "Unit Price", "Line Total"])
    for li in doc.lines.all():
        w.writerow([li.description, li.quantity, f"{li.unit_price:.2f}", f"{li.line_total:.2f}"])
    w.writerow([])
    w.writerow(["Subtotal", "", "", f"{doc.subtotal:.2f}"])
    w.writerow(["Tax", "", "", f"{doc.tax:.2f}"])
    w.writerow(["Total", "", "", f"{doc.total:.2f}"])
    resp = HttpResponse(buf.getvalue(), content_type="text/csv")
    resp["Content-Disposition"] = f'attachment; filename="{doc.number}.csv"'
    return resp

# -------- Send (Email / WhatsApp) ----------
@login_required
@require_POST
def doc_email(request: HttpRequest, pk: int):
    doc = get_object_or_404(Doc, pk=pk)
    to = request.POST.get("to") or getattr(doc.customer, "email", "")
    if not to:
        return JsonResponse({"ok": False, "error": "No recipient email"})
    # Render PDF (or HTML fallback) into bytes
    html = render_to_string("inventory/doc_print.html", {"doc": doc, "as_pdf": True})
    filename = f"{doc.number}.pdf"
    content = None
    mimetype = "application/pdf"
    try:
        from weasyprint import HTML
        content = HTML(string=html, base_url=request.build_absolute_uri("/")).write_pdf()
    except Exception:
        content = html.encode("utf-8")
        mimetype = "text/html"
    subject = f"{doc.get_doc_type_display()} {doc.number}"
    body = f"Hi {doc.customer.name},\n\nPlease find attached {doc.get_doc_type_display().lower()} {doc.number}.\n\nRegards,"
    msg = EmailMessage(subject=subject, body=body, to=[to])
    msg.attach(filename, content, mimetype)
    sent = msg.send(fail_silently=True)
    if sent:
        doc.status = "sent"; doc.save(update_fields=["status"])
        return JsonResponse({"ok": True, "message": "Email sent"})
    return JsonResponse({"ok": False, "error": "Email failed"})

@login_required
@require_GET
def doc_whatsapp(request: HttpRequest, pk: int):
    doc = get_object_or_404(Doc, pk=pk)
    phone = request.GET.get("phone") or (doc.customer.phone or "")
    if not phone:
        return JsonResponse({"ok": False, "error": "No phone provided"})
    link = request.build_absolute_uri(reverse("inventory:doc_pdf", args=[doc.id]))
    text = f"{doc.get_doc_type_display()} {doc.number} ({doc.total:.2f} {doc.currency})\n{link}"
    # Open WhatsApp prefilled (works on mobile/desktop web)
    url = f"https://wa.me/{phone}?text=" + __import__("urllib.parse").parse.quote(text)
    return redirect(url)


