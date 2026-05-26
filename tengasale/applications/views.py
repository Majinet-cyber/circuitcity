from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from deals.models import DeviceDeal
from geography.models import Region

from .forms import CustomerDetailsForm, KYCForm, LocationNextOfKinForm, SignatureForm, WorkProofForm
from .models import FinancingApplication


ACTIVE_STATUSES = [
    "draft",
    "started",
    "customer_details",
    "device_selection",
    "kyc",
    "kyc_capture",
    "location_details",
    "work_details",
    "signature",
    "correction_requested",
    "submitted",
    "pending_review",
    "resubmitted",
    "under_review",
    "approved",
    "contract_terms",
    "contract_signature",
    "imei_entry",
    "contract_creating",
    "warranty_check",
    "locking",
    "deposit_pending",
    "imei_required",
]


def merchant_application(request, app_id):
    return get_object_or_404(FinancingApplication, id=app_id, created_by=request.user)


def user_can_view_application(user, app):
    return (
        app.created_by_id == user.id
        or app.claimed_by_id == user.id
        or user.is_staff
        or user.is_superuser
    )


def geography_json_data():
    data = {}
    regions = Region.objects.prefetch_related("districts__traditional_authorities").order_by("name")
    for region in regions:
        data[region.name] = {}
        for district in region.districts.all():
            data[region.name][district.name] = [ta.name for ta in district.traditional_authorities.all()]
    return data


@login_required
def new_application(request):
    app = FinancingApplication.objects.create(
        created_by=request.user,
        status="started",
    )
    return redirect("edit_customer_details", app_id=app.id)


@login_required
def edit_customer_details(request, app_id):
    app = merchant_application(request, app_id)

    if request.method == "POST":
        form = CustomerDetailsForm(request.POST, instance=app)
        if form.is_valid():
            app = form.save(commit=False)
            app.monthly_income = app.exact_monthly_income
            app.income_source = app.occupation
            app.status = "customer_details"
            app.save()
            return redirect("choose_device", app_id=app.id)
    else:
        form = CustomerDetailsForm(instance=app)

    return render(request, "applications/customer_details.html", {"app": app, "form": form})


@login_required
def choose_device(request, app_id):
    app = merchant_application(request, app_id)
    deals = DeviceDeal.objects.filter(is_active=True, brand__is_active=True).select_related("brand").order_by(
        "brand__name",
        "model_name",
        "specs",
    )
    deal_options = [
        {
            "id": deal.id,
            "brand": deal.brand.name,
            "model_name": deal.model_name,
            "specs": deal.specs,
            "min_cash_price": str(deal.min_cash_price),
            "max_cash_price": str(deal.max_cash_price),
            "default_cash_price": str(deal.default_cash_price),
            "deposit_percent": str(deal.deposit_percent),
            "loan_multiplier": str(deal.loan_multiplier),
            "term_months": deal.term_months,
        }
        for deal in deals
    ]
    brand_names = []
    for deal in deals:
        if deal.brand.name not in brand_names:
            brand_names.append(deal.brand.name)
    form_error = ""

    if request.method == "POST":
        deal_id = request.POST.get("deal_id")
        selected_cash_price_raw = request.POST.get("selected_cash_price")
        try:
            deal_pk = int(deal_id or "")
        except (TypeError, ValueError):
            deal_pk = None
        deal = deals.filter(id=deal_pk).first() if deal_pk else None

        if not deal:
            form_error = "Select an available device deal before continuing."
        else:
            try:
                selected_cash_price = Decimal(selected_cash_price_raw or deal.default_cash_price)
            except (InvalidOperation, TypeError):
                selected_cash_price = None

            if selected_cash_price is None:
                form_error = "Enter a valid cash price."
            elif selected_cash_price < deal.min_cash_price or selected_cash_price > deal.max_cash_price:
                form_error = "Cash price must stay within the selected deal price range."
            else:
                app.apply_deal_selection(deal, selected_cash_price)
                app.status = "device_selection"
                app.save(
                    update_fields=[
                        "deal",
                        "selected_cash_price",
                        "selected_deposit_percent",
                        "selected_loan_multiplier",
                        "calculated_total_loan",
                        "calculated_deposit_amount",
                        "calculated_monthly_payment",
                        "calculated_daily_payment",
                        "calculated_6_month_total",
                        "calculated_6_month_monthly",
                        "calculated_6_month_daily",
                        "calculated_3_month_total",
                        "calculated_3_month_monthly",
                        "calculated_3_month_daily",
                        "status",
                    ]
                )
                return redirect("kyc_capture", app_id=app.id)

        messages.error(request, form_error)

    return render(
        request,
        "applications/choose_device.html",
        {
            "app": app,
            "deals": deals,
            "deal_options": deal_options,
            "brand_names": brand_names,
            "form_error": form_error,
        },
    )


