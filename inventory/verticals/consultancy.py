# inventory/verticals/consultancy.py
"""
Consultancy & Services vertical — views.

Supports: consultants, developers, agencies, tutors, repair shops, advisors.
Core flow: Client → Project → Quote → Invoice → Payment
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction as db_transaction
from django.db.models import Count, DecimalField, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from inventory.helpers import get_active_business
from inventory.models_consultancy import (
    ConsultancyClient,
    ConsultancyExpense,
    ConsultancyInvoice,
    ConsultancyInvoiceItem,
    ConsultancyPayment,
    ConsultancyProject,
    ConsultancyQuote,
    ConsultancyQuoteItem,
    ProjectStatus,
)
from tenants.utils import require_business

_DEC = DecimalField(max_digits=16, decimal_places=2)
_ZERO = Decimal("0.00")


def _coalesce(qs, field: str) -> Decimal:
    val = qs.aggregate(total=Coalesce(Sum(field), Value(0), output_field=_DEC))["total"]
    return Decimal(str(val or 0))


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@login_required
@require_business
def dashboard(request):
    business = get_active_business(request)
    today = timezone.localdate()
    month_start = today.replace(day=1)

    invoices_qs = ConsultancyInvoice.objects.filter(business=business, is_void=False)
    projects_qs = ConsultancyProject.objects.filter(business=business, is_active=True)
    payments_qs = ConsultancyPayment.objects.filter(business=business)

    # Revenue this month
    month_payments = payments_qs.filter(paid_at__date__gte=month_start)
    month_revenue = _coalesce(month_payments, "amount")

    # Outstanding invoices
    outstanding_qs = invoices_qs.filter(status__in=["draft", "sent", "partial", "overdue"])
    outstanding_list = list(outstanding_qs.values("total_amount", "amount_paid"))
    outstanding_amount = sum(
        Decimal(str(i["total_amount"] or 0)) - Decimal(str(i["amount_paid"] or 0))
        for i in outstanding_list
    )

    # Overdue invoices
    overdue_qs = invoices_qs.filter(
        status="overdue",
    ) | invoices_qs.filter(
        due_date__lt=today,
        status__in=["sent", "partial", "draft"],
    )
    overdue_count = overdue_qs.count()

    # Active projects
    active_projects = projects_qs.filter(
        status__in=[ProjectStatus.IN_PROGRESS, ProjectStatus.APPROVED, ProjectStatus.QUOTED]
    ).count()

    # Total clients
    total_clients = ConsultancyClient.objects.filter(business=business, is_active=True).count()

    # Recent projects
    recent_projects = projects_qs.select_related("client").order_by("-created_at")[:5]

    # Recent invoices
    recent_invoices = invoices_qs.select_related("client").order_by("-issued_at")[:5]

    # Best client (most invoiced amount)
    best_client = None
    best_client_data = (
        invoices_qs.filter(is_void=False)
        .values("client__name", "client__company")
        .annotate(total=Coalesce(Sum("total_amount"), Value(0), output_field=_DEC))
        .order_by("-total")
        .first()
    )
    if best_client_data:
        best_client = {
            "name": best_client_data.get("client__company") or best_client_data.get("client__name", ""),
            "total": best_client_data.get("total", _ZERO),
        }

    # Gamification badges
    badges = _compute_badges(
        business, invoices_qs, projects_qs, payments_qs, today, outstanding_amount
    )

    # Expenses this month
    month_expenses = _coalesce(
        ConsultancyExpense.objects.filter(business=business, expense_date__gte=month_start),
        "amount",
    )

    ctx = {
        "business": business,
        "active_tab": "dashboard",
        "today": today,
        "month_revenue": month_revenue,
        "outstanding_amount": outstanding_amount,
        "overdue_count": overdue_count,
        "active_projects": active_projects,
        "total_clients": total_clients,
        "recent_projects": recent_projects,
        "recent_invoices": recent_invoices,
        "best_client": best_client,
        "badges": badges,
        "month_expenses": month_expenses,
    }
    return render(request, "verticals/consultancy/dashboard.html", ctx)


def _compute_badges(
    business, invoices_qs, projects_qs, payments_qs, today, outstanding_amount
) -> list[dict]:
    badges = []

    # Zero Overdue Hero
    overdue_invoices = invoices_qs.filter(
        Q(status="overdue") | Q(due_date__lt=today, status__in=["sent", "partial"])
    ).count()
    if overdue_invoices == 0 and invoices_qs.count() > 0:
        badges.append({
            "name": "Zero Overdue Hero",
            "icon": "bi-check-circle-fill",
            "color": "success",
            "description": "No overdue invoices",
        })

    # Invoice Closer: paid invoices this month
    month_start = today.replace(day=1)
    paid_this_month = invoices_qs.filter(status="paid", updated_at__date__gte=month_start).count()
    if paid_this_month >= 1:
        badges.append({
            "name": "Invoice Closer",
            "icon": "bi-receipt",
            "color": "warning",
            "description": f"{paid_this_month} invoice(s) closed this month",
        })

    # Client Builder
    total_clients = ConsultancyClient.objects.filter(business=business, is_active=True).count()
    if total_clients >= 3:
        badges.append({
            "name": "Client Builder",
            "icon": "bi-people-fill",
            "color": "info",
            "description": f"{total_clients} active clients",
        })

    # Delivery Champion: projects delivered
    delivered = projects_qs.filter(status=ProjectStatus.DELIVERED).count()
    if delivered >= 1:
        badges.append({
            "name": "Delivery Champion",
            "icon": "bi-trophy-fill",
            "color": "primary",
            "description": f"{delivered} project(s) delivered",
        })

    # Retainer King
    retainers = projects_qs.filter(project_type="retainer", status=ProjectStatus.IN_PROGRESS).count()
    if retainers >= 1:
        badges.append({
            "name": "Retainer King",
            "icon": "bi-arrow-repeat",
            "color": "secondary",
            "description": f"{retainers} active retainer(s)",
        })

    return badges


# ---------------------------------------------------------------------------
# Clients
# ---------------------------------------------------------------------------

@login_required
@require_business
def clients_list(request):
    business = get_active_business(request)

    if request.method == "POST":
        try:
            ConsultancyClient.objects.create(
                business=business,
                name=request.POST.get("name", "").strip(),
                company=request.POST.get("company", "").strip(),
                email=request.POST.get("email", "").strip(),
                phone=request.POST.get("phone", "").strip(),
                address=request.POST.get("address", "").strip(),
                notes=request.POST.get("notes", "").strip(),
                created_by=request.user,
            )
            messages.success(request, "Client added.")
            return redirect("consultancy:clients")
        except Exception as exc:
            messages.error(request, f"Error: {exc}")

    clients = ConsultancyClient.objects.filter(
        business=business, is_active=True
    ).order_by("name")

    ctx = {
        "business": business,
        "active_tab": "clients",
        "clients": clients,
    }
    return render(request, "verticals/consultancy/clients.html", ctx)


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------

@login_required
@require_business
def projects_list(request):
    business = get_active_business(request)

    status_filter = request.GET.get("status", "")
    client_filter = request.GET.get("client_id", "")

    qs = ConsultancyProject.objects.filter(
        business=business, is_active=True
    ).select_related("client")

    if status_filter:
        qs = qs.filter(status=status_filter)
    if client_filter:
        qs = qs.filter(client_id=client_filter)

    clients = ConsultancyClient.objects.filter(business=business, is_active=True)

    ctx = {
        "business": business,
        "active_tab": "projects",
        "projects": qs.order_by("-created_at"),
        "status_choices": ProjectStatus.choices,
        "clients": clients,
        "status_filter": status_filter,
    }
    return render(request, "verticals/consultancy/projects.html", ctx)


@login_required
@require_business
def project_add(request):
    business = get_active_business(request)
    clients = ConsultancyClient.objects.filter(business=business, is_active=True)

    if request.method == "POST":
        try:
            client = get_object_or_404(
                ConsultancyClient, pk=request.POST.get("client_id"), business=business
            )
            agreed_value_str = request.POST.get("agreed_value", "").replace(",", "").strip()
            monthly_retainer_str = request.POST.get("monthly_retainer", "").replace(",", "").strip()

            ConsultancyProject.objects.create(
                business=business,
                client=client,
                title=request.POST.get("title", "").strip(),
                description=request.POST.get("description", "").strip(),
                project_type=request.POST.get("project_type", "project"),
                status=request.POST.get("status", ProjectStatus.LEAD),
                start_date=request.POST.get("start_date") or None,
                deadline=request.POST.get("deadline") or None,
                agreed_value=Decimal(agreed_value_str) if agreed_value_str else None,
                monthly_retainer=Decimal(monthly_retainer_str) if monthly_retainer_str else None,
                notes=request.POST.get("notes", "").strip(),
                created_by=request.user,
            )
            messages.success(request, "Project added.")
            return redirect("consultancy:projects")
        except Exception as exc:
            messages.error(request, f"Error: {exc}")

    # Pre-select client if provided
    preselect_client_id = request.GET.get("client_id")

    ctx = {
        "business": business,
        "active_tab": "projects",
        "clients": clients,
        "status_choices": ProjectStatus.choices,
        "type_choices": ConsultancyProject._meta.get_field("project_type").choices,
        "preselect_client_id": preselect_client_id,
    }
    return render(request, "verticals/consultancy/project_add.html", ctx)


@login_required
@require_business
def project_detail(request, project_id):
    business = get_active_business(request)
    project = get_object_or_404(ConsultancyProject, pk=project_id, business=business)

    if request.method == "POST":
        action = request.POST.get("action", "")
        if action == "update_status":
            project.status = request.POST.get("status", project.status)
            project.save(update_fields=["status"])
            messages.success(request, f"Status updated to {project.get_status_display()}.")
            return redirect("consultancy:project_detail", project_id=project_id)

    invoices = project.invoices.filter(is_void=False).order_by("-issued_at")
    quotes = project.quotes.order_by("-created_at")

    ctx = {
        "business": business,
        "active_tab": "projects",
        "project": project,
        "invoices": invoices,
        "quotes": quotes,
        "status_choices": ProjectStatus.choices,
    }
    return render(request, "verticals/consultancy/project_detail.html", ctx)


# ---------------------------------------------------------------------------
# Quotes
# ---------------------------------------------------------------------------

@login_required
@require_business
def quotes_list(request):
    business = get_active_business(request)
    quotes = ConsultancyQuote.objects.filter(business=business).select_related(
        "client", "project"
    ).order_by("-created_at")

    ctx = {
        "business": business,
        "active_tab": "quotes",
        "quotes": quotes,
    }
    return render(request, "verticals/consultancy/quotes.html", ctx)


@login_required
@require_business
def quote_create(request):
    business = get_active_business(request)
    clients = ConsultancyClient.objects.filter(business=business, is_active=True)

    if request.method == "POST":
        try:
            with db_transaction.atomic():
                client = get_object_or_404(
                    ConsultancyClient, pk=request.POST.get("client_id"), business=business
                )
                project_id = request.POST.get("project_id") or None
                project = None
                if project_id:
                    project = ConsultancyProject.objects.filter(
                        pk=project_id, business=business
                    ).first()

                # Line items
                descriptions = request.POST.getlist("item_description")
                quantities = request.POST.getlist("item_quantity")
                unit_prices = request.POST.getlist("item_unit_price")

                subtotal = Decimal("0")
                items_data = []
                for desc, qty_s, price_s in zip(descriptions, quantities, unit_prices):
                    if not desc.strip():
                        continue
                    qty = Decimal(qty_s.replace(",", "") or "1")
                    price = Decimal(price_s.replace(",", "") or "0")
                    line_total = qty * price
                    subtotal += line_total
                    items_data.append((desc.strip(), qty, price, line_total))

                discount = Decimal(request.POST.get("discount", "0").replace(",", "") or "0")
                tax = Decimal(request.POST.get("tax", "0").replace(",", "") or "0")

                quote = ConsultancyQuote.objects.create(
                    business=business,
                    client=client,
                    project=project,
                    title=request.POST.get("title", "").strip() or f"Quote for {client.name}",
                    description=request.POST.get("description", "").strip(),
                    subtotal=subtotal,
                    discount=discount,
                    tax=tax,
                    total_amount=subtotal - discount + tax,
                    status="draft",
                    valid_until=request.POST.get("valid_until") or None,
                    notes=request.POST.get("notes", "").strip(),
                    created_by=request.user,
                )
                for i, (desc, qty, price, total) in enumerate(items_data):
                    ConsultancyQuoteItem.objects.create(
                        quote=quote,
                        description=desc,
                        quantity=qty,
                        unit_price=price,
                        total=total,
                        sort_order=i,
                    )

                # Update project status if provided
                if project and project.status == ProjectStatus.LEAD:
                    project.status = ProjectStatus.QUOTED
                    project.save(update_fields=["status"])

                messages.success(request, f"Quote #{quote.quote_number} created.")
                return redirect("consultancy:quote_detail", quote_id=quote.pk)
        except Exception as exc:
            messages.error(request, f"Error: {exc}")

    preselect_client_id = request.GET.get("client_id")
    preselect_project_id = request.GET.get("project_id")

    ctx = {
        "business": business,
        "active_tab": "quotes",
        "clients": clients,
        "preselect_client_id": preselect_client_id,
        "preselect_project_id": preselect_project_id,
    }
    return render(request, "verticals/consultancy/quote_create.html", ctx)


@login_required
@require_business
def quote_detail(request, quote_id):
    business = get_active_business(request)
    quote = get_object_or_404(ConsultancyQuote, pk=quote_id, business=business)

    if request.method == "POST":
        action = request.POST.get("action", "")
        if action == "update_status":
            quote.status = request.POST.get("status", quote.status)
            quote.save(update_fields=["status"])
            # Update project
            if quote.project and quote.status == "accepted" and quote.project.status == ProjectStatus.QUOTED:
                quote.project.status = ProjectStatus.APPROVED
                quote.project.save(update_fields=["status"])
            messages.success(request, f"Quote status updated to {quote.get_status_display()}.")
        elif action == "convert_to_invoice":
            return redirect(
                f"{'/'.join(['', 'consultancy', 'invoices', 'create'])}/"
                f"?from_quote={quote.pk}"
            )
        return redirect("consultancy:quote_detail", quote_id=quote_id)

    ctx = {
        "business": business,
        "active_tab": "quotes",
        "quote": quote,
        "line_items": quote.line_items.all(),
        "status_choices": ConsultancyQuote._meta.get_field("status").choices,
    }
    return render(request, "verticals/consultancy/quote_detail.html", ctx)


# ---------------------------------------------------------------------------
# Invoices
# ---------------------------------------------------------------------------

@login_required
@require_business
def invoices_list(request):
    business = get_active_business(request)

    status_filter = request.GET.get("status", "")
    qs = ConsultancyInvoice.objects.filter(business=business, is_void=False).select_related(
        "client", "project"
    )
    if status_filter:
        qs = qs.filter(status=status_filter)

    total_outstanding = sum(
        max(Decimal("0"), inv.balance_due)
        for inv in qs.filter(status__in=["sent", "partial", "overdue", "draft"])
    )

    ctx = {
        "business": business,
        "active_tab": "invoices",
        "invoices": qs.order_by("-issued_at"),
        "total_outstanding": total_outstanding,
        "status_choices": ConsultancyInvoice._meta.get_field("status").choices,
        "status_filter": status_filter,
    }
    return render(request, "verticals/consultancy/invoices.html", ctx)


@login_required
@require_business
def invoice_create(request):
    business = get_active_business(request)
    clients = ConsultancyClient.objects.filter(business=business, is_active=True)

    # Pre-fill from quote if requested
    from_quote = None
    if request.method == "GET" and request.GET.get("from_quote"):
        try:
            from_quote = ConsultancyQuote.objects.get(
                pk=request.GET["from_quote"], business=business
            )
        except ConsultancyQuote.DoesNotExist:
            pass

    if request.method == "POST":
        try:
            with db_transaction.atomic():
                client = get_object_or_404(
                    ConsultancyClient, pk=request.POST.get("client_id"), business=business
                )
                project_id = request.POST.get("project_id") or None
                quote_id = request.POST.get("quote_id") or None
                project = None
                quote_obj = None
                if project_id:
                    project = ConsultancyProject.objects.filter(
                        pk=project_id, business=business
                    ).first()
                if quote_id:
                    quote_obj = ConsultancyQuote.objects.filter(
                        pk=quote_id, business=business
                    ).first()

                descriptions = request.POST.getlist("item_description")
                quantities = request.POST.getlist("item_quantity")
                unit_prices = request.POST.getlist("item_unit_price")

                subtotal = Decimal("0")
                items_data = []
                for desc, qty_s, price_s in zip(descriptions, quantities, unit_prices):
                    if not desc.strip():
                        continue
                    qty = Decimal(qty_s.replace(",", "") or "1")
                    price = Decimal(price_s.replace(",", "") or "0")
                    line_total = qty * price
                    subtotal += line_total
                    items_data.append((desc.strip(), qty, price, line_total))

                discount = Decimal(request.POST.get("discount", "0").replace(",", "") or "0")
                tax = Decimal(request.POST.get("tax", "0").replace(",", "") or "0")
                due_date = request.POST.get("due_date") or None

                invoice = ConsultancyInvoice.objects.create(
                    business=business,
                    client=client,
                    project=project,
                    quote=quote_obj,
                    title=request.POST.get("title", "").strip() or f"Invoice for {client.name}",
                    description=request.POST.get("description", "").strip(),
                    subtotal=subtotal,
                    discount=discount,
                    tax=tax,
                    total_amount=subtotal - discount + tax,
                    due_date=due_date,
                    status="draft",
                    notes=request.POST.get("notes", "").strip(),
                    created_by=request.user,
                )
                for i, (desc, qty, price, total) in enumerate(items_data):
                    ConsultancyInvoiceItem.objects.create(
                        invoice=invoice,
                        description=desc,
                        quantity=qty,
                        unit_price=price,
                        total=total,
                        sort_order=i,
                    )

                # Mark quote as having an invoice
                if quote_obj:
                    quote_obj.status = "accepted"
                    quote_obj.save(update_fields=["status"])

                messages.success(request, f"Invoice #{invoice.invoice_number} created.")
                return redirect("consultancy:invoice_detail", invoice_id=invoice.pk)
        except Exception as exc:
            messages.error(request, f"Error: {exc}")

    ctx = {
        "business": business,
        "active_tab": "invoices",
        "clients": clients,
        "from_quote": from_quote,
    }
    return render(request, "verticals/consultancy/invoice_create.html", ctx)


@login_required
@require_business
def invoice_detail(request, invoice_id):
    business = get_active_business(request)
    invoice = get_object_or_404(ConsultancyInvoice, pk=invoice_id, business=business)

    if request.method == "POST":
        action = request.POST.get("action", "")
        if action == "record_payment":
            try:
                amount = Decimal(request.POST.get("amount", "0").replace(",", ""))
                if amount <= 0:
                    messages.error(request, "Payment amount must be > 0.")
                else:
                    ConsultancyPayment.objects.create(
                        business=business,
                        invoice=invoice,
                        amount=amount,
                        payment_method=request.POST.get("payment_method", "cash"),
                        reference=request.POST.get("reference", "").strip(),
                        notes=request.POST.get("notes", "").strip(),
                        created_by=request.user,
                    )
                    messages.success(request, f"Payment of MWK {amount:,.0f} recorded.")
            except Exception as exc:
                messages.error(request, f"Error: {exc}")
        elif action == "mark_sent":
            if invoice.status == "draft":
                invoice.status = "sent"
                invoice.save(update_fields=["status"])
                messages.success(request, "Invoice marked as sent.")
        return redirect("consultancy:invoice_detail", invoice_id=invoice_id)

    payments = invoice.payments.order_by("-paid_at")
    payment_method_choices = ConsultancyPayment._meta.get_field("payment_method").choices

    ctx = {
        "business": business,
        "active_tab": "invoices",
        "invoice": invoice,
        "line_items": invoice.line_items.all(),
        "payments": payments,
        "payment_method_choices": payment_method_choices,
    }
    return render(request, "verticals/consultancy/invoice_detail.html", ctx)


# ---------------------------------------------------------------------------
# Expenses
# ---------------------------------------------------------------------------

@login_required
@require_business
def expenses(request):
    business = get_active_business(request)

    if request.method == "POST":
        try:
            project_id = request.POST.get("project_id") or None
            project = None
            if project_id:
                project = ConsultancyProject.objects.filter(
                    pk=project_id, business=business
                ).first()

            ConsultancyExpense.objects.create(
                business=business,
                project=project,
                category=request.POST.get("category", "other"),
                description=request.POST.get("description", "").strip(),
                amount=Decimal(request.POST.get("amount", "0").replace(",", "")),
                expense_date=request.POST.get("expense_date") or timezone.localdate(),
                notes=request.POST.get("notes", "").strip(),
                created_by=request.user,
            )
            messages.success(request, "Expense recorded.")
            return redirect("consultancy:expenses")
        except Exception as exc:
            messages.error(request, f"Error: {exc}")

    expense_qs = ConsultancyExpense.objects.filter(business=business)
    total_expenses = _coalesce(expense_qs, "amount")
    expense_list = expense_qs.select_related("project").order_by("-expense_date")[:100]
    projects = ConsultancyProject.objects.filter(business=business, is_active=True)

    ctx = {
        "business": business,
        "active_tab": "expenses",
        "expenses": expense_list,
        "total_expenses": total_expenses,
        "projects": projects,
        "category_choices": ConsultancyExpense._meta.get_field("category").choices,
    }
    return render(request, "verticals/consultancy/expenses.html", ctx)