@login_required
def kyc_capture(request, app_id):
    app = merchant_application(request, app_id)

    if request.method == "POST":
        form = KYCForm(request.POST, request.FILES, instance=app)
        if form.is_valid():
            app = form.save(commit=False)
            app.status = "kyc"
            app.save()
            return redirect("location_details", app_id=app.id)
    else:
        form = KYCForm(instance=app)

    kyc_complete = bool(app.customer_face_image and app.id_front_image and app.id_back_image)
    return render(request, "applications/kyc.html", {"app": app, "form": form, "kyc_complete": kyc_complete})


@login_required
def location_details(request, app_id):
    app = merchant_application(request, app_id)

    if request.method == "POST":
        form = LocationNextOfKinForm(request.POST, request.FILES, instance=app)
        if form.is_valid():
            app = form.save(commit=False)
            app.location = app.precise_location
            app.status = "location_details"
            app.save()
            return redirect("work_details", app_id=app.id)
    else:
        form = LocationNextOfKinForm(instance=app)

    return render(
        request,
        "applications/location.html",
        {
            "app": app,
            "form": form,
            "geography_data": geography_json_data(),
        },
    )


@login_required
def work_details(request, app_id):
    app = merchant_application(request, app_id)

    if request.method == "POST":
        form = WorkProofForm(request.POST, instance=app)
        if form.is_valid():
            app = form.save(commit=False)
            app.status = "work_details"
            app.save()
            return redirect("signature", app_id=app.id)
    else:
        form = WorkProofForm(instance=app)

    return render(request, "applications/work.html", {"app": app, "form": form})


@login_required
def signature(request, app_id):
    app = merchant_application(request, app_id)

    if request.method == "POST":
        form = SignatureForm(request.POST, instance=app)
        if form.is_valid():
            app = form.save(commit=False)
            if form.signature_file:
                app.signature_image.save(form.signature_file.name, form.signature_file, save=False)
            app.save(update_fields=["signature_image", "agreed_to_terms"])
            app.submit()
            messages.success(request, "Application submitted.")
            return redirect("application_submitted", app_id=app.id)
    else:
        form = SignatureForm(instance=app)

    return render(request, "applications/signature.html", {"app": app, "form": form})


@login_required
def capture_imei(request, app_id):
    return redirect("kyc_capture", app_id=app_id)


@login_required
def application_submitted(request, app_id):
    app = get_object_or_404(
        FinancingApplication.objects.select_related("created_by", "claimed_by"),
        id=app_id,
        created_by=request.user,
    )
    return render(request, "applications/submitted.html", {"app": app})


@login_required
def application_corrections(request, app_id):
    app = get_object_or_404(
        FinancingApplication.objects.select_related("created_by", "claimed_by", "reviewed_by"),
        id=app_id,
        created_by=request.user,
    )
    return render(
        request,
        "applications/corrections.html",
        {
            "app": app,
            "correction_labels": app.correction_field_labels(),
            "edit_url": app.get_correction_start_url(),
        },
    )


@login_required
def application_detail(request, app_id):
    app = get_object_or_404(
        FinancingApplication.objects.select_related("deal", "contract", "created_by", "claimed_by", "reviewed_by"),
        id=app_id,
    )

    if not user_can_view_application(request.user, app):
        raise PermissionDenied

    incomplete_statuses = [
        "draft",
        "started",
        "customer_details",
        "device_selection",
        "kyc",
        "kyc_capture",
        "location_details",
        "work_details",
        "signature",
        "correction_requested",
        "imei_required",
    ]

    return render(
        request,
        "applications/detail.html",
        {
            "app": app,
            "is_incomplete": app.status in incomplete_statuses,
        },
    )


@login_required
def active_applications(request):
    apps = FinancingApplication.objects.select_related("claimed_by").filter(
        created_by=request.user,
        status__in=ACTIVE_STATUSES,
    ).order_by("-created_at")

    return render(request, "applications/list.html", {"apps": apps, "title": "Active"})


@login_required
def completed_applications(request):
    apps = FinancingApplication.objects.select_related("claimed_by").filter(
        created_by=request.user,
        status__in=["contract_complete", "completed"],
    ).order_by("-created_at")

    return render(request, "applications/list.html", {"apps": apps, "title": "Completed"})


@login_required
def rejected_applications(request):
    apps = FinancingApplication.objects.select_related("claimed_by").filter(
        created_by=request.user,
        status="rejected",
    ).order_by("-created_at")

    return render(request, "applications/list.html", {"apps": apps, "title": "Archived & Rejected"})
